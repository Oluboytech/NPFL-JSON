#!/usr/bin/env python3
"""
sync_bsd_id_map_secret.py

SoccerHub.ng data-layer tooling.

CI counterpart to running `build_bsd_id_map.py --merge` by hand: builds
the fixture ID mapping the same way, then — instead of just writing a
local file — pushes the result straight to the BSD_ID_MAP_JSON repo
secret via the GitHub REST API, so the weekly refresh needs no human
in the loop.

Why this needs its own token: GITHUB_TOKEN (the one Actions injects
automatically) cannot read or write repo secrets — that's a deliberate
GitHub restriction, not an oversight. This script instead expects a
separate PAT (see REPO_ADMIN_TOKEN below) with just enough scope to
manage this one repo's Actions secrets.

Encryption: GitHub requires secret values to be sealed with the repo's
current public key (libsodium sealed box) before they're PUT to the
API — sending plaintext is rejected. This uses PyNaCl for that step.

Usage (intended to run inside GitHub Actions, not locally):
    export BSD_API_KEY=...
    export BSD_API_BASE_URL=...
    export REPO_ADMIN_TOKEN=...      # fine-grained PAT, secrets: write
    export GITHUB_REPOSITORY=Oluboytech/NPFL-JSON
    python3 scripts/sync_bsd_id_map_secret.py

Exits 0 with a clear message and no error if the mapping didn't
change since last run - this keeps scheduled runs quiet by default.
Use --always-update to force a write even with no changes (mainly
useful for testing the secret-write path itself).
"""

import argparse
import base64
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).parent))
from bsd_team_aliases import BSD_LEAGUE_ID, repo_name_to_bsd_name  # noqa: E402

try:
    from nacl import encoding, public
except ImportError:
    print("PyNaCl is required: pip install pynacl", file=sys.stderr)
    sys.exit(1)

FIXTURES_PATH = Path("2026-27/ng.1.json")
LOCAL_CACHE_PATH = Path(".automation/bsd_id_map.json")  # gitignored, CI-local only

BSD_API_KEY = os.environ.get("BSD_API_KEY")
BSD_API_BASE_URL = os.environ.get("BSD_API_BASE_URL", "").rstrip("/")
REPO_ADMIN_TOKEN = os.environ.get("REPO_ADMIN_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")  # "owner/repo"
SECRET_NAME = "BSD_ID_MAP_JSON"

LOOKAHEAD_DAYS = 120


# ---- fetch + match (same logic as build_bsd_id_map.py) --------------------

def fetch_bsd_matches():
    if not BSD_API_KEY or not BSD_API_BASE_URL:
        print("BSD_API_KEY / BSD_API_BASE_URL not set.", file=sys.stderr)
        sys.exit(1)

    date_from = date.today().isoformat()
    date_to = (date.today() + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
    url = (
        f"{BSD_API_BASE_URL}/events/"
        f"?league_id={BSD_LEAGUE_ID}&date_from={date_from}&date_to={date_to}"
    )
    req = Request(url, headers={"Authorization": f"Token {BSD_API_KEY}"})

    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read())
    except (HTTPError, URLError) as e:
        print(f"Failed to reach SoccerHub Data Service: {e}", file=sys.stderr)
        sys.exit(1)

    if isinstance(payload, dict):
        return payload.get("events") or payload.get("results") or []
    return payload


def build_mapping(fixtures, bsd_matches):
    name_lookup = repo_name_to_bsd_name()
    bsd_by_key = {}
    for m in bsd_matches:
        bsd_date = m["event_date"][:10]
        bsd_by_key[(bsd_date, m["home_team"], m["away_team"])] = m["id"]

    mapping = {}
    for fx in fixtures:
        repo_key = f"{fx['date']}:{fx['team1']}:{fx['team2']}"
        bsd_home = name_lookup.get(fx["team1"])
        bsd_away = name_lookup.get(fx["team2"])
        if not bsd_home or not bsd_away:
            continue
        bsd_id = bsd_by_key.get((fx["date"], bsd_home, bsd_away))
        if bsd_id is None:
            continue
        mapping[repo_key] = f"bsd-{bsd_id}"

    return mapping


# ---- GitHub secret API -----------------------------------------------------

def gh_request(method, path, body=None):
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {REPO_ADMIN_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urlopen(req, timeout=20) as resp:
            body_bytes = resp.read()
            return json.loads(body_bytes) if body_bytes else None
    except HTTPError as e:
        detail = e.read().decode(errors="replace")
        print(f"GitHub API {method} {path} failed: {e.code} {detail}", file=sys.stderr)
        sys.exit(1)


def get_repo_public_key():
    return gh_request("GET", "/actions/secrets/public-key")


def encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    """Seal secret_value for GitHub's Actions secret store using the
    repo's current public key. Returns a base64 string ready for the
    encrypted_value field of the create/update-secret API call."""
    pk = public.PublicKey(public_key_b64.encode(), encoding.Base64Encoder())
    box = public.SealedBox(pk)
    sealed = box.encrypt(secret_value.encode())
    return base64.b64encode(sealed).decode()


def push_secret(mapping: dict):
    key_info = get_repo_public_key()
    encrypted = encrypt_secret(key_info["key"], json.dumps(mapping, sort_keys=True))
    gh_request("PUT", f"/actions/secrets/{SECRET_NAME}", {
        "encrypted_value": encrypted,
        "key_id": key_info["key_id"],
    })


# ---- current secret snapshot, so we only write when something changed ----

def get_existing_mapping_from_local_cache():
    """
    GitHub's secrets API never lets you read a secret's value back, so we
    can't diff against "what's live" directly. Instead this relies on the
    same restored-from-secret file the check-fixture-status workflow
    already writes at the start of its run (.automation/bsd_id_map.json,
    gitignored) — if this workflow runs after that file's been restored
    in the same job, we can diff against it. If it's not present, this
    just treats it as an empty starting point and pushes whatever's
    matched now.
    """
    if LOCAL_CACHE_PATH.exists():
        try:
            return json.loads(LOCAL_CACHE_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--always-update", action="store_true",
                         help="Push to the secret even if the mapping is unchanged.")
    args = parser.parse_args()

    if not REPO_ADMIN_TOKEN:
        print("REPO_ADMIN_TOKEN not set - can't update the repo secret.", file=sys.stderr)
        sys.exit(1)
    if not GITHUB_REPOSITORY:
        print("GITHUB_REPOSITORY not set.", file=sys.stderr)
        sys.exit(1)
    if not FIXTURES_PATH.exists():
        print(f"Fixtures file not found: {FIXTURES_PATH}", file=sys.stderr)
        sys.exit(1)

    fixtures = json.loads(FIXTURES_PATH.read_text())["matches"]
    bsd_matches = fetch_bsd_matches()
    new_mapping = build_mapping(fixtures, bsd_matches)

    if not new_mapping:
        print("No fixtures matched this run - leaving the existing secret untouched.")
        return

    existing_mapping = get_existing_mapping_from_local_cache()
    merged = {**existing_mapping, **new_mapping}

    added = set(new_mapping) - set(existing_mapping)
    changed = {k for k in new_mapping if k in existing_mapping and existing_mapping[k] != new_mapping[k]}

    print(f"SoccerHub Data Service returned {len(bsd_matches)} fixture(s) for league {BSD_LEAGUE_ID}.")
    print(f"Matched {len(new_mapping)} / {len(fixtures)} repo fixtures this run "
          f"({len(added)} new, {len(changed)} changed).")
    print(f"Mapping would total {len(merged)} entries after merge.")

    if not added and not changed and not args.always_update:
        print("No changes since the currently cached mapping - not touching the secret.")
        return

    push_secret(merged)
    print(f"Updated {SECRET_NAME} secret with {len(merged)} total mapping(s).")


if __name__ == "__main__":
    main()
