# Fixture ID mapping (local only — never commit)

`check_fixture_status.py` needs a way to know which internal fixture ID
(from SoccerHub Data Service) corresponds to which row in
`2026-27/ng.1.json`, so it can ask "is this match finished yet?"

This mapping is **not** committed to the public repo — it's an internal
detail of SoccerHub's own data pipeline, and keeping it out of
`ng.1.json` avoids tying internal identifiers to a public,
redistributable dataset.

## Format

`.automation/bsd_id_map.json` (gitignored) looks like:

```json
{
  "2026-08-28:Shooting Stars:Inter Lagos": "bsd-fixture-id-123",
  "2026-08-30:Ikorodu City:Ranchers Bees": "bsd-fixture-id-124"
}
```

Key format: `"<date>:<team1>:<team2>"`, matching exactly what's in
`ng.1.json`.

## How to populate it — `scripts/build_bsd_id_map.py`

Run this locally whenever new fixtures have been loaded (only the next
round or two tend to be available at a time, not the full season in
advance):

```bash
export BSD_API_KEY=...
export BSD_API_BASE_URL=...

# See what would match without writing anything:
python3 scripts/build_bsd_id_map.py --dry-run

# Write .automation/bsd_id_map.json (overwrites):
python3 scripts/build_bsd_id_map.py

# Merge new matches into the existing file instead of overwriting:
python3 scripts/build_bsd_id_map.py --merge
```

It matches fixtures by `(date, home team, away team)` using the alias
table in `scripts/bsd_team_aliases.py` — NOT fuzzy string matching,
since NPFL team-name variants (`Enyimba` vs `Enyimba Int'l`, `Rangers
Int'l` vs `Enugu Rangers International`) are too easy to mismatch
automatically. If a new club is promoted or a team's listed name
changes, add/update its entry in that file.

## Getting BSD_API_KEY / BSD_API_BASE_URL

These are SoccerHub's own credentials for its data pipeline (the same
ones already used elsewhere in SoccerHub/NAM's integration, e.g.
`bsd-api.php`) — reuse them here rather than provisioning new ones.

## Turning the mapping into the BSD_ID_MAP_JSON secret

`BSD_ID_MAP_JSON` is not something you fetch from anywhere directly —
it's the *output* of the step above, pasted into a repo secret so CI
can use it without committing it to git:

1. Run `python3 scripts/build_bsd_id_map.py` (see above). This writes
   `.automation/bsd_id_map.json`.
2. Copy that file's entire contents.
3. In the repo: **Settings → Secrets and variables → Actions → New
   repository secret**, name it `BSD_ID_MAP_JSON`, and paste the JSON
   in as the value.
4. Re-run steps 1–3 whenever fresh fixtures are matched (weekly is
   reasonable) to keep the secret current. `--merge` lets you fold new
   matches into what's already there instead of starting over.

It's fine — expected, even — for the mapping to only cover a subset of
the season's fixtures at any given time; `check_fixture_status.py`
silently skips fixtures with no mapping yet.

## Team data enrichment — `scripts/sync_team_data.py`

Separately, `2026-27/teams/ng.1.teams.json` can be enriched with a
small amount of public-safe data (each team's `bsd_team_id` and
`current_coach`):

```bash
export BSD_API_KEY=...
export BSD_API_BASE_URL=...
python3 scripts/sync_team_data.py --dry-run   # preview
python3 scripts/sync_team_data.py             # write
```

This deliberately publishes **only** id/name/coach-name/venue-name —
never squad lists, injury status, tactical profiles, or anything
odds-derived. See the docstring in that script for the full rationale;
it follows the same "internal input, not a redistributed data source"
principle as the fixture-status checker. Your existing hand-entered
fields (stadium, notes, etc.) always take priority — the sync only
fills gaps.

## Where this lives in CI

The scheduled workflow (`.github/workflows/check-fixture-status.yml`)
writes the `BSD_ID_MAP_JSON` secret to `.automation/bsd_id_map.json` at
the start of each run:

```yaml
- name: Write fixture ID mapping from secret
  run: echo '${{ secrets.BSD_ID_MAP_JSON }}' > .automation/bsd_id_map.json
```

This keeps the mapping out of git history entirely while still making it
available to the script at runtime.

`scripts/build_bsd_id_map.py` and `scripts/sync_team_data.py` are
**local, manually-run tools** — not part of the scheduled CI workflow.
Re-run them yourself and update the secret / commit the refreshed teams
file as needed.
