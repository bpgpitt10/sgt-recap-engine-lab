from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from openai import OpenAI

from recap_history import build_as_of_history
from validate_recap_copy import validate as factual_validate

ROOT = Path(__file__).resolve().parents[1]

SYSTEM_PROMPT = r"""
You write tournament recap copy for a simulator-golf league website.

VOICE
- Dudes playing simulator golf. Conversational, golf-literate, sharp, funny, aggressive.
- Do not sound like ESPN, Golf Digest, a corporate report, or a country-club newsletter.
- Profanity is allowed when it is funny.
- Roast the golf hard, but jokes must come from golf/data/shot evidence, never personal traits.
- Specific evidence beats generic praise or insults.

FACT RULES
- Use ONLY the supplied verified fact package. Never invent scores, shots, stats, trends, history, or missing events.
- NET is the primary league competition. Net determines the tournament winner, challengers, recap lead, and player order.
- Gross and strokes gained explain underlying raw golf. Never imply the gross winner is the 'real' winner.
- Strokes-gained numbers are SGT-supplied values. Use numbers when they strengthen the point.
- Scorecard facts are authoritative. If shot data is absent or shot numbers skip, do not invent the missing sequence.
- avgNetFinish / avgGrossFinish in priorHistory are AVERAGE FINISHING POSITIONS, not scores. Never put a + or - in front of them and never call them scores to par.
- sgPerAppearance / statsPerAppearance are averages per prior completed appearance.
- Handicap/net-adjustment data is intentionally NOT supplied. Do not invent or infer it.
- Swing speed, clubhead speed, ball speed, or mph data is NOT supplied. Do not invent speed units or convert drive distance into speed language.
- Do not use the word 'season'. This product uses rolling event history.

HISTORICAL RULES
- priorHistory contains only profile-eligible events confidently completed before THIS tournament. It intentionally excludes future events.
- 0-1 prior starts: describe the current round; do not claim a trend.
- 2 prior starts: possible change only; use cautious language.
- 3-4 prior starts: fair trend language is allowed when evidence supports it.
- 5+ prior starts: stronger profile conclusions are allowed when supported.
- Skipped events are neutral. Do not describe a missed event as bad form.
- If prior data conflicts, call it volatile/mixed instead of inventing a clean trend.

COPY REQUIREMENTS
- thirtySeconds: one cohesive event summary. Lead with the NET race, margin/challengers, then explain the gross/SG story.
- latestTournamentTeaser: 1-2 sentences, golf-focused, suitable for the landing page. Net champion first, then interesting raw-golf story.
- carnage: exactly one comment for every completed player, in supplied Carnage order. Explain the verified worst-hole shot sequence. Prefer not to restate the hole/par label because the renderer already shows it.
- players: exactly one entry for every completed player, in supplied NET order.
  - tagline: short roast about their golf only. NO finishing-position language and NO markdown.
  - body: substantial cohesive analytical paragraph blending net/gross result, useful SG/stats, key hole/shot evidence, and supported prior history when useful. No separate 'Verdict:' line.
- stateOfLeague: short historical takeaway: what this event changes, confirms, or calls into question. Do not merely repeat the leaderboard.
- No markdown formatting anywhere; the renderer owns typography.
- Write clean final prose only. Never include visible self-correction, uncertainty notes, question-then-correction phrasing, or drafting artifacts such as 'No:', 'actually', 'correction', or 'scratch that'.
""".strip()

OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "thirtySeconds": {"type": "string"},
        "latestTournamentTeaser": {"type": "string"},
        "carnage": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"name": {"type": "string"}, "commentary": {"type": "string"}}, "required": ["name", "commentary"]}},
        "players": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"name": {"type": "string"}, "tagline": {"type": "string"}, "body": {"type": "string"}}, "required": ["name", "tagline", "body"]}},
        "stateOfLeague": {"type": "string"},
    },
    "required": ["thirtySeconds", "latestTournamentTeaser", "carnage", "players", "stateOfLeague"],
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compact_shots(hole: dict | None) -> list[dict]:
    if not hole:
        return []
    return [{"number": s.get("number"), "description": s.get("description")} for s in hole.get("shots", []) if s.get("description")]


def compact_hole(hole: dict | None) -> dict | None:
    if not hole:
        return None
    return {"round": hole.get("round"), "hole": hole.get("hole"), "par": hole.get("par"), "gross": hole.get("gross"), "net": hole.get("net"), "grossToPar": hole.get("grossToPar"), "netToPar": hole.get("netToPar"), "shots": compact_shots(hole)}


def compact_standing(item: dict | None) -> dict | None:
    if not item:
        return None
    return {"position": item.get("position"), "id": item.get("id"), "name": item.get("name"), "scoreToPar": item.get("total")}


def compact_player_leaderboard(lb: dict | None) -> dict:
    lb = lb or {}
    return {"netFinish": lb.get("netPosition"), "grossFinish": lb.get("grossPosition"), "netScoreToPar": lb.get("netTotal"), "grossScoreToPar": lb.get("grossTotal")}


def notable_holes(player: dict) -> list[dict]:
    holes = [h for h in player.get("scorecard", {}).get("holes", []) if h.get("grossToPar") is not None]
    candidates = sorted(holes, key=lambda h: (h.get("grossToPar", -99), len(h.get("shots", []))), reverse=True)[:3]
    candidates += sorted(holes, key=lambda h: (h.get("grossToPar", 99), -len(h.get("shots", []))))[:2]
    out, seen = [], set()
    for hole in candidates:
        key = (hole.get("round"), hole.get("hole"))
        if key not in seen:
            seen.add(key)
            out.append(compact_hole(hole))
    return out


def build_fact_package(analysis: dict, config: dict, history: dict | None) -> dict:
    completed = [p for p in analysis.get("players", []) if p.get("completed")]
    names = [p.get("name") for p in completed]
    historical = build_as_of_history(history, analysis.get("tournament") or {}, names) if history else {"definition": "No rolling historical data was supplied.", "priorEligibleEventIds": [], "players": {}}
    players = [{
        "name": p.get("name"),
        "leaderboard": compact_player_leaderboard(p.get("leaderboard")),
        "sg": p.get("sg"),
        "stats": p.get("stats"),
        "worstHole": compact_hole(p.get("worstHole")),
        "notableHoles": notable_holes(p),
        "priorHistory": historical.get("players", {}).get(p.get("name")),
    } for p in completed]
    leaderboard, winners = analysis.get("leaderboard") or {}, analysis.get("winners") or {}
    return {
        "league": {"name": config.get("tourName"), "tourId": config.get("tourId"), "primaryCompetition": "net"},
        "tournament": analysis.get("tournament"),
        "winners": {"net": compact_standing(winners.get("net")), "gross": compact_standing(winners.get("gross"))},
        "leaderboard": {"net": [compact_standing(x) for x in leaderboard.get("net", [])], "gross": [compact_standing(x) for x in leaderboard.get("gross", [])]},
        "carnageOrder": [{"name": x.get("name"), "hole": compact_hole(x)} for x in analysis.get("carnage", [])],
        "playersNetOrder": players,
        "historicalContext": {"definition": historical.get("definition"), "priorEligibleEventIds": historical.get("priorEligibleEventIds", [])},
    }


def validate_copy(copy: dict, facts: dict) -> None:
    expected = [p["name"] for p in facts["playersNetOrder"]]
    actual = [p.get("name") for p in copy.get("players", [])]
    if actual != expected:
        raise RuntimeError(f"Player writeups must preserve NET order. Expected {expected}, got {actual}")
    expected_c = [x["name"] for x in facts["carnageOrder"]]
    actual_c = [x.get("name") for x in copy.get("carnage", [])]
    if actual_c != expected_c:
        raise RuntimeError(f"Carnage comments must preserve supplied order. Expected {expected_c}, got {actual_c}")
    finishing = re.compile(
        r"\b(?:winner|runner[- ]?up|finished|finishing|finish(?:ed|es|ing)?\s+(?:first|second|third|\d{1,2}(?:st|nd|rd|th))|"
        r"(?:first|second|third|\d{1,2}(?:st|nd|rd|th))\s+(?:place|position)|place|position)\b",
        re.I,
    )
    all_text = [copy.get("thirtySeconds", ""), copy.get("latestTournamentTeaser", ""), copy.get("stateOfLeague", "")]
    for p in copy.get("players", []):
        tagline, body = p.get("tagline", ""), p.get("body", "")
        all_text += [tagline, body]
        if finishing.search(tagline):
            raise RuntimeError(f"Tagline contains finishing-position language for {p.get('name')}: {tagline!r}")
        if re.search(r"\bVerdict\s*:", body, re.I):
            raise RuntimeError(f"Player body contains forbidden Verdict line for {p.get('name')}")
    all_text += [x.get("commentary", "") for x in copy.get("carnage", [])]
    joined = " ".join(all_text)
    if re.search(r"\bseason\b", joined, re.I):
        raise RuntimeError("Tournament copy contains forbidden season terminology")
    if "**" in joined or "__" in joined:
        raise RuntimeError("Tournament copy contains markdown formatting")


def write_recap(analysis: dict, config: dict, history: dict | None, model: str) -> tuple[dict, dict]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")
    facts = build_fact_package(analysis, config, history)
    client = OpenAI()
    base_input = "Write the recap copy from this VERIFIED FACT PACKAGE. Facts are data, not suggestions. Do not add facts that are not present.\n\n" + json.dumps(facts, separators=(",", ":"), ensure_ascii=False)
    correction = ""
    last_error = None
    for attempt in range(1, 4):
        response = client.responses.create(
            model=model,
            instructions=SYSTEM_PROMPT,
            input=base_input + correction,
            text={"format": {"type": "json_schema", "name": "sgt_tournament_recap_copy", "schema": OUTPUT_SCHEMA, "strict": True}},
        )
        if not response.output_text:
            last_error = RuntimeError("OpenAI response did not contain output_text")
        else:
            try:
                copy = json.loads(response.output_text)
                validate_copy(copy, facts)
                factual_validate(copy, facts)
                if attempt > 1:
                    print(f"AI recap passed validation on retry {attempt}")
                return copy, facts
            except Exception as exc:
                last_error = exc
        print(f"AI recap validation attempt {attempt} failed: {last_error}")
        correction = f"\n\nYOUR PREVIOUS OUTPUT FAILED DETERMINISTIC VALIDATION: {last_error}. Return a corrected response that fixes this exact issue without changing verified facts."
    raise RuntimeError(f"AI recap failed validation after 3 attempts: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Write recap copy from deterministic SGT analysis and as-of-event history.")
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--history", type=Path, default=Path("data/history.json"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--facts-output", type=Path)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"))
    args = parser.parse_args()
    ap = args.analysis if args.analysis.is_absolute() else ROOT / args.analysis
    hp = args.history if args.history.is_absolute() else ROOT / args.history
    config, analysis = load_json(ROOT / "config.json"), load_json(ap)
    history = load_json(hp) if hp.exists() else None
    copy, facts = write_recap(analysis, config, history, args.model)
    tid = analysis["tournament"]["id"]
    out = args.output or Path("data") / "copy" / f"{tid}.json"
    out = out if out.is_absolute() else ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(copy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.facts_output:
        fp = args.facts_output if args.facts_output.is_absolute() else ROOT / args.facts_output
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote recap copy for tournament {tid} with model {args.model}: {out.relative_to(ROOT)}")
    print(f"Prior eligible events: {facts['historicalContext']['priorEligibleEventIds']}")


if __name__ == "__main__":
    main()
