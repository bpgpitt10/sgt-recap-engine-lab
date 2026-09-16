from pathlib import Path

# Patch exporter: capture official SGT row completion/total metadata and only fetch finished players.
path = Path('src/export_tournament.py')
text = path.read_text()

needle = '''def discover_players_from_leaderboard(html: str, tournament_id: int) -> list[dict]:\n    """Return players in the exact order SGT renders the leaderboard."""'''
replacement = '''def leaderboard_row_metadata(row) -> dict:\n    classes = set(row.get("class") or []) if row else set()\n    total_node = row.select_one("td.total") if row else None\n    finished_position = row.select_one("td.finished-only-position") if row else None\n    live_position = row.select_one("td.live-position") if row else None\n    return {\n        "finished": "finished-card" in classes,\n        "statusClass": next((value for value in ("finished-card", "in-progress-card") if value in classes), None),\n        "position": clean_text(finished_position) or clean_text(live_position),\n        "total": clean_text(total_node),\n    }\n\n\ndef discover_players_from_leaderboard(html: str, tournament_id: int) -> list[dict]:\n    """Return players in the exact order SGT renders the leaderboard, with official row status."""'''
if needle not in text:
    raise SystemExit('exporter: discover function marker not found')
text = text.replace(needle, replacement, 1)

old = '''        player_id = int(match.group(1))\n        name = nearest_player_name(link)\n        players.setdefault(player_id, {"id": player_id, "name": name})\n        if not players[player_id].get("name") and name:\n            players[player_id]["name"] = name'''
new = '''        player_id = int(match.group(1))\n        name = nearest_player_name(link)\n        row = link.find_parent("tr")\n        metadata = leaderboard_row_metadata(row)\n        players.setdefault(player_id, {"id": player_id, "name": name, **metadata})\n        if not players[player_id].get("name") and name:\n            players[player_id]["name"] = name\n        if row:\n            players[player_id].update(metadata)'''
if old not in text:
    raise SystemExit('exporter: anchor loop not found')
text = text.replace(old, new, 1)

old = '''def merge_orders(gross_order: list[dict], net_order: list[dict]) -> list[dict]:\n    merged: dict[int, dict] = {}\n    for item in gross_order + net_order:\n        player_id = item["id"]\n        merged.setdefault(player_id, {"id": player_id, "name": item.get("name")})\n        if not merged[player_id].get("name") and item.get("name"):\n            merged[player_id]["name"] = item["name"]\n    return list(merged.values())'''
new = '''def merge_orders(gross_order: list[dict], net_order: list[dict]) -> list[dict]:\n    merged: dict[int, dict] = {}\n    for item in gross_order + net_order:\n        player_id = item["id"]\n        merged.setdefault(player_id, {"id": player_id, "name": item.get("name")})\n        if not merged[player_id].get("name") and item.get("name"):\n            merged[player_id]["name"] = item["name"]\n\n    # Completed recaps only need official finishers. If SGT row-status metadata is\n    # unavailable after a future markup change, preserve the legacy all-player fallback.\n    status_entries = [item for item in gross_order + net_order if "finished" in item]\n    finished_ids = {item["id"] for item in status_entries if item.get("finished")}\n    if status_entries and finished_ids:\n        return [item for player_id, item in merged.items() if player_id in finished_ids]\n    return list(merged.values())'''
if old not in text:
    raise SystemExit('exporter: merge_orders not found')
text = text.replace(old, new, 1)

old = '''    print(f"Discovered {len(players)} unique players | gross order={len(gross_order)} | net order={len(net_order)}")\n    exported_players = []'''
new = '''    finished_ids = {item["id"] for item in gross_order + net_order if item.get("finished")}\n    print(\n        f"Discovered {len(players)} players to export | gross rows={len(gross_order)} | "\n        f"net rows={len(net_order)} | official finishers={len(finished_ids)}"\n    )\n    gross_by_id = {item["id"]: item for item in gross_order}\n    net_by_id = {item["id"]: item for item in net_order}\n    exported_players = []'''
if old not in text:
    raise SystemExit('exporter: discovery print not found')
text = text.replace(old, new, 1)

old = '''        item = {"id": player_id, "name": player.get("name"), "scorecard": None, "stats": None, "shots": None, "errors": {}}'''
new = '''        item = {\n            "id": player_id,\n            "name": player.get("name"),\n            "leaderboard": {"gross": gross_by_id.get(player_id), "net": net_by_id.get(player_id)},\n            "scorecard": None,\n            "stats": None,\n            "shots": None,\n            "errors": {},\n        }'''
if old not in text:
    raise SystemExit('exporter: player item not found')
text = text.replace(old, new, 1)
text = text.replace('"exporterVersion": "lab-0.4"', '"exporterVersion": "lab-0.5"', 1)
path.write_text(text)

# Patch analyzer: official leaderboard F decides completion; score/par totals use scored holes only.
path = Path('src/analyze_tournament.py')
text = path.read_text()
text = text.replace('def parse_scorecard(html: str | None) -> dict:', 'def parse_scorecard(html: str | None, official_finished: bool | None = None) -> dict:', 1)

old = '''        complete = len(holes) == 18 and all(hole["gross"] is not None for hole in holes)\n        rounds.append({\n            "round": round_index,\n            "complete": complete,\n            "par": sum(hole["par"] for hole in holes if hole["par"] is not None),\n            "gross": sum(hole["gross"] for hole in holes if hole["gross"] is not None),\n            "net": sum(hole["net"] for hole in holes if hole["net"] is not None) if any(hole["net"] is not None for hole in holes) else None,\n            "holes": holes,\n        })'''
new = '''        scored_holes = [hole for hole in holes if hole["gross"] is not None]\n        legacy_complete = len(holes) == 18 and len(scored_holes) == 18\n        if official_finished is True:\n            complete = bool(scored_holes) and all(hole["par"] is not None for hole in scored_holes)\n        elif official_finished is False:\n            complete = False\n        else:\n            complete = legacy_complete\n\n        played_par = sum(hole["par"] for hole in scored_holes if hole["par"] is not None)\n        gross_total = sum(hole["gross"] for hole in scored_holes)\n        net_values = [hole["net"] for hole in scored_holes]\n        net_total = sum(value for value in net_values if value is not None) if net_values and all(value is not None for value in net_values) else None\n        rounds.append({\n            "round": round_index,\n            "complete": complete,\n            "holesPlayed": len(scored_holes),\n            "scheduledHoles": len(holes),\n            "par": played_par,\n            "gross": gross_total,\n            "net": net_total,\n            "holes": holes,\n        })'''
if old not in text:
    raise SystemExit('analyzer: round completion block not found')
text = text.replace(old, new, 1)

old = '''    return {\n        "rounds": rounds,\n        "holes": all_holes,\n        "complete": bool(rounds) and len(complete_rounds) == len(rounds),\n        "par": par_total if complete_rounds else None,'''
new = '''    return {\n        "rounds": rounds,\n        "holes": all_holes,\n        "holesPlayed": sum(round_["holesPlayed"] for round_ in complete_rounds),\n        "scheduledHoles": sum(round_["scheduledHoles"] for round_ in rounds),\n        "completionSource": "officialLeaderboard" if official_finished is not None else "legacy18Hole",\n        "complete": bool(rounds) and len(complete_rounds) == len(rounds),\n        "par": par_total if complete_rounds else None,'''
if old not in text:
    raise SystemExit('analyzer: scorecard return block not found')
text = text.replace(old, new, 1)

insert_after = '''def display_to_par(value: int | None) -> str | None:\n    if value is None:\n        return None\n    if value == 0:\n        return "E"\n    return f"+{value}" if value > 0 else str(value)\n'''
addition = '''\n\ndef leaderboard_to_par(value: str | None) -> int | None:\n    if not value:\n        return None\n    normalized = value.strip().upper()\n    if normalized == "E":\n        return 0\n    match = re.search(r"[-+]?\\d+", normalized.replace(",", ""))\n    return int(match.group()) if match else None\n'''
if insert_after not in text:
    raise SystemExit('analyzer: display_to_par block not found')
text = text.replace(insert_after, insert_after + addition, 1)

old = '''        player_id = raw_player["id"]\n        scorecard = parse_scorecard(raw_player.get("scorecard"))\n        stats = parse_stats(raw_player.get("stats"))'''
new = '''        player_id = raw_player["id"]\n        raw_lb = raw_player.get("leaderboard") or {}\n        gross_meta = raw_lb.get("gross") or next((item for item in gross_order if item.get("id") == player_id), {})\n        net_meta = raw_lb.get("net") or next((item for item in net_order if item.get("id") == player_id), {})\n        official_values = [meta.get("finished") for meta in (gross_meta, net_meta) if "finished" in meta]\n        official_finished = any(official_values) if official_values else None\n        scorecard = parse_scorecard(raw_player.get("scorecard"), official_finished=official_finished)\n\n        if official_finished is True:\n            if not scorecard.get("complete"):\n                raise RuntimeError(f"Official finisher {raw_player.get('name') or player_id} has no usable completed scorecard")\n            expected_gross = leaderboard_to_par(gross_meta.get("total"))\n            expected_net = leaderboard_to_par(net_meta.get("total"))\n            if expected_gross is not None and scorecard.get("grossToPar") != expected_gross:\n                raise RuntimeError(\n                    f"Official gross total mismatch for {raw_player.get('name') or player_id}: "\n                    f"leaderboard={expected_gross}, scorecard={scorecard.get('grossToPar')}"\n                )\n            if expected_net is not None and scorecard.get("netToPar") != expected_net:\n                raise RuntimeError(\n                    f"Official net total mismatch for {raw_player.get('name') or player_id}: "\n                    f"leaderboard={expected_net}, scorecard={scorecard.get('netToPar')}"\n                )\n\n        stats = parse_stats(raw_player.get("stats"))'''
if old not in text:
    raise SystemExit('analyzer: player parse block not found')
text = text.replace(old, new, 1)

old = '''            "name": raw_player.get("name"),\n            "completed": scorecard.get("complete", False),\n            "leaderboard": {'''
new = '''            "name": raw_player.get("name"),\n            "completed": scorecard.get("complete", False),\n            "officialFinished": official_finished,\n            "leaderboard": {'''
if old not in text:
    raise SystemExit('analyzer: player output block not found')
text = text.replace(old, new, 1)

old = '''            "playersWithShots": sum(1 for player in analyzed_players if player.get("worstHole") and player["worstHole"].get("shots")),\n        },'''
new = '''            "playersWithShots": sum(1 for player in analyzed_players if player.get("worstHole") and player["worstHole"].get("shots")),\n            "variableHoleFinishers": sum(\n                1 for player in analyzed_players\n                if player["completed"] and player["scorecard"].get("holesPlayed") not in (None, 18)\n            ),\n        },'''
if old not in text:
    raise SystemExit('analyzer: validation block not found')
text = text.replace(old, new, 1)
path.write_text(text)

print('Patched official-finisher + variable-hole completion support')
