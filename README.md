# NPFL-JSON

Free, open Nigeria Premier Football League (NPFL) data — fixtures, results,
teams, and players — in JSON. No API key required.

Maintained by [SoccerHub](https://soccerhub.ng), a Nigerian football app for
Android. Base fixture data is compiled from the official NPFL season
schedule and kept up to date manually as results and schedule changes come
in.

Currently covers the **2026/27 season** — all 380 matches (20 clubs, 38
matchdays, double round-robin), sourced from the NPFL's official published
fixture list.

## ⚠️ Attribution required — please read [LICENSE.md](LICENSE.md)

This data is free to use in any project, commercial or not, **on the
condition that you credit SoccerHub with a visible, dofollow link** back to
`https://soccerhub.ng` anywhere the data (or data derived from it) is shown
to users. Full terms are in [LICENSE.md](LICENSE.md) — it's short, please
read it before shipping.

Minimum credit line:

```
Data provided by SoccerHub (https://soccerhub.ng)
```

## Structure

```
2026-27/
  ng.1.json              # fixtures & results, NPFL top flight
  teams/
    ng.1.teams.json       # club info: stadium, city, state, code
  players/
    <team-id>.json         # squad list per club (added as confirmed)
```

Each season gets its own folder, following the same pattern as
[openfootball/football.json](https://github.com/openfootball/football.json),
e.g. `2027-28/ng.1.json` once that season starts.

**Known gaps in the source data**, carried through as-is rather than
guessed at:
- Several venues are listed as `TBA` in the official fixture list (mostly
  Doma United and Niger Tornadoes home fixtures) — represented as `null`
  here until confirmed.
- The league has a mid-season transfer window / break (31 Dec 2026 – 7 Jan
  2027) between Matchday 19 and 20.
- Per the NPFL's own fixture list: *"The NPFL may adjust the dates and
  time of match fixtures due to TV and broadcast convenience"* — treat
  dates/times as provisional until closer to matchday, and check
  `last_updated` at the top of `ng.1.json`.

## Fixtures & results — `ng.1.json`

```json
{
  "name": "NPFL 2026/27",
  "season": "2026-27",
  "matches": [
    {
      "round": "Matchday 1",
      "date": "2026-08-28",
      "time": "4:00PM",
      "team1": "Shooting Stars",
      "team2": "Inter Lagos",
      "venue": "Ibadan",
      "status": "scheduled",
      "score": null,
      "id": "npfl-2026-27-shooting-stars-inter-lagos",
      "home_team_id": "shooting-stars",
      "away_team_id": "inter-lagos"
    }
  ]
}
```

- `status`: `"scheduled"` | `"finished"` | `"postponed"` | `"cancelled"`
- `score`: `null` until played, then `{ "ft": [home, away] }` (matches the
  openfootball convention, so existing parsers built for that format work
  with minimal changes)
- `id`: stable NPFL match identifier derived from the season and home/away
  team IDs.
- `home_team_id` / `away_team_id`: references to the stable IDs in
  `teams/ng.1.teams.json`. Existing `team1` / `team2` fields remain unchanged
  for compatibility.

## Teams — `teams/ng.1.teams.json`

Club metadata: id, name, short code, stadium, city, state. Match records now
reference these stable team IDs without removing the existing team-name fields.

## Players — `players/<team-id>.json`

One file per club. Squad data is added only when confirmed; the repository
currently contains the player-directory scaffold, not fabricated player records.

## Using the data

Raw files can be fetched directly via GitHub's raw content URLs, e.g.:

```
https://raw.githubusercontent.com/Oluboytech/NPFL-JSON/main/2026-27/ng.1.json
```

## How this data is put together

- **Fixtures skeleton**: sourced from the NPFL's official published season
  calendar.
- **Results & schedule changes**: updated manually, cross-checked against
  live sports data as matches are played.
- **Teams & players**: compiled manually from public club information.

This repo does not redistribute any third-party licensed data feed — only
publicly available match schedules, results, and club/player facts.

## Validation

Run the dependency-free validator before committing data changes:

```bash
python3 scripts/validate_data.py
```

It checks JSON validity, team references, stable match IDs, fixture integrity,
matchday counts, and the existing result/status rules. It does not rewrite data.
GitHub Actions runs the same validation on pushes and pull requests.

## Contributing

Spotted a wrong score, missing fixture, or outdated squad list? Open an
issue or pull request — corrections are welcome.

## Automated fixture-status checking

This repo includes an optional GitHub Action
(`.github/workflows/check-fixture-status.yml`) that polls a licensed
sports data feed to detect when a fixture has finished or been
postponed — **but it never writes that feed's data into this repo.**

Instead, it opens a GitHub issue asking a maintainer to confirm the
result from a public source and enter it manually. This keeps the
distinction clear between "a signal that tells us to go check" and "data
we're republishing" — the latter would violate the data provider's
license; the former doesn't touch it. See
[`scripts/check_fixture_status.py`](scripts/check_fixture_status.py) for
the full rationale and [`.automation/README.md`](.automation/README.md)
for setup.

This automation is internal to SoccerHub's maintenance workflow — you
don't need it to use or fork this data.

### Recording a confirmed result

Once you've verified a result from a public source, use
[`scripts/record_result.py`](scripts/record_result.py) instead of
hand-editing the JSON:

```bash
# Interactive (prompts for date, teams, score)
python3 scripts/record_result.py

# Or non-interactive
python3 scripts/record_result.py \
  --date 2026-08-28 --team1 "Shooting Stars" --team2 "Inter Lagos" \
  --home-score 2 --away-score 1 --status finished
```

It refuses to write anything if the date+teams don't match exactly one
fixture, shows a before/after diff before saving, and validates the file
stays well-formed JSON with the same match count — so a typo can't
silently corrupt the file for everyone using this data.

It also handles schedule changes (`--new-date`, `--new-time`,
`--new-venue`) for the fixtures still marked `TBA` in the source PDF.

## License

[Custom attribution license](LICENSE.md) — free to use, credit required.
Not CC0 / public domain. Please don't strip attribution before
redistributing.

## Disclaimer

SoccerHub is not affiliated with or an official data provider of the
Nigeria Premier Football League. Data is provided on a best-effort basis.
