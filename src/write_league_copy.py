from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]

SYSTEM_PROMPT = r"""
You write league snapshot and player scouting-file copy for a simulator-golf league website.

VOICE
- Dudes playing simulator golf. Conversational, golf-literate, sharp, funny, aggressive.
- Do not sound like ESPN, Golf Digest, a corporate report, or a country-club newsletter.
- Profanity is allowed when it is funny.
- Roast the golf hard, but jokes must come from golf/data evidence, never personal traits.
- Specific golf tendencies beat generic praise or insults.

FACT RULES
- Use ONLY the supplied verified rolling-history facts. Never invent scores, stats, wins, events, trends, or reasons.
- NET is the primary league competition. AVG NET determines the supplied player order.
- Gross and SGT strokes gained explain the underlying golf; never imply gross makes someone the 'real' winner.
- Skipped events are neutral. A player with fewer starts did not necessarily play worse; they simply did not appear.
- Do not use the word 'season'. The product uses rolling event windows.
- Do not infer handicaps from net adjustments.

HISTORICAL EVIDENCE RULES
- round_only: describe the observed round/window only. Do not call anything a trend.
- possible_change: two appearances can suggest a possible change, but use cautious language.
- trend: three or four appearances support a fair trend statement.
- strong_trend: five or more appearances support stronger player-profile conclusions.
- If the data conflicts, say the profile is volatile or mixed rather than forcing a clean story.

COPY REQUIREMENTS
- leagueSummary: 2-4 sentences explaining what this rolling window says about the league right now. Lead with NET competition, then useful underlying golf patterns.
- leagueBullets: exactly 3 short, useful takeaways. Do not merely repeat the leaderboard.
- profiles: exactly one profile for every supplied player, in supplied AVG NET order.
- Each profile should be one cohesive paragraph, substantial enough that people enjoy reading about themselves.
- Blend AVG NET/result pattern, wins when useful, SG fingerprint, repeatable stat tendencies, volatility, and recent event evidence.
- Roast bad golf when the evidence earns it.
- Do not add a separate Verdict line.
- Do not put markdown formatting in the output; the renderer owns typography.
- Avoid overloading every paragraph with numbers. Use exact numbers only when they make the point sharper.
""".strip()

OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "leagueSummary": {"type": "string"},
        "leagueBullets": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {"type": "string"},
        },
        "profiles": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "profile": {"type": "string"},
                },
                "required": ["name", "profile"],
            },
        },
    },
    "required": ["leagueSummary", "leagueBullets", "profiles"],
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compact_player(player: dict) -> dict:
    return {
        "name": player.get("name"),
        "starts": player.get("starts"),
        "evidenceLevel": player.get("evidenceLevel"),
        "avgNet": player.get("avgNet"),
        "avgGross": player.get("avgGross"),
        "netWins": player.get("netWins"),
        "grossWins": player.get("grossWins"),
        "sg": player.get("sg"),
        "stats": player.get("stats"),
        "events": player.get("events"),
    }


def fact_package(history: dict, scope_names: list[str], scope: dict) -> dict:
    return {
        "league": history.get("tour"),
        "rollingWindow": {
            "selectorsSharingThisWindow": scope_names,
            "eventCount": scope.get("eventCount"),
            "eventIds": scope.get("eventIds"),
            "definition": history.get("scopeDefinition"),
        },
        "playersAvgNetOrder": [compact_player(player) for player in scope.get("players", [])],
    }


def validate_copy(copy: dict, facts: dict) -> None:
    expected = [player["name"] for player in facts["playersAvgNetOrder"]]
    actual = [player.get("name") for player in copy.get("profiles", [])]
    if actual != expected:
        raise RuntimeError(f"Profiles must preserve AVG NET order. Expected {expected}, got {actual}")

    text = " ".join(
        [copy.get("leagueSummary", ""), *copy.get("leagueBullets", [])]
        + [profile.get("profile", "") for profile in copy.get("profiles", [])]
    )
    if re.search(r"\bseason\b", text, re.IGNORECASE):
        raise RuntimeError("Rolling league copy contains forbidden season terminology")
    if re.search(r"\bVerdict\s*:", text, re.IGNORECASE):
        raise RuntimeError("Rolling league copy contains forbidden Verdict line")
    if "**" in text or "__" in text:
        raise RuntimeError("Rolling league copy contains markdown formatting")


def write_window(client: OpenAI, model: str, facts: dict) -> dict:
    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=(
            "Write the rolling league snapshot and scouting profiles from this VERIFIED FACT PACKAGE. "
            "Facts are data, not suggestions. Do not add facts that are not present.\n\n"
            + json.dumps(facts, separators=(",", ":"), ensure_ascii=False)
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "sgt_rolling_league_copy",
                "schema": OUTPUT_SCHEMA,
                "strict": True,
            }
        },
    )
    if not response.output_text:
        raise RuntimeError("OpenAI response did not contain output_text")
    copy = json.loads(response.output_text)
    validate_copy(copy, facts)
    return copy


def write_all(history: dict, model: str) -> tuple[dict, dict]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI()
    scope_groups: dict[tuple[int, ...], list[str]] = {}
    for scope_name in history.get("availableScopes", []):
        scope = history["scopes"][scope_name]
        key = tuple(int(value) for value in scope.get("eventIds", []))
        scope_groups.setdefault(key, []).append(scope_name)

    output_scopes = {}
    facts_scopes = {}
    for event_ids, scope_names in scope_groups.items():
        canonical = scope_names[0]
        scope = history["scopes"][canonical]
        facts = fact_package(history, scope_names, scope)
        print(f"Writing rolling window {scope_names}: events={list(event_ids)} players={len(scope.get('players', []))}")
        copy = write_window(client, model, facts)
        for scope_name in scope_names:
            output_scopes[scope_name] = {
                "generatedFromScope": canonical,
                "eventIds": list(event_ids),
                **copy,
            }
            facts_scopes[scope_name] = facts

    return (
        {
            "schemaVersion": 1,
            "model": model,
            "defaultScope": history.get("defaultScope"),
            "availableScopes": history.get("availableScopes"),
            "scopes": output_scopes,
        },
        {
            "schemaVersion": 1,
            "defaultScope": history.get("defaultScope"),
            "scopes": facts_scopes,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Write rolling league snapshot and scouting-file copy.")
    parser.add_argument("history", type=Path, default=Path("data/history.json"), nargs="?")
    parser.add_argument("--output", type=Path, default=Path("data/league-copy.json"))
    parser.add_argument("--facts-output", type=Path, default=Path("data/league-facts.json"))
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"))
    args = parser.parse_args()

    history_path = args.history if args.history.is_absolute() else ROOT / args.history
    output = args.output if args.output.is_absolute() else ROOT / args.output
    facts_output = args.facts_output if args.facts_output.is_absolute() else ROOT / args.facts_output

    copy, facts = write_all(load_json(history_path), args.model)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(copy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    facts_output.parent.mkdir(parents=True, exist_ok=True)
    facts_output.write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {output.relative_to(ROOT)} using {args.model}")


if __name__ == "__main__":
    main()
