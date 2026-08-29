#!/usr/bin/env python3
"""
apply_bsd_results.py

SoccerHub.ng data-layer tooling.

Fetches confirmed match results directly from SoccerHub Data Service
(BSD) and patches them into 2026-27/ng.1.json. This replaces the
earlier "BSD triggers, human/official-site confirms" split: BSD's
event detail already carries the final score once a match is finished,
so this applies it directly rather than only flagging it for review.

NOTE ON PROVENANCE: unlike scripts/apply_official_results.py (which
reads scores from npfl.com.ng, the league's own public site), this
script republishes data from a third-party API that has no published
terms of service covering redistribution. That's a deliberate,
accepted tradeoff, not an oversight - see the project history/README
for context. If BSD's terms change or a redistribution concern is
raised, scripts/apply_official_results.py is the safer fallback path
and can be swapped back in with no schema changes, since both scripts
write the same 2026-27/ng.1.json shape.

Uses the same fixture-ID mapping as check_fixture_status.py
(.automation/bsd_id_map.json, populated via the BSD_ID_MAP_JSON
secret) to know which BSD event id corresponds to which repo fixture -
so this only ever queries events you've already confirmed the mapping
for, never a guessed id.

Safety net unchanged: if a fixture's mapping is missing, BSD is
unreachable, or BSD's event doesn't show a parseable final score yet,
this falls back to opening the same "result-needed" GitHub issue the
other result scripts use - so nothing is ever silently skipped.

Usage (intended to run inside GitHub Actions):
    export BSD_API_KEY=...
    export BSD_API_BASE_URL=...
    export GITHUB_TOKEN=...
    export GITHUB_REPOSITORY=Oluboytech/NPFL-JSON
    python3 scripts/apply_bsd_results.py

    # Preview without writing or committing:
    python3 scripts/apply_bsd_results.py --dry-run
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).parent))
from bsd_team_aliases import BSD_LEAGUE_ID  # noqa: E402  (kept for reference/consistency)

FIXTURES_PATH = Path("2026-27/ng.1.json")
MAPPING_PATH = Path(".automation/bsd_id_map.json")  # gitignored, written from the secret

BSD_API_KEY = os.environ.get("BSD_API_KEY")
BSD_API_BASE_URL = os.environ.get("BSD_API_BASE_URL", "").rstrip("/")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")

# BSD's confirmed status vocabulary (see scripts/check_fixture_status.py).
FINISHED_STATUSES = {"finished"}


def bsd_get(path):
    url = f"{BSD_API_BASE_URL}{path}"
    req = Request(url, headers={"Authorization": f"Token {BSD_API_KEY}"})
    with urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def extract_score(event: dict):
    """
    Returns (home_score, away_score) if the event data has a confirmed
    final score, else None. Deliberately checks a few plausible field
    shapes rather than assuming one, since the exact JSON key names
    weren't confirmed against raw API output before this was written -
    only against the rendered site. If BSD's actual shape doesn't match
    any of these, this returns None and the fixture safely falls back
    to a GitHub issue instead of silently mis-reading a wrong field.
    """
    if event.get("status") not in FINISHED_STATUSES:
        return None

    # Shape A: separate home_score / away_score fields
    if "home_score" in event and "away_score" in event:
        hs, as_ = event.get("home_score"), event.get("away_score")
        if isinstance(hs, int) and isinstance(as_, int):
            return (hs, as_)

    # Shape B: nested score object, e.g. {"score": {"home": 2, "away": 1}}
    score_obj = event.get("score")
    if isinstance(score_obj, dict):
        hs, as_ = score_obj.get("home"), score_obj.get("away")
        if isinstance(hs, int) and isinstance(as_, int):
            return (hs, as_)
        # Some APIs nest full-time score under "ft": [home, away]
        ft = score_obj.get("ft")
        if isinstance(ft, list) and len(ft) == 2 and all(isinstance(x, int) for x in ft):
            return (ft[0], ft[1])

    # Shape C: top-level "ft" list
    ft = event.get("ft")
    if isinstance(ft, list) and len(ft) == 2 and all(isinstance(x, int) for x in ft):
        return (ft[0], ft[1])

    return None


def gh_request(method, path, body=None):
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urlopen(req, timeout=20) as resp:
        body_bytes = resp.read()
        return json.loads(body_bytes) if body_bytes else None


def open_result_needed_issue(match: dict, reason: str):
    title = (
        f"Result needed: {match['team1']} vs {match['team2']} "
        f"({match['date']}) [bsd-score-unavailable]"
    )
    body = (
        f"SoccerHub Data Service was queried directly for this fixture's "
        f"result but a confirmed score could not be extracted.\n\n"
        f"Reason: {reason}\n\n"
        f"Please confirm the final score from a public source (NPFL's "
        f"own site, official club channels, or news reporting) and "
        f"update `2026-27/ng.1.json` manually:\n\n"
        f"- Set `status` to `finished`\n"
        f"- Set `score.ft` to `[home, away]`\n\n"
        f"Match: {match['team1']} vs {match['team2']}, "
        f"Matchday {match.get('matchday', '?')}, {match['date']}"
    )
    gh_request("POST", "/issues", {
        "title": title,
        "body": body,
        "labels": ["automation", "result-needed"],
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                         help="Print what would change without writing, committing, or opening issues.")
    args = parser.parse_args()

    if not BSD_API_KEY or not BSD_API_BASE_URL:
        print("BSD_API_KEY / BSD_API_BASE_URL not set.", file=sys.stderr)
        sys.exit(1)
    if not FIXTURES_PATH.exists():
        print(f"Fixtures file not found: {FIXTURES_PATH}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(FIXTURES_PATH.read_text())
    matches = data["matches"]

    if not MAPPING_PATH.exists():
        print(f"No mapping file at {MAPPING_PATH} - nothing to check this run.")
        return
    mapping = json.loads(MAPPING_PATH.read_text())

    today = date.today().isoformat()
    due = [
        m for m in matches
        if m.get("status") == "scheduled" and m.get("date", "9999-99-99") <= today
    ]

    if not due:
        print("No fixtures due for a result check.")
        return

    print(f"{len(due)} fixture(s) due for a result check.")

    updated = 0
    issues_opened = 0

    for m in due:
        repo_key = f"{m['date']}:{m['team1']}:{m['team2']}"
        external_ref = mapping.get(repo_key)

        if not external_ref:
            print(f"  ? {m['team1']} vs {m['team2']}: no BSD id mapped for this fixture yet")
            if not args.dry_run:
                open_result_needed_issue(m, "no BSD fixture id mapped yet (see .automation/README.md)")
                issues_opened += 1
            continue

        event_id = external_ref.removeprefix("bsd-")

        try:
            event = bsd_get(f"/events/{event_id}/")
        except (HTTPError, URLError) as e:
            print(f"  ? {m['team1']} vs {m['team2']}: could not reach BSD ({e})")
            if not args.dry_run:
                open_result_needed_issue(m, f"could not reach SoccerHub Data Service: {e}")
                issues_opened += 1
            continue

        score = extract_score(event)

        if score is not None:
            m["status"] = "finished"
            if not isinstance(m.get("score"), dict):
                m["score"] = {}
            m["score"]["ft"] = list(score)
            updated += 1
            print(f"  \u2713 {m['team1']} {score[0]}-{score[1]} {m['team2']}")
            continue

        reason = (
            f"BSD status is {event.get('status')!r} - not yet finished, "
            f"or score fields didn't match any known shape"
        )
        print(f"  ? {m['team1']} vs {m['team2']}: {reason}")
        if not args.dry_run:
            open_result_needed_issue(m, reason)
            issues_opened += 1

    print(f"\n{updated} result(s) confirmed and applied, {issues_opened} issue(s) opened.")

    if updated == 0:
        return

    if args.dry_run:
        print("--dry-run: not writing ng.1.json or committing.")
        return

    FIXTURES_PATH.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Updated {FIXTURES_PATH}")


if __name__ == "__main__":
    main()
