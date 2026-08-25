#!/usr/bin/env python3
"""Validate the NPFL dataset without changing any data.

This validator is deliberately dependency-free. It checks JSON validity,
referential integrity, fixture IDs, the 20-team/380-match structure, and the
existing result/status rules while preserving the existing public field names.
"""

import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEASON = "2026-27"
FIXTURES_PATH = ROOT / SEASON / "ng.1.json"
TEAMS_PATH = ROOT / SEASON / "teams" / "ng.1.teams.json"
SEASONS_PATH = ROOT / "seasons.json"
VALID_STATUSES = {"scheduled", "finished", "postponed", "cancelled"}
MATCH_ID_RE = re.compile(r"^npfl-\d{4}-\d{2}-[a-z0-9-]+-[a-z0-9-]+$")


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing file: {path.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path.relative_to(ROOT)}: {exc}")


def main() -> None:
    fixtures = load_json(FIXTURES_PATH)
    teams_doc = load_json(TEAMS_PATH)
    seasons = load_json(SEASONS_PATH)

    if fixtures.get("season") != SEASON:
        fail(f"fixture season must be {SEASON!r}")
    if not isinstance(fixtures.get("matches"), list):
        fail("matches must be an array")

    teams = teams_doc.get("teams")
    if not isinstance(teams, list):
        fail("teams must be an array")
    if len(teams) != 20:
        fail(f"expected 20 teams, found {len(teams)}")

    team_by_name = {}
    team_by_id = {}
    for team in teams:
        for key in ("id", "name", "code"):
            if not isinstance(team.get(key), str) or not team[key]:
                fail(f"team is missing a valid {key!r}: {team!r}")
        if team["name"] in team_by_name:
            fail(f"duplicate team name: {team['name']}")
        if team["id"] in team_by_id:
            fail(f"duplicate team id: {team['id']}")
        team_by_name[team["name"]] = team["id"]
        team_by_id[team["id"]] = team

    matches = fixtures["matches"]
    if len(matches) != 380:
        fail(f"expected 380 matches, found {len(matches)}")

    ids = set()
    pair_counts = Counter()
    round_counts = Counter()
    home_counts = Counter()
    away_counts = Counter()

    for index, match in enumerate(matches, start=1):
        required = ("round", "date", "time", "team1", "team2", "venue", "status", "score",
                    "id", "home_team_id", "away_team_id")
        missing = [key for key in required if key not in match]
        if missing:
            fail(f"match #{index} missing fields: {', '.join(missing)}")

        if not MATCH_ID_RE.fullmatch(match["id"]):
            fail(f"match #{index} has invalid id: {match['id']!r}")
        if match["id"] in ids:
            fail(f"duplicate match id: {match['id']}")
        ids.add(match["id"])

        if match["team1"] not in team_by_name or match["team2"] not in team_by_name:
            fail(f"match #{index} references an unknown team")
        if match["home_team_id"] != team_by_name[match["team1"]]:
            fail(f"match #{index} home_team_id does not match team1")
        if match["away_team_id"] != team_by_name[match["team2"]]:
            fail(f"match #{index} away_team_id does not match team2")
        if match["home_team_id"] == match["away_team_id"]:
            fail(f"match #{index} has the same home and away team")

        try:
            date.fromisoformat(match["date"])
        except (TypeError, ValueError):
            fail(f"match #{index} has invalid ISO date: {match['date']!r}")

        if match["status"] not in VALID_STATUSES:
            fail(f"match #{index} has invalid status: {match['status']!r}")

        score = match["score"]
        if score is not None:
            if not isinstance(score, dict) or "ft" not in score:
                fail(f"match #{index} score must be null or contain ft")
            ft = score["ft"]
            if (not isinstance(ft, list) or len(ft) != 2 or
                    any(not isinstance(x, int) or isinstance(x, bool) or x < 0 for x in ft)):
                fail(f"match #{index} has invalid ft score")
        if match["status"] == "finished" and score is None:
            fail(f"match #{index} is finished but has no score")

        round_counts[match["round"]] += 1
        pair_counts[(match["home_team_id"], match["away_team_id"])] += 1
        home_counts[match["home_team_id"]] += 1
        away_counts[match["away_team_id"]] += 1

    expected_rounds = {f"Matchday {n}" for n in range(1, 39)}
    if set(round_counts) != expected_rounds:
        fail("round set is not exactly Matchday 1 through Matchday 38")
    if any(count != 10 for count in round_counts.values()):
        fail(f"each matchday must contain 10 matches: {dict(round_counts)}")
    if any(count != 19 for count in home_counts.values()) or any(count != 19 for count in away_counts.values()):
        fail("each team must have 19 home and 19 away fixtures")
    if len(pair_counts) != 380 or any(count != 1 for count in pair_counts.values()):
        fail("home/away fixture pairs are not unique")

    season_entries = seasons.get("seasons", [])
    if not any(s.get("season") == SEASON and s.get("fixtures") == f"{SEASON}/ng.1.json"
               for s in season_entries):
        fail("seasons.json does not reference the 2026-27 fixture file")

    print("OK: NPFL 2026-27 dataset passed validation")
    print(f"  teams: {len(teams)}")
    print(f"  matches: {len(matches)}")
    print(f"  matchdays: {len(round_counts)}")
    print(f"  unique match IDs: {len(ids)}")


if __name__ == "__main__":
    main()
