# Player squad files

One JSON file per club, named by team id (see `../teams/ng.1.teams.json`),
e.g. `rangers-intl.json`, `enyimba.json`.

Not yet populated for 2026/27 — squad lists are added manually as they're
confirmed. Contributions welcome, see [CONTRIBUTING.md](../../CONTRIBUTING.md).

Format:

```json
{
  "team_id": "rangers-intl",
  "team_name": "Rangers Int'l",
  "season": "2026-27",
  "attribution": "https://soccerhub.ng",
  "last_updated": "2026-08-25",
  "players": [
    {
      "id": "rangers-intl-example-player",
      "name": "Example Player",
      "position": "FWD",
      "shirt_number": 9,
      "date_of_birth": null,
      "nationality": "NGA"
    }
  ]
}
```
