#!/usr/bin/env python3
"""
build_bsd_id_map.py

SoccerHub.ng data-layer tooling.

Matches fixtures in 2026-27/ng.1.json against SoccerHub Data Service's
fixture list for the Nigeria Premier Football League, keyed by
(date, home team, away team) using the alias table in
bsd_team_aliases.py, and produces/updates the local mapping file:

    .automation/bsd_id_map.json

...in the "date:team1:team2" -> "bsd-<fixture-id>" format that
scripts/check_fixture_status.py expects.

This is a LOCAL, MANUALLY-RUN tool. It is not part of the scheduled CI
workflow (which only reads the mapping via the BSD_ID_MAP_JSON secret).
Run this whenever a new round of fixtures becomes available, then paste
the resulting file's contents into the BSD_ID_MAP_JSON repo secret.

Usage:
    export BSD_API_KEY=...
    export BSD_API_BASE_URL=...
    python3 scripts/build_bsd_id_map.py

    # Merge into an existing mapping instead of overwriting:
    python3 scripts/build_bsd_id_map.py --merge

    # Only print what WOULD change, don't write the file:
    python3 scripts/build_bsd_id_map.py --dry-run

Note on coverage: only the upcoming round(s) tend to be available at
any given time, not the full season in advance. Re-running this script
periodically (weekly is reasonable) and merging is expected workflow,
not a sign anything is broken.
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).parent))
from bsd_team_aliases import BSD_LEAGUE_ID, repo_name_to_bsd_name  # noqa: E402

FIXTURES_PATH = Path("2026-27/ng.1.json")
OUT_PATH = Path(".automation/bsd_id_map.json")

BSD_API_KEY = os.environ.get("BSD_API_KEY")
BSD_API_BASE_URL = os.environ.get("BSD_API_BASE_URL", "").rstrip("/")

# How far ahead to ask for fixtures. Only the next few rounds tend to be
# loaded at any given time, so a wide window is cheap and safe.
LOOKAHEAD_DAYS = 120


def fetch_bsd_matches():
    """
    Calls SoccerHub Data Service's match search endpoint for the NPFL
    league and returns the raw list of match dicts. Adjust the
    path/params below if your account's REST shape differs from what's
    assumed here (mirrors the fields used elsewhere in SoccerHub's data
    integration, e.g. NAM's bsd-api.php).
    """
    if not BSD_API_KEY or not BSD_API_BASE_URL:
        print("BSD_API_KEY / BSD_API_BASE_URL not set in environment.", file=sys.stderr)
        sys.exit(1)

    date_from = date.today().isoformat()
    date_to = (date.today() + timedelta(days=LOOKAHEAD_DAYS)).isoformat()

    url = (
        f"{BSD_API_BASE_URL}/matches"
        f"?league={BSD_LEAGUE_ID}&date_from={date_from}&date_to={date_to}"
    )
    req = Request(url, headers={"Authorization": f"Bearer {BSD_API_KEY}"})

    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read())
    except (HTTPError, URLError) as e:
        print(f"Failed to reach SoccerHub Data Service: {e}", file=sys.stderr)
        sys.exit(1)

    # Handle both a bare list and a DRF-style {"results": [...]} envelope.
    return payload.get("results", payload) if isinstance(payload, dict) else payload


def build_mapping(fixtures, bsd_matches):
    name_lookup = repo_name_to_bsd_name()

    bsd_by_key = {}
    for m in bsd_matches:
        bsd_date = m["event_date"][:10]
        bsd_by_key[(bsd_date, m["home_team"], m["away_team"])] = m["id"]

    mapping = {}
    unmatched = []

    for fx in fixtures:
        repo_key = f"{fx['date']}:{fx['team1']}:{fx['team2']}"

        bsd_home = name_lookup.get(fx["team1"])
        bsd_away = name_lookup.get(fx["team2"])
        if not bsd_home or not bsd_away:
            unmatched.append((repo_key, "no alias for team name(s) — check bsd_team_aliases.py"))
            continue

        bsd_id = bsd_by_key.get((fx["date"], bsd_home, bsd_away))
        if bsd_id is None:
            unmatched.append((repo_key, "not in the currently loaded fixtures"))
            continue

        mapping[repo_key] = f"bsd-{bsd_id}"

    return mapping, unmatched


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--merge", action="store_true",
                         help="Merge newly-found IDs into the existing mapping file instead of overwriting it.")
    parser.add_argument("--dry-run", action="store_true",
                         help="Print what would be written without touching the file.")
    args = parser.parse_args()

    if not FIXTURES_PATH.exists():
        print(f"Fixtures file not found: {FIXTURES_PATH}", file=sys.stderr)
        sys.exit(1)

    fixtures = json.loads(FIXTURES_PATH.read_text())["matches"]
    bsd_matches = fetch_bsd_matches()

    new_mapping, unmatched = build_mapping(fixtures, bsd_matches)

    if args.merge and OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text())
        merged = {**existing, **new_mapping}
        added = set(new_mapping) - set(existing)
        changed = {k for k in new_mapping if k in existing and existing[k] != new_mapping[k]}
        final = merged
    else:
        added = set(new_mapping)
        changed = set()
        final = new_mapping

    print(f"SoccerHub Data Service returned {len(bsd_matches)} fixture(s) for league {BSD_LEAGUE_ID}.")
    print(f"Matched {len(new_mapping)} / {len(fixtures)} repo fixtures this run.")
    print(f"  new: {len(added)}   changed: {len(changed)}")

    if unmatched:
        print(f"\n{len(unmatched)} unmatched (normal if those rounds haven't been loaded yet):")
        for key, reason in unmatched[:15]:
            print(f"  - {key}  [{reason}]")
        if len(unmatched) > 15:
            print(f"  ... and {len(unmatched) - 15} more")

    if args.dry_run:
        print(f"\n--dry-run: not writing {OUT_PATH}")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(final, indent=2, sort_keys=True))
    print(f"\nWrote {OUT_PATH} ({len(final)} total mapping(s)).")
    print("Next step: copy this file's contents into the BSD_ID_MAP_JSON repo secret.")


if __name__ == "__main__":
    main()
