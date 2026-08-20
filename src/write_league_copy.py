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
- NET is the primary league competition. avgNetFinish is AVERAGE FINISHING POSITION, not a score. Never prefix it with + or - and never describe it as a score to par.
- avgGrossFinish is also AVERAGE FINISHING POSITION, not a score.
- sgPerAppearance and statsPerAppearance are averages per completed appearance in this rolling window.
- Gross and SGT strokes gained explain the underlying golf; never imply gross makes someone the 'real' winner.
- Skipped events are neutral. A player with fewer starts did not necessarily play worse; they simply did not appear.
- Do not use the word 'season'. The product uses rolling event windows.
- Handicap/net-adjustment data and swing/ball-speed data are not supplied. Do not infer them.

HISTORICAL EVIDENCE RULES
- round_only: describe the observed round/window only. Do not call anything a trend.
- possible_change: two appearances can suggest a possible change, but use cautious language.
- trend: three or four appearances support a fair trend statement.
- strong_trend: five or more appearances support stronger player-profile conclusions.
- If the data conflicts, say the profile is volatile or mixed rather than forcing a clean story.

COPY REQUIREMENTS
- leagueSummary: 2-4 sentences explaining what this rolling window says about the league right now. Lead with NET competition, then useful underlying golf patterns.
- leagueBullets: exactly 3 short, useful takeaways. Do not merely repeat the leaderboard.
- profiles: exactly one profile for every supplied player, in supplied AVG NET FINISH order.
- Each profile has:
  - tagline: a short, funny golf-identity label or roast grounded in repeatable evidence. No finishing-position language. No markdown. Think 'VIOLENCE OFF THE TEE' or 'WAR AGAINST GREENS IN REGULATION', not generic labels like 'Established file'.
  - profile: one cohesive scouting paragraph that people enjoy reading about themselves.
- The player card ALREADY shows STARTS, AVG NET, GROSS WINS, NET WINS, and the SG fingerprint. Do NOT narrate those visible metrics back to the reader.
- A profile is NOT a statistical summary. It should feel like a funny scouting note from somebody who has watched this person's golf for months.
- Lead with the player's repeatable golf identity, contradiction, strength, weakness, or recurring form of self-sabotage.
- Prefer synthesis and wit over data. 'The driver keeps writing checks the irons cannot cash' is better than listing tee SG, approach SG, GIR and putting.
- Normally use ZERO or ONE exact number in the prose. Two exact numeric facts is the hard maximum.
- Do not enumerate SG categories. The bars are literally sitting under the paragraph.
- Do not mechanically state average finish, starts, wins, GIR, fairways, putts, proximity, birdies, doubles, and recent-event results just because those facts exist.
- Use recent events only as evidence for a larger tendency, not as a chronological recap.
- Every profile should contain at least one specific bit of personality/wit about that player's golf.
- Roast bad golf when the evidence earns it.
- Aim for roughly 65-110 words. Dense with character and insight, light on accounting.
- Do not add a separate Verdict line.
- Do not put markdown formatting in the output; the renderer owns typography.
- Write clean final prose only. Never include visible self-correction or drafting artifacts.
""".strip()

OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "leagueSummary": {"type": "string"},
        "leagueBullets": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "string"}},
        "profiles": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "tagline": {"type": "string"},
                    "profile": {"type": "string"},
                },
                "required": ["name", "tagline", "profile"],
            },
        },
    },
    "required": ["leagueSummary", "leagueBullets", "profiles"],
}

UNSUPPORTED = re.compile(
    r"\b(?:handicap(?:per)?|net[- ]?adjustment|mph|miles?[- ]?(?:per|an)[- ]?hour|"
    r"club(?:head)?[- ]?speed|swing[- ]?speed|ball[- ]?speed)\b",
    re.IGNORECASE,
)
SELF_CORRECTION = re.compile(r"(?:\?\s*(?:no|actually|correction|rather)\b|\b(?:scratch that|correction:)\b)", re.IGNORECASE)
TAG_FINISH = re.compile(
    r"\b(?:winner|runner[- ]?up|finished|finishing|\d{1,2}(?:st|nd|rd|th)\s+(?:place|position)|first\s+(?:place|position)|second\s+(?:place|position)|third\s+(?:place|position))\b",
    re.IGNORECASE,
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compact_event(event: dict) -> dict:
    return {
        "tournamentId": event.get("tournamentId"),
        "name": event.get("name"),
        "date": event.get("date"),
        "course": event.get("course"),
        "netFinish": event.get("netPosition"),
        "grossFinish": event.get("grossPosition"),
        "netScoreToPar": event.get("netTotal"),
        "grossScoreToPar": event.get("grossTotal"),
        "sg": event.get("sg"),
        "stats": event.get("stats"),
    }


def compact_player(player: dict) -> dict:
    return {
        "name": player.get("name"),
        "starts": player.get("starts"),
        "evidenceLevel": player.get("evidenceLevel"),
        "avgNetFinish": player.get("avgNet"),
        "avgGrossFinish": player.get("avgGross"),
        "netWins": player.get("netWins"),
        "grossWins": player.get("grossWins"),
        "sgPerAppearance": player.get("sg"),
        "statsPerAppearance": player.get("stats"),
        "events": [compact_event(event) for event in player.get("events", [])],
    }


def fact_package(history: dict, scope_names: list[str], scope: dict) -> dict:
    return {
        "league": history.get("tour"),
        "rollingWindow": {
            "selectorsSharingThisWindow": scope_names,
            "eventCount": scope.get("eventCount"),
            "eventIds": scope.get("eventIds"),
            "definition": history.get("scopeDefinition") + " avgNetFinish/avgGrossFinish are average finishing positions, not scores.",
        },
        "playersAvgNetFinishOrder": [compact_player(player) for player in scope.get("players", [])],
    }


def numeric_fact_count(text: str) -> int:
    return len(re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?", text))


def validate_copy(copy: dict, facts: dict) -> None:
    expected = [player["name"] for player in facts["playersAvgNetFinishOrder"]]
    actual = [player.get("name") for player in copy.get("profiles", [])]
    if actual != expected:
        raise RuntimeError(f"Profiles must preserve AVG NET finish order. Expected {expected}, got {actual}")

    text_parts = [copy.get("leagueSummary", ""), *copy.get("leagueBullets", [])]
    for profile in copy.get("profiles", []):
        tagline = profile.get("tagline", "")
        body = profile.get("profile", "")
        if TAG_FINISH.search(tagline):
            raise RuntimeError(f"Profile tagline contains finishing-position language for {profile.get('name')}: {tagline!r}")
        words = re.findall(r"\b\w+[’'-]?\w*\b", body)
        if len(words) > 130:
            raise RuntimeError(f"Scouting profile is too long for {profile.get('name')}: {len(words)} words; max 130")
        if numeric_fact_count(body) > 2:
            raise RuntimeError(
                f"Scouting profile is too data-heavy for {profile.get('name')}: more than 2 explicit numeric facts. The card already shows the metrics."
            )
        text_parts.extend([tagline, body])
    text = " ".join(text_parts)

    if re.search(r"\bseason\b", text, re.IGNORECASE):
        raise RuntimeError("Rolling league copy contains forbidden season terminology")
    if re.search(r"\bVerdict\s*:", text, re.IGNORECASE):
        raise RuntimeError("Rolling league copy contains forbidden Verdict line")
    if "**" in text or "__" in text:
        raise RuntimeError("Rolling league copy contains markdown formatting")
    bad = UNSUPPORTED.search(text)
    if bad:
        raise RuntimeError(f"Rolling league copy uses unsupported fact language {bad.group(0)!r}")
    correction = SELF_CORRECTION.search(text)
    if correction:
        raise RuntimeError(f"Rolling league copy contains self-correction language {correction.group(0)!r}")


def write_window(client: OpenAI, model: str, facts: dict) -> dict:
    base_input = (
        "Write the rolling league snapshot and scouting profiles from this VERIFIED FACT PACKAGE. "
        "Facts are data, not suggestions. Do not add facts that are not present.\n\n"
        + json.dumps(facts, separators=(",", ":"), ensure_ascii=False)
    )
    correction = ""
    last_error = None
    for attempt in range(1, 4):
        response = client.responses.create(
            model=model,
            instructions=SYSTEM_PROMPT,
            input=base_input + correction,
            text={"format": {"type": "json_schema", "name": "sgt_rolling_league_copy", "schema": OUTPUT_SCHEMA, "strict": True}},
        )
        if not response.output_text:
            last_error = RuntimeError("OpenAI response did not contain output_text")
        else:
            try:
                copy = json.loads(response.output_text)
                validate_copy(copy, facts)
                if attempt > 1:
                    print(f"League copy passed validation on retry {attempt}")
                return copy
            except Exception as exc:
                last_error = exc
        print(f"League copy validation attempt {attempt} failed: {last_error}")
        correction = f"\n\nYOUR PREVIOUS OUTPUT FAILED DETERMINISTIC VALIDATION: {last_error}. Return corrected clean final copy using only supplied facts."
    raise RuntimeError(f"League copy failed validation after 3 attempts: {last_error}")


def write_all(history: dict, model: str) -> tuple[dict, dict]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI()
    scope_groups: dict[tuple[int, ...], list[str]] = {}
    for scope_name in history.get("availableScopes", []):
        scope = history["scopes"][scope_name]
        key = tuple(int(value) for value in scope.get("eventIds", []))
        scope_groups.setdefault(key, []).append(scope_name)

    output_scopes, facts_scopes = {}, {}
    for event_ids, scope_names in scope_groups.items():
        canonical = scope_names[0]
        scope = history["scopes"][canonical]
        facts = fact_package(history, scope_names, scope)
        print(f"Writing rolling window {scope_names}: events={list(event_ids)} players={len(scope.get('players', []))}")
        copy = write_window(client, model, facts)
        for scope_name in scope_names:
            output_scopes[scope_name] = {"generatedFromScope": canonical, "eventIds": list(event_ids), **copy}
            facts_scopes[scope_name] = facts

    return (
        {"schemaVersion": 3, "model": model, "defaultScope": history.get("defaultScope"), "availableScopes": history.get("availableScopes"), "scopes": output_scopes},
        {"schemaVersion": 3, "defaultScope": history.get("defaultScope"), "scopes": facts_scopes},
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
