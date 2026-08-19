from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

from bs4 import BeautifulSoup

BASE_URL = "https://simulatorgolftour.com"
ROOT = Path(__file__).resolve().parents[1]


def build_opener() -> urllib.request.OpenerDirector:
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (compatible; SGTRecapEngineLab/0.3)"),
        ("Accept-Language", "en-US,en;q=0.9"),
    ]
    return opener


def fetch_text(opener: urllib.request.OpenerDirector, path: str, referer: str) -> str:
    url = f"{BASE_URL}{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html, */*; q=0.01",
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    try:
        with opener.open(request, timeout=30) as response:
            body = response.read()
            if not body.strip():
                raise RuntimeError(f"Empty response from {url}")
            print(f"GET {path}: HTTP {getattr(response, 'status', None)} | {len(body)} bytes")
            return body.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        preview = exc.read()[:500].decode("utf-8", errors="replace")
        print(f"HTTP {exc.code} fetching {url}: {preview!r}", file=sys.stderr)
        raise


def clean_text(node) -> str | None:
    if not node:
        return None
    value = node.get_text(" ", strip=True)
    return value or None


def nearest_player_name(tag) -> str | None:
    direct = clean_text(tag)
    if direct and not direct.isdigit() and len(direct) <= 80:
        return direct

    parent = tag.find_parent("tr")
    if parent is None:
        parent = tag.find_parent(class_=re.compile(r"player|leader|row", re.I))
    if parent:
        profile = parent.find("a", href=re.compile(r"^/profile/"))
        if profile:
            return clean_text(profile)

    return None


def discover_players_from_leaderboard(html: str, tournament_id: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    players: dict[int, dict] = {}
    scorecard_pattern = re.compile(rf"/scorecard/{tournament_id}/(\d+)")

    for link in soup.find_all("a", href=True):
        match = scorecard_pattern.search(link.get("href", ""))
        if not match:
            continue
        player_id = int(match.group(1))
        name = nearest_player_name(link)
        players.setdefault(player_id, {"id": player_id, "name": name})
        if not players[player_id].get("name") and name:
            players[player_id]["name"] = name

    id_attributes = ("data-player-id", "data-playerid", "data-pid", "data-user-id", "data-userid")
    for tag in soup.find_all(True):
        for attr in id_attributes:
            raw = tag.get(attr)
            if not raw or not str(raw).isdigit():
                continue
            player_id = int(raw)
            name = nearest_player_name(tag)
            players.setdefault(player_id, {"id": player_id, "name": name})
            if not players[player_id].get("name") and name:
                players[player_id]["name"] = name

    # Fallback: IDs may appear in non-anchor markup. This still lets the run tell us
    # whether the numeric routing pattern exists, even if a name needs a later parser tweak.
    for match in scorecard_pattern.finditer(html):
        player_id = int(match.group(1))
        players.setdefault(player_id, {"id": player_id, "name": None})

    return list(players.values())


def diagnostic_links(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "score" in href.lower() or "profile" in href.lower() or "player" in href.lower():
            out.append({"href": href, "text": clean_text(link)})
    return out[:250]


def export_tournament(tournament_id: int) -> dict:
    opener = build_opener()
    tournament_url = f"{BASE_URL}/tournament/{tournament_id}"

    with opener.open(tournament_url, timeout=30) as response:
        tournament_page = response.read().decode("utf-8", errors="replace")
        print(f"Tournament page: HTTP {getattr(response, 'status', None)} | {len(tournament_page)} bytes")

    gross_html = fetch_text(opener, f"/sgt-api/leaderboard/{tournament_id}", tournament_url)
    net_html = fetch_text(opener, f"/sgt-api/leaderboard/{tournament_id}/net", tournament_url)

    players = discover_players_from_leaderboard(gross_html, tournament_id)
    if not players:
        players = discover_players_from_leaderboard(net_html, tournament_id)

    if not players:
        debug_dir = ROOT / "data" / "debug" / str(tournament_id)
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / "gross-leaderboard.html").write_text(gross_html, encoding="utf-8")
        (debug_dir / "net-leaderboard.html").write_text(net_html, encoding="utf-8")
        (debug_dir / "leaderboard-links.json").write_text(
            json.dumps({"gross": diagnostic_links(gross_html), "net": diagnostic_links(net_html)}, indent=2) + "\n",
            encoding="utf-8",
        )
        raise RuntimeError(
            "Could not discover player IDs from leaderboard markup. "
            f"Diagnostics written to {debug_dir.relative_to(ROOT)}"
        )

    print(f"Discovered {len(players)} player IDs from leaderboard")

    exported_players = []
    for index, player in enumerate(players, start=1):
        player_id = player["id"]
        print(f"Player {index}/{len(players)}: {player.get('name') or 'unknown'} ({player_id})")
        referer = f"{BASE_URL}/scorecard/{tournament_id}/{player_id}"
        item = {"id": player_id, "name": player.get("name"), "scorecard": None, "stats": None, "shots": None, "errors": {}}

        targets = {
            "scorecard": f"/sgt-api/scorecard/{tournament_id}/{player_id}/indv",
            "stats": f"/sgt-api/scorecard/{tournament_id}/{player_id}/indv/stats",
            "shots": f"/sgt-api/scorecard/{tournament_id}/{player_id}/indv/shots",
        }
        for key, path in targets.items():
            try:
                item[key] = fetch_text(opener, path, referer)
            except Exception as exc:  # preserve the rest of the tournament if one optional feed is missing
                item["errors"][key] = f"{type(exc).__name__}: {exc}"
                print(f"  {key} failed: {exc}", file=sys.stderr)

        exported_players.append(item)

    return {
        "schemaVersion": 1,
        "tournament": {
            "id": tournament_id,
            "url": tournament_url,
        },
        "export": {
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "source": "Simulator Golf Tour",
            "exporterVersion": "lab-0.3",
        },
        "leaderboard": {
            "grossHtml": gross_html,
            "netHtml": net_html,
        },
        "players": exported_players,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a complete SGT tournament package.")
    parser.add_argument("tournament_id", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    data = export_tournament(args.tournament_id)
    output = args.output or Path("data") / "tournaments" / f"{args.tournament_id}.json"
    output = output if output.is_absolute() else ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    with_scorecards = sum(1 for player in data["players"] if player.get("scorecard"))
    with_stats = sum(1 for player in data["players"] if player.get("stats"))
    with_shots = sum(1 for player in data["players"] if player.get("shots"))
    print(
        f"Wrote {output.relative_to(ROOT)} | players={len(data['players'])} "
        f"scorecards={with_scorecards} stats={with_stats} shots={with_shots}"
    )

    if not data["players"] or with_scorecards == 0:
        raise RuntimeError("Exporter did not retrieve any usable player scorecards")


if __name__ == "__main__":
    main()
