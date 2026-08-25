#!/usr/bin/env python3
"""
sync_team_data.py

SoccerHub.ng data-layer tooling.

Enriches 2026-27/teams/ng.1.teams.json with a small amount of public-
safe data from SoccerHub Data Service: each team's bsd_team_id (for
cross-referencing) and current_coach (name only).

WHAT THIS DELIBERATELY DOES NOT PUBLISH:
This repo is a public, redistributable dataset. Internal/derived use of
SoccerHub Data Service's data is fine (see .automation/README.md and
scripts/check_fixture_status.py for the existing pattern of using it as
a trigger, not a source). To stay consistent with that:
  - No squad/roster data, player names, or injury status
  - No manager tactical profiles, formations, win/loss stats, or any
    other derived performance metric
  - No odds, predictions, or market data of any kind
If you need any of that for SoccerHub/NAM internally, pull it directly
from the data service there — don't route it through this public repo.

What IS published: team id/name/short_name (already public), venue
name/city (already public, standard sports-reference info), and a
coach's name (a public fact about who manages a football club).

Usage:
    export BSD_API_KEY=...
    export BSD_API_BASE_URL=...
    python3 scripts/sync_team_data.py

    # Preview without writing:
    python3 scripts/sync_team_data.py --dry-run

Existing hand-maintained fields (stadium, note, city, state, code) are
preserved. Enrichment only fills in bsd_team_id / current_coach, and
only overwrites `stadium` if the repo's existing value is null — your
manual data always wins for fields you've already filled in.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).parent))
from bsd_team_aliases import TEAM_ALIASES  # noqa: E402

TEAMS_PATH = Path("2026-27/teams/ng.1.teams.json")

BSD_API_KEY = os.environ.get("BSD_API_KEY")
BSD_API_BASE_URL = os.environ.get("BSD_API_BASE_URL", "").rstrip("/")


def bsd_get(path):
    url = f"{BSD_API_BASE_URL}{path}"
    req = Request(url, headers={"Authorization": f"Bearer {BSD_API_KEY}"})
    try:
        with urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except (HTTPError, URLError) as e:
        print(f"  ! request failed for {path}: {e}", file=sys.stderr)
        return None


def fetch_bsd_team_data(bsd_team_id):
    """
    Returns {"venue_name": str|None, "coach_name": str|None} for one team
    id, using only public-safe fields (see module docstring for what is
    intentionally excluded).
    """
    result = {"venue_name": None, "coach_name": None}

    team = bsd_get(f"/teams/{bsd_team_id}")
    if team and team.get("venue_id"):
        venue = bsd_get(f"/venues/{team['venue_id']}")
        if venue:
            result["venue_name"] = venue.get("name")

    managers = bsd_get(f"/managers?team_id={bsd_team_id}")
    if managers:
        results = managers.get("results", managers) if isinstance(managers, dict) else managers
        if results:
            result["coach_name"] = results[0].get("name")

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                         help="Print the changes without writing the file.")
    args = parser.parse_args()

    if not BSD_API_KEY or not BSD_API_BASE_URL:
        print("BSD_API_KEY / BSD_API_BASE_URL not set in environment.", file=sys.stderr)
        sys.exit(1)

    if not TEAMS_PATH.exists():
        print(f"Teams file not found: {TEAMS_PATH}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(TEAMS_PATH.read_text())

    updated, skipped, no_bsd_data = 0, 0, 0

    for team in data["teams"]:
        alias = TEAM_ALIASES.get(team["id"])
        if not alias:
            print(f"  ? {team['id']}: no data-service alias configured, skipping "
                  f"(add it to scripts/bsd_team_aliases.py)")
            skipped += 1
            continue

        bsd_id = alias["bsd_team_id"]
        team["bsd_team_id"] = bsd_id

        bsd_data = fetch_bsd_team_data(bsd_id)

        changed = False
        if bsd_data["venue_name"] and not team.get("stadium"):
            team["stadium"] = bsd_data["venue_name"]
            changed = True
        if bsd_data["coach_name"]:
            if team.get("current_coach") != bsd_data["coach_name"]:
                team["current_coach"] = bsd_data["coach_name"]
                changed = True
        else:
            no_bsd_data += 1

        if changed:
            updated += 1
        print(f"  {'✓' if changed else '·'} {team['name']}: "
              f"coach={bsd_data['coach_name'] or '(none on record)'}")

    data["bsd_enrichment_note"] = (
        "bsd_team_id and current_coach are enriched via SoccerHub's own "
        "data service (id/name/coach only — no squad, injury, tactical, "
        "or odds-derived data is published here). Coach data reflects "
        "records as of last_updated and may lag actual managerial "
        "changes; verify before relying on it."
    )

    print(f"\n{updated} team(s) updated, {skipped} skipped (no alias), "
          f"{no_bsd_data} with no coach on record.")

    if args.dry_run:
        print("\n--dry-run: not writing file. Preview:")
        print(json.dumps(data, indent=2)[:2000] + "\n...")
        return

    TEAMS_PATH.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Wrote {TEAMS_PATH}")


if __name__ == "__main__":
    main()
