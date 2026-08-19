from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from openai import OpenAI

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
- Gross and strokes gained explain who played the best raw golf and why. Never imply the gross winner is the 'real' winner.
- Strokes-gained numbers are SGT-supplied values. Use numbers when they strengthen the point.
- Scorecard facts are authoritative. If shot data is absent or incomplete, do not invent the missing sequence.
- This fact package may not contain historical context. If it does not, do not manufacture trends; keep State of the League limited to what this event suggests or establishes right now.

COPY REQUIREMENTS
- thirtySeconds: one cohesive event summary. Lead with the NET race, margin/challengers, then explain the gross/SG story.
- latestTournamentTeaser: 1-2 sentences, golf-focused, suitable for the landing page. Net champion first, then the interesting raw-golf story.
- carnage: exactly one comment for every completed player, in the supplied Carnage order. Explain how that player's worst hole went to hell using the supplied hole/shot evidence. Make it funny and specific.
- players: exactly one entry for every completed player, in supplied NET order. Each needs:
  - tagline: short bold-style roast about their golf only. NO finishing-position language.
  - body: substantial cohesive analytical paragraph blending net/gross result, useful SG/stats, what worked/failed, and key hole/shot evidence. No separate 'Verdict:' line.
- stateOfLeague: short takeaway. Do not repeat the leaderboard.
""".strip()

OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "thirtySeconds": {"type": "string"},
        "latestTournamentTeaser": {"type": "string"},
        "carnage": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "commentary": {"type": "string"},
                },
                "required": ["name", "commentary"],
            },
        },
        "players": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "tagline": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["name", "tagline", "body"],
            },
        },
        "stateOfLeague": {"type": "string"},
    },
    "required": [
        "thirtySeconds",
        "latestTournamentTeaser",
        "carnage",
        "players",
        "stateOfLeague",
    ],
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compact_shots(hole: dict | None) -> list[dict]:
    if not hole:
        return []
    return [
        {"number": shot.get("number"), "description": shot.get("description")}
        for shot in hole.get("shots", [])
        if shot.get("description")
    ]


def compact_hole(hole: dict | None) -> dict | None:
    if not hole:
        return None
    return {
        "round": hole.get("round"),
        "hole": hole.get("hole"),
        "par": hole.get("par"),
        "gross": hole.get("gross"),
        "net": hole.get("net"),
        "grossToPar": hole.get("grossToPar"),
        "netToPar": hole.get("netToPar"),
        "shots": compact_shots(hole),
    }


def notable_holes(player: dict) -> list[dict]:
    holes = player.get("scorecard", {}).get("holes", [])
    eligible = [hole for hole in holes if hole.get("grossToPar") is not None]
    worst = sorted(eligible, key=lambda h: (h.get("grossToPar", -99), len(h.get("shots", []))), reverse=True)[:3]
    best = sorted(eligible, key=lambda h: (h.get("grossToPar", 99), -len(h.get("shots", []))))[:2]
    ordered = []
    seen = set()
    for hole in worst + best:
        key = (hole.get("round"), hole.get("hole"))
        if key in seen:
            continue
        seen.add(key)
        ordered.append(compact_hole(hole))
    return ordered


def build_fact_package(analysis: dict, config: dict) -> dict:
    completed_players = [player for player in analysis.get("players", []) if player.get("completed")]
    return {
        "league": {
            "name": config.get("tourName"),
            "tourId": config.get("tourId"),
            "season": "Season 1",
            "primaryCompetition": "net",
        },
        "tournament": analysis.get("tournament"),
        "winners": analysis.get("winners"),
        "leaderboard": analysis.get("leaderboard"),
        "carnageOrder": [
            {
                "name": item.get("name"),
                "hole": compact_hole(item),
            }
            for item in analysis.get("carnage", [])
        ],
        "playersNetOrder": [
            {
                "name": player.get("name"),
                "leaderboard": player.get("leaderboard"),
                "sg": player.get("sg"),
                "stats": player.get("stats"),
                "worstHole": compact_hole(player.get("worstHole")),
                "notableHoles": notable_holes(player),
            }
            for player in completed_players
        ],
        "historicalContext": None,
    }


def validate_copy(copy: dict, facts: dict) -> None:
    expected_players = [player["name"] for player in facts["playersNetOrder"]]
    actual_players = [player.get("name") for player in copy.get("players", [])]
    if actual_players != expected_players:
        raise RuntimeError(f"Player writeups must preserve NET order. Expected {expected_players}, got {actual_players}")

    expected_carnage = [item["name"] for item in facts["carnageOrder"]]
    actual_carnage = [item.get("name") for item in copy.get("carnage", [])]
    if actual_carnage != expected_carnage:
        raise RuntimeError(f"Carnage comments must preserve supplied order. Expected {expected_carnage}, got {actual_carnage}")

    finishing_language = re.compile(
        r"\b(winner|runner[- ]?up|finished|finishing|place|position|first|second|third|1st|2nd|3rd)\b",
        re.IGNORECASE,
    )
    for player in copy.get("players", []):
        tagline = player.get("tagline", "")
        body = player.get("body", "")
        if finishing_language.search(tagline):
            raise RuntimeError(f"Tagline contains finishing-position language for {player.get('name')}: {tagline!r}")
        if re.search(r"\bVerdict\s*:", body, re.IGNORECASE):
            raise RuntimeError(f"Player body contains forbidden Verdict line for {player.get('name')}")


def write_recap(analysis: dict, config: dict, model: str) -> tuple[dict, dict]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")

    facts = build_fact_package(analysis, config)
    client = OpenAI()
    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=(
            "Write the recap copy from this VERIFIED FACT PACKAGE. Facts are data, not suggestions. "
            "Do not add facts that are not present.\n\n"
            + json.dumps(facts, separators=(",", ":"), ensure_ascii=False)
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "sgt_tournament_recap_copy",
                "schema": OUTPUT_SCHEMA,
                "strict": True,
            }
        },
    )
    if not response.output_text:
        raise RuntimeError("OpenAI response did not contain output_text")
    copy = json.loads(response.output_text)
    validate_copy(copy, facts)
    return copy, facts


def main() -> None:
    parser = argparse.ArgumentParser(description="Write recap copy from deterministic SGT analysis.")
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--facts-output", type=Path)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.6"))
    args = parser.parse_args()

    analysis_path = args.analysis if args.analysis.is_absolute() else ROOT / args.analysis
    config = load_json(ROOT / "config.json")
    analysis = load_json(analysis_path)
    copy, facts = write_recap(analysis, config, args.model)

    tournament_id = analysis["tournament"]["id"]
    output = args.output or Path("data") / "copy" / f"{tournament_id}.json"
    output = output if output.is_absolute() else ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(copy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.facts_output:
        facts_output = args.facts_output if args.facts_output.is_absolute() else ROOT / args.facts_output
        facts_output.parent.mkdir(parents=True, exist_ok=True)
        facts_output.write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Wrote recap copy for tournament {tournament_id} with model {args.model}: {output.relative_to(ROOT)}")
    print(f"Player writeups: {len(copy['players'])} | Carnage comments: {len(copy['carnage'])}")


if __name__ == "__main__":
    main()
