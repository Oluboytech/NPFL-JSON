# Changelog

## Unreleased

### Added
- Added stable `id` fields to all 2026/27 match records.
- Added `home_team_id` and `away_team_id` references to all 2026/27 match records.
- Added JSON Schema documentation for match and team records under `schemas/`.
- Added a dependency-free dataset validator at `scripts/validate_data.py`.
- Added GitHub Actions validation for pushes and pull requests.

### Compatibility
- Existing `round`, `date`, `time`, `team1`, `team2`, `venue`, `status`, and `score` fields are unchanged.
- Existing result tooling continues to identify fixtures by date and team names.
- No player, venue, score, or schedule facts were invented or inferred.

### Documentation
- Documented the new stable match/team identifiers in the README.
- Corrected the README's player-data description to reflect the current repository state.
- Added validation instructions and schema documentation.
- Corrected the README raw-data URL and repository name.
