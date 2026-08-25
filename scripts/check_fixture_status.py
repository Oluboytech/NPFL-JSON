#!/usr/bin/env python3
"""
check_fixture_status.py

Polls SoccerHub Data Service to detect which NPFL fixtures in this repo
have changed status (kicked off / finished / postponed), WITHOUT ever
writing raw score, lineup, or player data into this public repository.

This script's only output is:
  1. A local rate-limit ledger (calls_used_today.json) so we never exceed
     the daily call budget.
  2. GitHub issues asking a human to manually confirm and enter the
     result, sourced from public reporting (NPFL's own site, news, etc).

The raw API response is used transiently in memory to decide "should I
flag this fixture for human review?" and is never serialized to disk or
committed. This is the whole point: SoccerHub Data Service is a trigger,
not a source.

Required environment variables (set as GitHub Actions secrets):
  BSD_API_KEY        - SoccerHub Data Service API key
  BSD_API_BASE_URL    - base URL for SoccerHub Data Service
  GITHUB_TOKEN        - provided automatically by Actions, used to open issues
  GITHUB_REPOSITORY   - "owner/repo", provided automatically by Actions

Daily call budget: configurable, default conservative (see DAILY_CALL_BUDGET).
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, date
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ---- Configuration -----------------------------------------------------

DAILY_CALL_BUDGET = int(os.environ.get("DAILY_CALL_BUDGET", "500"))  # well under 7500
LEDGER_PATH = Path(".automation/calls_used_today.json")
FIXTURES_PATH = Path("2026-27/ng.1.json")

BSD_API_KEY = os.environ.get("BSD_API_KEY")
BSD_API_BASE_URL = os.environ.get("BSD_API_BASE_URL", "").rstrip("/")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")  # "owner/repo"

MAX_RETRIES = 3
BACKOFF_SECONDS = 2


# ---- Rate limit ledger ---------------------------------------------------

def load_ledger():
    if not LEDGER_PATH.exists():
        return {"date": str(date.today()), "calls_used": 0}
    ledger = json.loads(LEDGER_PATH.read_text())
    if ledger.get("date") != str(date.today()):
        # New day, reset
        return {"date": str(date.today()), "calls_used": 0}
    return ledger


def save_ledger(ledger):
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2))


def calls_remaining(ledger):
    return max(0, DAILY_CALL_BUDGET - ledger["calls_used"])


# ---- SoccerHub Data Service client (circuit-breaker style) --------------

class CircuitOpenError(Exception):
    pass


class BSDClient:
    """
    Minimal SoccerHub Data Service client. Every call increments the
    ledger BEFORE the request is made, so a crash mid-run never
    under-counts usage against the budget.
    """

    def __init__(self, ledger):
        self.ledger = ledger
        self.failures = 0
        self.circuit_open = False

    def _check_budget(self):
        if calls_remaining(self.ledger) <= 0:
            raise CircuitOpenError("Daily call budget exhausted; stopping for today.")

    def get_fixture_status(self, external_match_ref: str) -> dict | None:
        """
        Returns a small status-only dict, e.g.:
          {"status": "finished", "kicked_off": true}
        Never returns or retains score/lineup detail beyond this call's
        local scope - caller must not persist raw payloads.

        external_match_ref is stored in the mapping file as "bsd-<id>";
        the numeric id is what the API's /events/{id}/ path needs.
        """
        if self.circuit_open:
            raise CircuitOpenError("Circuit breaker open, skipping further calls this run.")

        self._check_budget()

        event_id = external_match_ref.removeprefix("bsd-")
        url = f"{BSD_API_BASE_URL}/events/{event_id}/"
        req = Request(url, headers={"Authorization": f"Token {BSD_API_KEY}"})

        for attempt in range(1, MAX_RETRIES + 1):
            self.ledger["calls_used"] += 1
            save_ledger(self.ledger)  # persist BEFORE the network call
            try:
                with urlopen(req, timeout=10) as resp:
                    raw = json.loads(resp.read())
                    self.failures = 0
                    # Extract ONLY status-shape info; discard the rest
                    # immediately so raw payload never leaves this function.
                    # Real status values: notstarted | inprogress | penalties | finished
                    return {
                        "status": raw.get("status"),
                        "kicked_off": raw.get("status") in ("inprogress", "penalties", "finished"),
                    }
            except (HTTPError, URLError, TimeoutError) as e:
                self.failures += 1
                if self.failures >= 5:
                    self.circuit_open = True
                    print(f"Circuit breaker tripped after repeated failures: {e}", file=sys.stderr)
                    return None
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_SECONDS * attempt)
                else:
                    print(f"Failed to reach SoccerHub Data Service for {external_match_ref}: {e}", file=sys.stderr)
                    return None
        return None


# ---- GitHub issue creation ------------------------------------------------

def open_github_issue(title: str, body: str, labels: list[str]):
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        print(f"[dry-run, no GH token] Would open issue: {title}")
        return
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues"
    payload = json.dumps({"title": title, "body": body, "labels": labels}).encode()
    req = Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=10) as resp:
            resp.read()
            print(f"Opened issue: {title}")
    except (HTTPError, URLError) as e:
        print(f"Failed to open GitHub issue: {e}", file=sys.stderr)


def issue_already_open(external_match_ref: str) -> bool:
    """Check open issues for this match ref to avoid duplicate issues."""
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        return False
    url = (
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues"
        f"?state=open&labels=result-needed"
    )
    req = Request(url, headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urlopen(req, timeout=10) as resp:
            issues = json.loads(resp.read())
            return any(external_match_ref in (i.get("title") or "") for i in issues)
    except (HTTPError, URLError):
        return False  # fail open; worst case a duplicate issue


# ---- Fixture selection: only check what's plausibly relevant today -------

def load_fixtures():
    data = json.loads(FIXTURES_PATH.read_text())
    return data


def fixtures_due_for_check(data):
    """
    Only fixtures dated today or earlier, still marked 'scheduled', are
    worth a status check. Everything in the future is skipped - no point
    burning budget on matches that haven't happened yet.
    """
    today = date.today().isoformat()
    due = []
    for m in data["matches"]:
        if m.get("status") == "scheduled" and m.get("date", "9999-99-99") <= today:
            due.append(m)
    return due


def external_ref_for(match: dict) -> str | None:
    """
    This repo's JSON doesn't store SoccerHub Data Service's internal
    fixture IDs (deliberately - we don't want provider-specific
    identifiers baked into public data). A private, gitignored mapping
    file (see .automation/README.md and scripts/build_bsd_id_map.py)
    holds team1/team2/date -> fixture ID; look it up here.
    """
    mapping_path = Path(".automation/bsd_id_map.json")
    if not mapping_path.exists():
        return None
    mapping = json.loads(mapping_path.read_text())
    key = f"{match['date']}:{match['team1']}:{match['team2']}"
    return mapping.get(key)


# ---- Main ------------------------------------------------------------------

def main():
    if not BSD_API_KEY or not BSD_API_BASE_URL:
        print("BSD_API_KEY / BSD_API_BASE_URL not set - nothing to do.", file=sys.stderr)
        sys.exit(0)

    ledger = load_ledger()
    print(f"Calls used today so far: {ledger['calls_used']} / {DAILY_CALL_BUDGET}")

    data = load_fixtures()
    due = fixtures_due_for_check(data)
    print(f"{len(due)} fixture(s) due for a status check.")

    if not due:
        return

    client = BSDClient(ledger)
    flagged = 0

    for match in due:
        if calls_remaining(ledger) <= 0:
            print("Daily budget exhausted, stopping.")
            break

        ref = external_ref_for(match)
        if not ref:
            continue  # no mapping available, skip silently

        label = f"{match['team1']} vs {match['team2']} ({match['date']})"

        if issue_already_open(ref):
            continue

        try:
            status = client.get_fixture_status(ref)
        except CircuitOpenError as e:
            print(str(e))
            break

        if status and status.get("status") == "finished":
            title = f"Result needed: {label} [{ref}]"
            body = (
                f"SoccerHub Data Service indicates this fixture has finished.\n\n"
                f"**Do not copy raw score/lineup data directly into this repo.**\n"
                f"Please confirm the final score from a public source "
                f"(NPFL's own site, official club channels, or news "
                f"reporting) and update `2026-27/ng.1.json` manually:\n\n"
                f"- Set `status` to `finished`\n"
                f"- Set `score.ft` to `[home, away]`\n\n"
                f"Match: {match['team1']} vs {match['team2']}, "
                f"{match['round']}, {match['date']}"
            )
            open_github_issue(title, body, labels=["result-needed", "automation"])
            flagged += 1
        elif status and status.get("status") == "postponed":
            title = f"Schedule change flagged: {label} [{ref}]"
            body = (
                f"SoccerHub Data Service indicates this fixture's status changed to "
                f"`postponed`. Please verify against a public source and "
                f"update the fixture's `status`/`date` in "
                f"`2026-27/ng.1.json` manually."
            )
            open_github_issue(title, body, labels=["schedule-change", "automation"])
            flagged += 1

    print(f"Done. {flagged} issue(s) opened. Calls used today: {ledger['calls_used']} / {DAILY_CALL_BUDGET}")


if __name__ == "__main__":
    main()
