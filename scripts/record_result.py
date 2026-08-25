#!/usr/bin/env python3
"""
record_result.py

Takes a human-confirmed match result (typed by a maintainer, sourced from
public reporting - NOT copied from any data provider's raw API response)
and patches it into 2026-27/ng.1.json safely.

This is the other half of the "SoccerHub Data Service triggers, human
confirms, script applies" workflow: check_fixture_status.py detects that
a match probably finished and opens an issue; a maintainer looks up the
real score somewhere public; this script writes it in without needing to
hand-edit JSON (and without risking a typo that breaks the file for every
consumer of this repo).

Usage (interactive):
    python3 scripts/record_result.py

Usage (non-interactive, e.g. scripted from a resolved GitHub issue):
    python3 scripts/record_result.py \\
        --date 2026-08-28 \\
        --team1 "Shooting Stars" --team2 "Inter Lagos" \\
        --home-score 2 --away-score 1 \\
        --status finished

Safety properties:
  - Refuses to guess which fixture you mean if date+teams don't match
    exactly one row.
  - Never touches any field except status/score/date/time/venue
    (whichever you explicitly pass).
  - Validates the file is still well-formed JSON with the same match
    count before writing - a corrupt write is refused, not silently
    partial.
  - Prints a diff-style summary before writing so a mistake is obvious
    before it's committed.
"""

import argparse
import json
import sys
from pathlib import Path

FIXTURES_PATH = Path("2026-27/ng.1.json")

VALID_STATUSES = {"scheduled", "finished", "postponed", "cancelled"}


def load_fixtures():
    if not FIXTURES_PATH.exists():
        print(f"Cannot find {FIXTURES_PATH} - run this from the repo root.", file=sys.stderr)
        sys.exit(1)
    return json.loads(FIXTURES_PATH.read_text())


def find_match(data, date_str, team1, team2):
    candidates = [
        m for m in data["matches"]
        if m["date"] == date_str
        and {m["team1"], m["team2"]} == {team1, team2}
    ]
    return candidates


def apply_result(match, home_score, away_score, status, new_date, new_time, new_venue):
    """
    Mutates `match` in place. home_score/away_score map to team1/team2 as
    printed in the fixture (NOT necessarily "home" in a literal sense for
    the rare neutral-venue game, but team1 is always listed first).
    """
    before = dict(match)

    if status:
        match["status"] = status
    if home_score is not None and away_score is not None:
        match["score"] = {"ft": [home_score, away_score]}
        if not status:
            match["status"] = "finished"
    if new_date:
        match["date"] = new_date
    if new_time:
        match["time"] = new_time
    if new_venue:
        match["venue"] = new_venue

    return before, match


def print_diff(before, after):
    print("\n--- Change summary ---")
    for key in ("status", "score", "date", "time", "venue"):
        if before.get(key) != after.get(key):
            print(f"  {key}: {before.get(key)!r} -> {after.get(key)!r}")
    print("----------------------\n")


def save_fixtures(data, expected_match_count):
    if len(data["matches"]) != expected_match_count:
        print(
            f"Refusing to save: match count changed unexpectedly "
            f"({expected_match_count} -> {len(data['matches'])}). "
            f"This should never happen from a single-result edit.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate round-trip before writing to disk
    serialized = json.dumps(data, indent=2, ensure_ascii=False)
    json.loads(serialized)  # will raise if somehow invalid

    FIXTURES_PATH.write_text(serialized + "\n", encoding="utf-8")
    print(f"Saved {FIXTURES_PATH}")


def interactive_flow():
    data = load_fixtures()
    expected_count = len(data["matches"])

    date_str = input("Match date (YYYY-MM-DD): ").strip()
    team1 = input("Team 1 (as it appears in the fixture, e.g. 'Shooting Stars'): ").strip()
    team2 = input("Team 2: ").strip()

    matches = find_match(data, date_str, team1, team2)
    if len(matches) == 0:
        print("No fixture found matching that date + team pair. Check spelling/date.", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print("Multiple fixtures matched - this shouldn't happen. Aborting.", file=sys.stderr)
        sys.exit(1)

    match = matches[0]
    print(f"\nFound: {match['team1']} vs {match['team2']}, {match['round']}, {match['date']}")
    print(f"Current status: {match['status']}, score: {match['score']}")

    confirm_source = input(
        "\nWhere did you confirm this score? (e.g. 'NPFL official site', "
        "'Punch Sports', 'club Twitter') - for your own record, not stored: "
    ).strip()
    if not confirm_source:
        print("Please note a source before recording a result - this keeps the "
              "data trail honest even though it isn't written to the file.")

    raw_score = input(f"Final score as '{match['team1']} {match['team2']}', e.g. '2 1': ").strip()
    try:
        home_score, away_score = (int(x) for x in raw_score.split())
    except ValueError:
        print("Couldn't parse score - expected two numbers separated by a space.", file=sys.stderr)
        sys.exit(1)

    before, after = apply_result(
        match, home_score, away_score, status="finished",
        new_date=None, new_time=None, new_venue=None,
    )
    print_diff(before, after)

    if input("Write this to the file? [y/N] ").strip().lower() != "y":
        print("Aborted, nothing written.")
        sys.exit(0)

    save_fixtures(data, expected_count)


def cli_flow(args):
    data = load_fixtures()
    expected_count = len(data["matches"])

    matches = find_match(data, args.date, args.team1, args.team2)
    if len(matches) == 0:
        print("No fixture found matching that date + team pair.", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print("Multiple fixtures matched - refusing to guess.", file=sys.stderr)
        sys.exit(1)

    if args.status and args.status not in VALID_STATUSES:
        print(f"--status must be one of {VALID_STATUSES}", file=sys.stderr)
        sys.exit(1)

    match = matches[0]
    before, after = apply_result(
        match,
        home_score=args.home_score,
        away_score=args.away_score,
        status=args.status,
        new_date=args.new_date,
        new_time=args.new_time,
        new_venue=args.new_venue,
    )
    print_diff(before, after)
    save_fixtures(data, expected_count)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", help="Fixture date, YYYY-MM-DD")
    parser.add_argument("--team1", help="Team 1 exactly as in ng.1.json")
    parser.add_argument("--team2", help="Team 2 exactly as in ng.1.json")
    parser.add_argument("--home-score", type=int, help="team1's score")
    parser.add_argument("--away-score", type=int, help="team2's score")
    parser.add_argument("--status", choices=sorted(VALID_STATUSES), help="New status")
    parser.add_argument("--new-date", help="Corrected date (schedule change), YYYY-MM-DD")
    parser.add_argument("--new-time", help="Corrected kickoff time")
    parser.add_argument("--new-venue", help="Corrected venue")

    args = parser.parse_args()

    if args.date and args.team1 and args.team2:
        cli_flow(args)
    elif not any(vars(args).values()):
        interactive_flow()
    else:
        parser.error("Provide --date, --team1, and --team2 together for non-interactive mode, "
                      "or no arguments at all for interactive mode.")


if __name__ == "__main__":
    main()
