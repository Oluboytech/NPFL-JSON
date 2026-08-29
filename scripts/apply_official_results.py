#!/usr/bin/env python3
"""
apply_official_results.py

SoccerHub.ng data-layer tooling.

Now runs as a second-opinion cross-check on scripts/apply_bsd_results.py
(which writes scores fetched directly from SoccerHub Data Service - see
that script's docstring for the provenance decision behind that). This
script reads from npfl.com.ng - the Nigeria Premier Football League's
own official website, a primary public source - and does two things
with it:

  1. Fill-in: for any fixture still 'scheduled' whose date has passed
     (i.e. apply_bsd_results.py hasn't confirmed a score for it yet -
     no mapping, BSD unreachable, etc.), apply a result from the
     official site directly if one's available there.
  2. Cross-check: for any fixture already 'finished' (i.e. BSD already
     wrote a score), compare it against the official site's score. If
     they disagree, this does NOT overwrite either value - it opens a
     "score-mismatch" issue for a human to resolve, since a disagreement
     could mean a correction, a forfeiture ruling, or an error on
     either side, and guessing which one's right isn't this script's
     call to make.

This is intentionally conservative about what counts as "found": the
Time/Results column on npfl.com.ng shows either a kickoff time (e.g.
"4:00 pm") for future/unplayed matches or a score (e.g. "2 - 1") for
finished ones. A time string always contains ':' or an am/pm marker; a
score is two small integers joined by '-' or a dash-like character with
nothing else around it. Anything that doesn't cleanly match the score
pattern is treated as "not found yet", never guessed at.

Usage (intended to run in GitHub Actions after apply_bsd_results.py,
or standalone on its own schedule):
    export GITHUB_TOKEN=...
    export GITHUB_REPOSITORY=Oluboytech/NPFL-JSON
    python3 scripts/apply_official_results.py

    # Preview without writing or committing:
    python3 scripts/apply_official_results.py --dry-run
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).parent))
from npfl_official_aliases import repo_name_to_official  # noqa: E402

FIXTURES_PATH = Path("2026-27/ng.1.json")
RESULTS_PAGE_URL = "https://npfl.com.ng/fixtures-results/"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")

# A score cell looks like "2 - 1", "2-1", "10 - 2", etc. A time cell
# looks like "4:00 pm", "16:00", "TBD", etc. This pattern only matches
# the score shape - small integers joined by a dash, nothing else.
SCORE_PATTERN = re.compile(r"^\s*(\d{1,2})\s*[-–]\s*(\d{1,2})\s*$")


def fetch_results_page_text() -> str:
    req = Request(RESULTS_PAGE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_official_results(html: str) -> dict:
    """
    Returns {(official_home_name, official_away_name): (home_score, away_score)}
    for every row on the page where the Time/Results column contains a
    parseable score. Rows without a clean score match are simply absent
    from the returned dict - this function never guesses.

    Parsing approach: npfl.com.ng's table rows are plain HTML <tr>/<td>
    with team names as link text and the result/time as a separate link
    text in the next cell. Rather than depend on exact class names
    (which the site doesn't consistently expose and could change),
    this extracts all link text in document order and looks for the
    (home vs away, result-or-time) pairing pattern within each row's
    <tr>...</tr> block.
    """
    results = {}

    row_pattern = re.compile(r"<tr\b.*?>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
    link_text_pattern = re.compile(r"<a\b[^>]*>(.*?)</a>", re.DOTALL | re.IGNORECASE)
    tag_strip = re.compile(r"<[^>]+>")

    for row_match in row_pattern.finditer(html):
        row_html = row_match.group(1)
        link_texts = [
            tag_strip.sub("", t).strip()
            for t in link_text_pattern.findall(row_html)
        ]
        # Filter out empty/whitespace-only link texts (e.g. bare image links)
        link_texts = [t for t in link_texts if t]
        if len(link_texts) < 2:
            continue

        # The match-name link text looks like "Team A vs Team B"; the
        # result/time link text is a separate, shorter link. Find the
        # "X vs Y" one specifically rather than assuming position.
        vs_text = next((t for t in link_texts if " vs " in t), None)
        if not vs_text:
            continue
        home_name, _, away_name = vs_text.partition(" vs ")
        home_name, away_name = home_name.strip(), away_name.strip()
        if not home_name or not away_name:
            continue

        # Look for a score among the OTHER link texts in this row.
        score = None
        for t in link_texts:
            if t == vs_text:
                continue
            m = SCORE_PATTERN.match(t)
            if m:
                score = (int(m.group(1)), int(m.group(2)))
                break

        if score is not None:
            results[(home_name, away_name)] = score

    return results


def gh_request(method, path, body=None):
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urlopen(req, timeout=20) as resp:
        body_bytes = resp.read()
        return json.loads(body_bytes) if body_bytes else None


def open_result_needed_issue(match: dict, reason: str):
    """Same style of issue check_fixture_status.py opens, used here only
    as the fallback when the official-site scrape couldn't confirm a
    score - so a scrape failure is never silent."""
    title = (
        f"Result needed: {match['team1']} vs {match['team2']} "
        f"({match['date']}) [official-site-scrape-miss]"
    )
    body = (
        f"Tried to fetch this result from the official NPFL site "
        f"({RESULTS_PAGE_URL}) but couldn't confirm a score.\n\n"
        f"Reason: {reason}\n\n"
        f"Please confirm the final score from a public source (NPFL's "
        f"own site, official club channels, or news reporting) and "
        f"update `2026-27/ng.1.json` manually:\n\n"
        f"- Set `status` to `finished`\n"
        f"- Set `score.ft` to `[home, away]`\n\n"
        f"Match: {match['team1']} vs {match['team2']}, "
        f"Matchday {match.get('matchday', '?')}, {match['date']}"
    )
    gh_request("POST", "/issues", {
        "title": title,
        "body": body,
        "labels": ["automation", "result-needed"],
    })


def open_score_mismatch_issue(match: dict, bsd_score, official_score):
    """
    Opened when BSD's committed score and npfl.com.ng's score for the
    same fixture disagree. This is treated as a genuine data conflict,
    not resolved automatically in either direction - the two sources
    could differ due to a correction, an admin decision (e.g.
    forfeiture), or an error on either side, and picking one silently
    could paper over something a maintainer actually needs to see.
    """
    title = (
        f"Score mismatch: {match['team1']} vs {match['team2']} "
        f"({match['date']}) [bsd-vs-official-disagree]"
    )
    body = (
        f"SoccerHub Data Service and the official NPFL site "
        f"({RESULTS_PAGE_URL}) disagree on this fixture's result:\n\n"
        f"- BSD (currently committed): **{bsd_score[0]}-{bsd_score[1]}**\n"
        f"- Official site: **{official_score[0]}-{official_score[1]}**\n\n"
        f"Please check a public source and correct `2026-27/ng.1.json` "
        f"manually if needed (`score.ft` under this fixture).\n\n"
        f"Match: {match['team1']} vs {match['team2']}, "
        f"Matchday {match.get('matchday', '?')}, {match['date']}"
    )
    gh_request("POST", "/issues", {
        "title": title,
        "body": body,
        "labels": ["automation", "score-mismatch"],
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                         help="Print what would change without writing or committing.")
    args = parser.parse_args()

    if not FIXTURES_PATH.exists():
        print(f"Fixtures file not found: {FIXTURES_PATH}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(FIXTURES_PATH.read_text())
    matches = data["matches"]

    today = date.today().isoformat()
    past_or_today = [m for m in matches if m.get("date", "9999-99-99") <= today]

    # Two groups get different treatment:
    #  - 'scheduled' fixtures: fill in a result if the official site has
    #    one (this is the original, primary behavior of this script).
    #  - 'finished' fixtures (already written by apply_bsd_results.py):
    #    cross-check against the official site instead of overwriting -
    #    a second opinion, not a second writer.
    scheduled_due = [m for m in past_or_today if m.get("status") == "scheduled"]
    finished_to_verify = [m for m in past_or_today if m.get("status") == "finished"]

    if not scheduled_due and not finished_to_verify:
        print("No fixtures due for a result check.")
        return

    print(f"{len(scheduled_due)} scheduled fixture(s) to fill in, "
          f"{len(finished_to_verify)} finished fixture(s) to cross-check.")

    try:
        html = fetch_results_page_text()
    except (HTTPError, URLError) as e:
        print(f"Could not reach {RESULTS_PAGE_URL}: {e}", file=sys.stderr)
        html = None

    official_results = parse_official_results(html) if html else {}
    print(f"Parsed {len(official_results)} confirmed result(s) from the official site.")

    updated = 0
    issues_opened = 0
    mismatches_flagged = 0

    for m in scheduled_due:
        official_home = repo_name_to_official(m["team1"])
        official_away = repo_name_to_official(m["team2"])

        score = None
        if official_home and official_away:
            score = official_results.get((official_home, official_away))

        if score is not None:
            m["status"] = "finished"
            if not isinstance(m.get("score"), dict):
                m["score"] = {}
            m["score"]["ft"] = list(score)
            updated += 1
            print(f"  \u2713 {m['team1']} {score[0]}-{score[1]} {m['team2']}")
            continue

        # Fallback: couldn't confirm from the official site - flag for a human.
        if not official_home or not official_away:
            reason = "no official-site name alias configured for one or both teams"
        elif html is None:
            reason = "could not reach the official results page"
        else:
            reason = "match not yet showing a result on the official site"

        print(f"  ? {m['team1']} vs {m['team2']}: {reason}")
        if not args.dry_run:
            open_result_needed_issue(m, reason)
            issues_opened += 1

    for m in finished_to_verify:
        official_home = repo_name_to_official(m["team1"])
        official_away = repo_name_to_official(m["team2"])
        if not official_home or not official_away:
            continue  # no alias configured - can't cross-check, stay silent

        official_score = official_results.get((official_home, official_away))
        if official_score is None:
            continue  # official site doesn't have it yet either - nothing to compare

        committed_ft = (m.get("score") or {}).get("ft")
        if not isinstance(committed_ft, list) or len(committed_ft) != 2:
            continue  # malformed/missing committed score - not this script's job to fix

        bsd_score = tuple(committed_ft)
        if bsd_score == tuple(official_score):
            print(f"  = {m['team1']} vs {m['team2']}: confirmed, both sources agree "
                  f"({bsd_score[0]}-{bsd_score[1]})")
            continue

        print(f"  \u26a0 {m['team1']} vs {m['team2']}: MISMATCH - "
              f"BSD says {bsd_score[0]}-{bsd_score[1]}, "
              f"official site says {official_score[0]}-{official_score[1]}")
        mismatches_flagged += 1
        if not args.dry_run:
            open_score_mismatch_issue(m, bsd_score, official_score)
            issues_opened += 1

    print(f"\n{updated} result(s) filled in, {mismatches_flagged} mismatch(es) flagged, "
          f"{issues_opened} issue(s) opened total.")

    if updated == 0:
        return

    if args.dry_run:
        print("--dry-run: not writing ng.1.json or committing.")
        return

    FIXTURES_PATH.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Updated {FIXTURES_PATH}")


if __name__ == "__main__":
    main()
