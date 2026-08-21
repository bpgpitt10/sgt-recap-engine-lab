from __future__ import annotations

import re

import render_high_loft as renderer

# Capture original functions before monkey-patching them below.
_original_analysis_map = renderer.analysis_map
_original_landing = renderer.landing
_original_recap_page = renderer.recap_page


def competition_mode(event: dict, cfg: dict) -> str:
    event_id = str(event.get("id"))
    return str((cfg.get("competitionOverrides") or {}).get(event_id, "net")).lower()


def normalized_analysis_map() -> dict[int, dict]:
    """Normalize Carnage shape and apply explicit event-level competition order.

    Older/current analyzer outputs may store carnage[].hole as the numeric hole
    number while the High Loft renderer wants the player's full worst-hole
    object for par, gross score, relative-to-par damage, and shot trail.

    For an explicitly configured gross-primary scratch event, swap only the two
    leaderboard arrays before rendering. The authoritative winners object stays
    untouched so archive cards continue to report literal Net/Gross winners.
    """
    analyses = _original_analysis_map()
    cfg = renderer.config()
    for analysis in analyses.values():
        players = {
            player.get("name"): player
            for player in analysis.get("players", [])
            if player.get("completed")
        }
        normalized = []
        for original in analysis.get("carnage", []):
            item = dict(original)
            raw_hole = item.get("hole")
            if not isinstance(raw_hole, dict):
                player = players.get(item.get("name")) or {}
                worst_hole = player.get("worstHole")
                if isinstance(worst_hole, dict):
                    item["hole"] = worst_hole
                else:
                    raise RuntimeError(
                        f"Carnage entry for {item.get('name')} has numeric/invalid hole "
                        f"{raw_hole!r} and no authoritative worstHole object"
                    )
            normalized.append(item)
        analysis["carnage"] = normalized

        if competition_mode(analysis.get("tournament") or {}, cfg) == "gross":
            leaderboard = analysis.get("leaderboard") or {}
            net = leaderboard.get("net", [])
            gross = leaderboard.get("gross", [])
            leaderboard["net"], leaderboard["gross"] = gross, net

    return analyses


def gross_primary_landing(history: dict, league_copy: dict, analyses: dict[int, dict], latest_copy: dict, cfg: dict, production_root):
    html = _original_landing(history, league_copy, analyses, latest_copy, cfg, production_root)
    latest_event = history["completedEvents"][0]
    if competition_mode(latest_event, cfg) != "gross":
        return html
    return (
        html.replace("🏆 Net champion", "🏆 Gross champion")
        .replace("Net challenger", "Gross challenger")
        .replace("Gross winner</small>", "Net standings leader</small>", 1)
        .replace("Gross runner-up", "Net standings runner-up", 1)
    )


def gross_primary_recap_page(event: dict, analysis: dict, copy: dict, cfg: dict, excluded: bool) -> str:
    html = _original_recap_page(event, analysis, copy, cfg, excluded)
    if competition_mode(event, cfg) != "gross":
        return html

    html = (
        html.replace("🏆 Net champion", "🏆 Gross champion")
        .replace("Net challenger", "Gross challenger")
        .replace("Gross winner", "Net standings leader", 1)
        .replace("Gross runner-up", "Net standings runner-up", 1)
        .replace("The net race first. Then the wreckage underneath it.", "The gross race first. Then the wreckage underneath it.")
        .replace(
            "Net determines the tournament. Gross and SGT strokes gained explain the golf underneath it.",
            "Gross determines this scratch tournament. Net is secondary; SGT strokes gained explains the golf underneath it.",
        )
        .replace('data-board="net" aria-pressed="true">Net</button>', 'data-board="net" aria-pressed="true">Gross</button>')
        .replace('data-board="gross" aria-pressed="false">Gross</button>', 'data-board="gross" aria-pressed="false">Net</button>')
        .replace("Net order. Gross context.", "Gross order. Net context.")
    )
    html = re.sub(
        r"<span>NET ([^<]+?) · GROSS ([^<]+?)</span>",
        r"<span>GROSS \2 · NET \1</span>",
        html,
    )
    return html


renderer.analysis_map = normalized_analysis_map
renderer.landing = gross_primary_landing
renderer.recap_page = gross_primary_recap_page


if __name__ == "__main__":
    renderer.main()
