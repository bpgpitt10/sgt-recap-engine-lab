from __future__ import annotations

import render_high_loft as renderer

# Capture the original function before monkey-patching it below. Otherwise the
# wrapper calls itself forever after renderer.analysis_map is reassigned.
_original_analysis_map = renderer.analysis_map


def normalized_analysis_map() -> dict[int, dict]:
    """Accept both supported Carnage shapes before handing data to the renderer.

    Older/current analyzer outputs may store carnage[].hole as the numeric hole
    number while the High Loft renderer wants the player's full worst-hole
    object for par, gross score, relative-to-par damage, and shot trail.
    Preserve an already-expanded object; otherwise resolve it from the
    authoritative completed player record.
    """
    analyses = _original_analysis_map()
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
    return analyses


renderer.analysis_map = normalized_analysis_map


if __name__ == "__main__":
    renderer.main()
