from __future__ import annotations

import backfill_high_loft_archive as backfill
import write_recap


_original_build_fact_package = write_recap.build_fact_package


def backfill_safe_fact_package(analysis: dict, config: dict, history: dict | None) -> dict:
    """Flatten renderer-normalized Carnage holes before building recap facts.

    The archive backfill expands carnage[].hole to the authoritative worst-hole
    object so the HTML renderer has shots/par/score data. The generic recap fact
    builder expects each Carnage entry itself to carry those hole fields. Without
    this adapter it produces a nested hole object and the factual validator can
    end up trying int(dict).
    """
    adapted = dict(analysis)
    carnage = []
    for original in analysis.get("carnage", []):
        item = dict(original)
        hole = item.get("hole")
        if isinstance(hole, dict):
            flat = dict(hole)
            flat["name"] = item.get("name")
            carnage.append(flat)
        else:
            carnage.append(item)
    adapted["carnage"] = carnage
    return _original_build_fact_package(adapted, config, history)


write_recap.build_fact_package = backfill_safe_fact_package


if __name__ == "__main__":
    backfill.main()
