from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]


def text(node) -> str | None:
    if not node:
        return None
    value = node.get_text(" ", strip=True)
    return value or None


def as_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"-?\d+", value.replace(",", ""))
    return int(match.group()) if match else None


def as_float(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group()) if match else None


def display_to_par(value: int | None) -> str | None:
    if value is None:
        return None
    if value == 0:
        return "E"
    return f"+{value}" if value > 0 else str(value)


def parse_scorecard(html: str | None) -> dict:
    if not html:
        return {"rounds": [], "complete": False}
    soup = BeautifulSoup(html, "html.parser")
    rounds = []
    all_holes = []

    for round_index, table in enumerate(soup.select("table.scorecard-table"), start=1):
        hole_row = table.select_one("tr.hole-row")
        par_row = table.select_one("tr.par-row")
        score_rows = table.select("tr.score-row")
        if not hole_row or not par_row:
            continue

        labels = [text(cell) for cell in hole_row.find_all("td")][1:]
        pars = [as_int(text(cell)) for cell in par_row.find_all("td")][1:]
        gross_values = None
        net_values = None
        for row in score_rows:
            cells = row.find_all("td")
            if not cells:
                continue
            label = (text(cells[0]) or "").upper()
            values = [as_int(text(cell)) for cell in cells][1:]
            if label == "GROSS":
                gross_values = values
            elif label == "NET":
                net_values = values

        holes = []
        for idx, label in enumerate(labels):
            if not label or not label.isdigit():
                continue
            hole = int(label)
            par = pars[idx] if idx < len(pars) else None
            gross = gross_values[idx] if gross_values and idx < len(gross_values) else None
            net = net_values[idx] if net_values and idx < len(net_values) else None
            item = {
                "round": round_index,
                "hole": hole,
                "par": par,
                "gross": gross,
                "net": net,
                "grossToPar": gross - par if gross is not None and par is not None else None,
                "netToPar": net - par if net is not None and par is not None else None,
            }
            holes.append(item)
            all_holes.append(item)

        complete = len(holes) == 18 and all(hole["gross"] is not None for hole in holes)
        rounds.append({
            "round": round_index,
            "complete": complete,
            "par": sum(hole["par"] for hole in holes if hole["par"] is not None),
            "gross": sum(hole["gross"] for hole in holes if hole["gross"] is not None),
            "net": sum(hole["net"] for hole in holes if hole["net"] is not None) if any(hole["net"] is not None for hole in holes) else None,
            "holes": holes,
        })

    complete_rounds = [round_ for round_ in rounds if round_["complete"]]
    par_total = sum(round_["par"] for round_ in complete_rounds)
    gross_total = sum(round_["gross"] for round_ in complete_rounds)
    net_total = sum(round_["net"] for round_ in complete_rounds if round_["net"] is not None) if complete_rounds else None
    gross_to_par = gross_total - par_total if complete_rounds else None
    net_to_par = net_total - par_total if net_total is not None and complete_rounds else None

    return {
        "rounds": rounds,
        "holes": all_holes,
        "complete": bool(rounds) and len(complete_rounds) == len(rounds),
        "par": par_total if complete_rounds else None,
        "gross": gross_total if complete_rounds else None,
        "net": net_total,
        "grossToPar": gross_to_par,
        "netToPar": net_to_par,
        "grossDisplay": display_to_par(gross_to_par),
        "netDisplay": display_to_par(net_to_par),
    }


def player_stat_value(cell) -> str | None:
    wrapper = cell.find("div", class_=lambda value: value and "d-flex" in value and "flex-row" in value)
    if wrapper:
        direct = wrapper.find_all("div", recursive=False)
        if direct:
            return text(direct[0])
    return text(cell)


def parse_stats(html: str | None) -> dict:
    if not html:
        return {"all": {}, "sg": {}}
    soup = BeautifulSoup(html, "html.parser")
    stats = {}
    for row in soup.select("table.stats-table tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        label = text(cells[0])
        if not label:
            continue
        stats[label.upper()] = player_stat_value(cells[1])

    def sg_value(*needles: str) -> float | None:
        for label, value in stats.items():
            normalized = label.replace("-", " ")
            if all(needle in normalized for needle in needles):
                return as_float(value)
        return None

    sg = {
        "tee": sg_value("TEE", "STROKES GAINED"),
        "approach": sg_value("APPROACH", "STROKES GAINED"),
        "shortGame": sg_value("SHORT", "STROKES GAINED"),
        "putting": sg_value("PUTTING", "STROKES GAINED"),
        "teeToGreen": sg_value("TEE TO GREEN", "STROKES GAINED"),
        "total": sg_value("TOTAL", "STROKES GAINED"),
    }
    return {"all": stats, "sg": sg}


def parse_shots(html: str | None) -> list[dict]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    rounds = []
    headings = soup.find_all("h2")
    for heading in headings:
        match = re.search(r"ROUND\s+(\d+)", (text(heading) or "").upper())
        if not match:
            continue
        round_no = int(match.group(1))
        container = heading.find_next_sibling("div")
        if not container:
            continue
        for card in container.find_all(attrs={"data-hole": True}):
            hole = as_int(str(card.get("data-hole")))
            if hole is None:
                continue
            shots = []
            for number_node in card.select(".shot-number"):
                number = as_int(text(number_node))
                parent = number_node.parent
                description_node = parent.find("div", class_=lambda value: value and "ms-2" in value) if parent else None
                shots.append({"number": number, "description": text(description_node)})
            rounds.append({"round": round_no, "hole": hole, "shots": shots})
    return rounds


def absurdity_score(shots: list[dict]) -> int:
    score = 0
    keywords = {
        "penalty": 5,
        "shank": 5,
        "ob": 5,
        "hazard": 4,
        "water": 4,
        "sand": 2,
        "bunker": 2,
        "rough": 1,
        "0 yds": 5,
        "1 yds": 3,
    }
    for shot in shots:
        description = (shot.get("description") or "").lower()
        score += sum(weight for keyword, weight in keywords.items() if keyword in description)
    score += max(0, len(shots) - 5)
    return score


def tournament_metadata(page_html: str | None, tournament_id: int) -> dict:
    soup = BeautifulSoup(page_html or "", "html.parser")
    h1 = soup.find("h1")
    return {"id": tournament_id, "name": text(h1)}


def analyze(raw: dict) -> dict:
    tournament_id = int(raw["tournament"]["id"])
    gross_order = raw.get("leaderboard", {}).get("grossOrder", [])
    net_order = raw.get("leaderboard", {}).get("netOrder", [])
    gross_position = {item["id"]: index + 1 for index, item in enumerate(gross_order)}
    net_position = {item["id"]: index + 1 for index, item in enumerate(net_order)}

    shot_lookup = {}
    analyzed_players = []
    for raw_player in raw.get("players", []):
        player_id = raw_player["id"]
        scorecard = parse_scorecard(raw_player.get("scorecard"))
        stats = parse_stats(raw_player.get("stats"))
        shots = parse_shots(raw_player.get("shots"))
        for item in shots:
            shot_lookup[(player_id, item["round"], item["hole"])] = item["shots"]

        worst_candidates = [hole for hole in scorecard.get("holes", []) if hole.get("grossToPar") is not None]
        for hole in worst_candidates:
            hole_shots = shot_lookup.get((player_id, hole["round"], hole["hole"]), [])
            hole["shots"] = hole_shots
            hole["shotAbsurdity"] = absurdity_score(hole_shots)
        worst = max(worst_candidates, key=lambda hole: (hole["grossToPar"], hole["shotAbsurdity"]), default=None)

        analyzed_players.append({
            "id": player_id,
            "name": raw_player.get("name"),
            "completed": scorecard.get("complete", False),
            "leaderboard": {
                "grossPosition": gross_position.get(player_id),
                "netPosition": net_position.get(player_id),
                "grossTotal": scorecard.get("grossDisplay"),
                "netTotal": scorecard.get("netDisplay"),
                "netAdjustment": (scorecard.get("grossToPar") - scorecard.get("netToPar")) if scorecard.get("grossToPar") is not None and scorecard.get("netToPar") is not None else None,
            },
            "scorecard": scorecard,
            "sg": stats["sg"],
            "stats": stats["all"],
            "worstHole": worst,
            "sourceErrors": raw_player.get("errors", {}),
        })

    player_by_id = {player["id"]: player for player in analyzed_players}
    completed_ids = {player["id"] for player in analyzed_players if player["completed"]}

    def standings(order: list[dict], kind: str) -> list[dict]:
        result = []
        for index, order_item in enumerate(order, start=1):
            player = player_by_id.get(order_item["id"])
            if not player or player["id"] not in completed_ids:
                continue
            result.append({
                "position": index,
                "id": player["id"],
                "name": player["name"] or order_item.get("name"),
                "total": player["leaderboard"][f"{kind}Total"],
                "netAdjustment": player["leaderboard"].get("netAdjustment") if kind == "net" else None,
            })
        return result

    gross = standings(gross_order, "gross")
    net = standings(net_order, "net")
    carnage = [
        {
            "name": player["name"],
            "id": player["id"],
            **player["worstHole"],
        }
        for player in analyzed_players
        if player["completed"] and player.get("worstHole")
    ]
    carnage.sort(key=lambda item: (item["grossToPar"], item["shotAbsurdity"]), reverse=True)

    return {
        "schemaVersion": 1,
        "tournament": tournament_metadata(raw.get("tournament", {}).get("pageHtml"), tournament_id),
        "leaderboard": {"gross": gross, "net": net},
        "winners": {
            "net": net[0] if net else None,
            "gross": gross[0] if gross else None,
        },
        "players": sorted(analyzed_players, key=lambda player: player["leaderboard"].get("netPosition") or 9999),
        "carnage": carnage,
        "validation": {
            "rawPlayers": len(raw.get("players", [])),
            "completedPlayers": len(completed_ids),
            "playersWithStats": sum(1 for player in analyzed_players if any(value is not None for value in player["sg"].values())),
            "playersWithShots": sum(1 for player in analyzed_players if player.get("worstHole") and player["worstHole"].get("shots")),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic facts from an SGT tournament export.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expect-net-winner")
    parser.add_argument("--expect-gross-winner")
    args = parser.parse_args()

    input_path = args.input if args.input.is_absolute() else ROOT / args.input
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    result = analyze(raw)
    output = args.output or Path("data") / "analysis" / f"{raw['tournament']['id']}.json"
    output = output if output.is_absolute() else ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    net_winner = (result.get("winners", {}).get("net") or {}).get("name")
    gross_winner = (result.get("winners", {}).get("gross") or {}).get("name")
    print(f"Net winner: {net_winner} | Gross winner: {gross_winner}")
    print(json.dumps(result["validation"], indent=2))

    if args.expect_net_winner and net_winner != args.expect_net_winner:
        raise RuntimeError(f"Expected net winner {args.expect_net_winner!r}, got {net_winner!r}")
    if args.expect_gross_winner and gross_winner != args.expect_gross_winner:
        raise RuntimeError(f"Expected gross winner {args.expect_gross_winner!r}, got {gross_winner!r}")
    if result["validation"]["completedPlayers"] == 0:
        raise RuntimeError("No completed player scorecards were parsed")
    if not result["carnage"]:
        raise RuntimeError("No worst-hole facts were produced")


if __name__ == "__main__":
    main()
