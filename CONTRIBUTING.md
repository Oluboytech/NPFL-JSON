# Contributing

Corrections and additions are welcome — this is community-checkable data.

## What to contribute

- Fixed fixture dates/times (schedule changes happen often in NPFL)
- Final scores for matches marked `"status": "scheduled"` that have
  actually been played
- Missing or incorrect team info (stadium, city, state, code)
- Missing or incorrect player info (name, position, shirt number)
- New season folders once fixtures are officially released

## How to contribute

1. Fork the repo
2. Edit the relevant JSON file directly — keep the existing structure and
   key names
3. Validate your JSON (e.g. `python3 -m json.tool yourfile.json`) before
   committing
4. Open a pull request with a short description and, where possible, a
   source link (official NPFL site, a news report, etc.)

## Guidelines

- Don't remove or alter the `attribution` field in any file
- Match `team1`/`team2` names to the exact spelling used in
  `teams/ng.1.teams.json`
- Use `null`, not `"TBD"` or empty strings, for unknown values
- One pull request per logical change is easier to review than one giant
  PR touching everything

## Data provenance

If you're adding a new season, note in your PR where the fixture list came
from (ideally the official NPFL calendar) so we're not accidentally
pulling from a licensed feed.
