"""
bsd_team_aliases.py

SoccerHub.ng data-layer tooling.

Single source of truth mapping this repo's NPFL clubs to SoccerHub Data
Service's team records. Both build_bsd_id_map.py (fixture -> fixture
ID) and sync_team_data.py (team profile enrichment) import this so the
two scripts can never drift out of sync with each other.

BSD_LEAGUE_ID: internal ID for the Nigeria Premier Football League.

TEAM_ALIASES: keyed by this repo's team "id" slug (as used in
2026-27/teams/ng.1.teams.json). Each entry gives:
  - repo_name:   the team1/team2 string as written in ng.1.json fixtures
                 (needed because fixtures reference teams by name, not id)
  - bsd_name:    the team name as returned by the data service
  - bsd_team_id: the data service's internal numeric team ID

Update this table when:
  - A new club is promoted into the league (add a new entry)
  - The data service renames a team in their system (update bsd_name)
  - You discover a team is listed under a different bsd_team_id

Do NOT try to auto-derive this via fuzzy string matching on team names.
NPFL club names collide in confusing ways (e.g. two different "Rangers"
in Nigerian football history, "Int'l" vs "International" vs no suffix)
and a wrong auto-match silently corrupts fixture data. Keep it explicit.
"""

BSD_LEAGUE_ID = 28

TEAM_ALIASES = {
    "abia-warriors":     {"repo_name": "Abia Warriors",   "bsd_name": "Abia Warriors",                 "bsd_team_id": 565},
    "barau":             {"repo_name": "Barau",           "bsd_name": "Barau FC",                       "bsd_team_id": 567},
    "bendel-insurance":  {"repo_name": "Bendel Insurance","bsd_name": "Bendel Insurance FC",             "bsd_team_id": 570},
    "doma-united":       {"repo_name": "Doma United",     "bsd_name": "Doma United FC",                  "bsd_team_id": 5648},
    "enyimba":           {"repo_name": "Enyimba Int'l",   "bsd_name": "Enyimba",                         "bsd_team_id": 568},
    "ikorodu-city":      {"repo_name": "Ikorodu City",    "bsd_name": "Ikorodu City",                    "bsd_team_id": 576},
    "inter-lagos":       {"repo_name": "Inter Lagos",     "bsd_name": "Inter Lagos FC",                  "bsd_team_id": 8255},
    "kano-pillars":      {"repo_name": "Kano Pillars",    "bsd_name": "Kano Pillars",                    "bsd_team_id": 566},
    "katsina-united":    {"repo_name": "Katsina United",  "bsd_name": "Katsina United",                  "bsd_team_id": 573},
    "kun-khalifat":      {"repo_name": "Kun Khalifat",    "bsd_name": "Kun Khalifat FC",                 "bsd_team_id": 572},
    "kwara-united":      {"repo_name": "Kwara United",    "bsd_name": "Kwara United",                    "bsd_team_id": 575},
    "nasarawa-united":   {"repo_name": "Nasarawa United", "bsd_name": "Nasarawa United",                 "bsd_team_id": 582},
    "niger-tornadoes":   {"repo_name": "Niger Tornadoes", "bsd_name": "Niger Tornadoes",                 "bsd_team_id": 581},
    "plateau-united":    {"repo_name": "Plateau United",  "bsd_name": "Plateau United",                  "bsd_team_id": 580},
    "ranchers-bees":     {"repo_name": "Ranchers Bees",   "bsd_name": "Ranchers Bees",                   "bsd_team_id": 8256},
    "rangers-intl":      {"repo_name": "Rangers Int'l",   "bsd_name": "Enugu Rangers International",     "bsd_team_id": 571},
    "rivers-united":     {"repo_name": "Rivers United",   "bsd_name": "Rivers United",                   "bsd_team_id": 564},
    "shooting-stars":    {"repo_name": "Shooting Stars",  "bsd_name": "Shooting Stars",                  "bsd_team_id": 577},
    "sporting-lagos":    {"repo_name": "Sporting Lagos",  "bsd_name": "Sporting Lagos FC",                "bsd_team_id": 5649},
    "warri-wolves":      {"repo_name": "Warri Wolves",    "bsd_name": "Warri Wolves FC",                 "bsd_team_id": 574},
}


def repo_name_to_bsd_name():
    """Convenience lookup: repo fixture team-name string -> BSD team name."""
    return {v["repo_name"]: v["bsd_name"] for v in TEAM_ALIASES.values()}


def repo_name_to_bsd_id():
    """Convenience lookup: repo fixture team-name string -> BSD team id."""
    return {v["repo_name"]: v["bsd_team_id"] for v in TEAM_ALIASES.values()}
