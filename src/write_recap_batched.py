from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

import write_recap
from validate_recap_copy import validate as factual_validate

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_SCHEMA_VERSION = 1
DEFAULT_BATCH_SIZE = 6

BATCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
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
    },
    "required": ["carnage", "players"],
}

NARRATIVE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "thirtySeconds": {"type": "string"},
        "latestTournamentTeaser": {"type": "string"},
        "stateOfLeague": {"type": "string"},
    },
    "required": ["thirtySeconds", "latestTournamentTeaser", "stateOfLeague"],
}

BATCH_INSTRUCTIONS = r"""
BATCHED GENERATION MODE
- This request is ONLY for the supplied subset of players.
- Return exactly one players entry for every player in playersNetOrder, in that exact order.
- Return exactly one carnage entry for every player in carnageOrder, in that exact order.
- Do NOT write thirtySeconds, latestTournamentTeaser, or stateOfLeague in this request.
- Treat this as final publishable player/Carnage copy, not notes for another writer.
""".strip()

NARRATIVE_INSTRUCTIONS = r"""
NARRATIVE-ONLY GENERATION MODE
- Return ONLY thirtySeconds, latestTournamentTeaser, and stateOfLeague.
- Do NOT write player cards or Carnage commentary in this request.
- The supplied package is intentionally compact. Use only facts present in it.
- Lead the event story with the configured primary competition.
- Use SG/category leaders only as SGT-relative performance evidence.
""".strip()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def chunks(items: list[dict], size: int) -> list[list[dict]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def subset_facts(full_facts: dict, player_names: list[str]) -> dict:
    names = set(player_names)
    return {
        "league": full_facts.get("league"),
        "tournament": full_facts.get("tournament"),
        "winners": full_facts.get("winners"),
        "leaderboard": full_facts.get("leaderboard"),
        "carnageOrder": [item for item in full_facts.get("carnageOrder", []) if item.get("name") in names],
        "playersNetOrder": [item for item in full_facts.get("playersNetOrder", []) if item.get("name") in names],
        "historicalContext": full_facts.get("historicalContext"),
    }


def sg_leaders(players: list[dict]) -> dict:
    categories = ("tee", "approach", "shortGame", "putting", "teeToGreen", "total")
    output = {}
    for category in categories:
        values = []
        for player in players:
            value = (player.get("sg") or {}).get(category)
            if isinstance(value, (int, float)):
                values.append((float(value), player.get("name")))
        if not values:
            continue
        values.sort(key=lambda item: item[0])
        output[category] = {
            "lowest": {"name": values[0][1], "value": values[0][0]},
            "highest": {"name": values[-1][1], "value": values[-1][0]},
        }
    return output


def narrative_facts(full_facts: dict) -> dict:
    players = list(full_facts.get("playersNetOrder", []))
    by_name = {player.get("name"): player for player in players}
    interesting_names: list[str] = []

    for player in players[:5]:
        name = player.get("name")
        if name and name not in interesting_names:
            interesting_names.append(name)
    for standing in (full_facts.get("leaderboard") or {}).get("gross", [])[:5]:
        name = standing.get("name")
        if name and name not in interesting_names:
            interesting_names.append(name)
    for leader in sg_leaders(players).values():
        for side in ("highest", "lowest"):
            name = (leader.get(side) or {}).get("name")
            if name and name not in interesting_names:
                interesting_names.append(name)

    key_players = []
    for name in interesting_names[:12]:
        player = by_name.get(name)
        if not player:
            continue
        key_players.append({
            "name": name,
            "leaderboard": player.get("leaderboard"),
            "sg": player.get("sg"),
            "worstHole": player.get("worstHole"),
            "priorHistory": player.get("priorHistory"),
        })

    return {
        "league": full_facts.get("league"),
        "tournament": full_facts.get("tournament"),
        "fieldSize": len(players),
        "winners": full_facts.get("winners"),
        "leaderboard": {
            "netTop10": ((full_facts.get("leaderboard") or {}).get("net") or [])[:10],
            "grossTop10": ((full_facts.get("leaderboard") or {}).get("gross") or [])[:10],
        },
        "sgCategoryExtremes": sg_leaders(players),
        "carnageChampion": (full_facts.get("carnageOrder") or [None])[0],
        "keyPlayers": key_players,
        "historicalContext": full_facts.get("historicalContext"),
    }


def checkpoint_fingerprint(kind: str, model: str, facts: dict, schema: dict, instructions: str) -> str:
    return canonical_hash({
        "checkpointSchema": CHECKPOINT_SCHEMA_VERSION,
        "kind": kind,
        "model": model,
        "systemPrompt": write_recap.SYSTEM_PROMPT,
        "modeInstructions": instructions,
        "outputSchema": schema,
        "facts": facts,
    })


def checkpoint_path(root: Path, tournament_id: int, name: str) -> Path:
    return root / str(tournament_id) / f"{name}.json"


def save_checkpoint(path: Path, *, kind: str, tournament_id: int, model: str, fingerprint: str, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schemaVersion": CHECKPOINT_SCHEMA_VERSION,
        "kind": kind,
        "tournamentId": tournament_id,
        "requestedModel": model,
        "fingerprint": fingerprint,
        "payload": payload,
    }
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_checkpoint(path: Path, *, fingerprint: str) -> dict | None:
    if not path.exists():
        return None
    try:
        record = load_json(path)
    except Exception as exc:
        print(f"Ignoring unreadable checkpoint {path}: {exc}")
        return None
    if record.get("schemaVersion") != CHECKPOINT_SCHEMA_VERSION or record.get("fingerprint") != fingerprint:
        print(f"Ignoring stale checkpoint {path}")
        return None
    payload = record.get("payload")
    if not isinstance(payload, dict):
        print(f"Ignoring malformed checkpoint {path}")
        return None
    return payload


def dummy_copy(partial: dict) -> dict:
    return {
        "thirtySeconds": "",
        "latestTournamentTeaser": "",
        "carnage": partial.get("carnage", []),
        "players": partial.get("players", []),
        "stateOfLeague": "",
    }


def validate_batch(partial: dict, facts: dict) -> None:
    candidate = dummy_copy(partial)
    write_recap.validate_copy(candidate, facts)
    factual_validate(candidate, facts)


def generate_json(
    client: Any,
    *,
    model: str,
    facts: dict,
    schema: dict,
    schema_name: str,
    mode_instructions: str,
    task: str,
    validator,
) -> dict:
    base_input = task + "\n\nVERIFIED FACT PACKAGE:\n" + json.dumps(facts, separators=(",", ":"), ensure_ascii=False)
    correction = ""
    last_error: Exception | None = None
    for attempt in range(1, 4):
        response = client.responses.create(
            model=model,
            instructions=write_recap.SYSTEM_PROMPT + "\n\n" + mode_instructions,
            input=base_input + correction,
            text={"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}},
        )
        if not response.output_text:
            last_error = RuntimeError("OpenAI response did not contain output_text")
        else:
            try:
                payload = json.loads(response.output_text)
                validator(payload)
                if attempt > 1:
                    print(f"{schema_name} passed deterministic validation on retry {attempt}")
                return payload
            except Exception as exc:
                last_error = exc
        print(f"{schema_name} validation attempt {attempt} failed: {last_error}")
        correction = (
            f"\n\nYOUR PREVIOUS OUTPUT FAILED DETERMINISTIC VALIDATION: {last_error}. "
            "Return corrected clean final copy using only supplied facts."
        )
    raise RuntimeError(f"{schema_name} failed deterministic validation after 3 attempts: {last_error}")


def assemble_batch_copy(full_facts: dict, batch_payloads: list[dict]) -> tuple[list[dict], list[dict]]:
    players_by_name = {}
    carnage_by_name = {}
    for payload in batch_payloads:
        for item in payload.get("players", []):
            players_by_name[item["name"]] = item
        for item in payload.get("carnage", []):
            carnage_by_name[item["name"]] = item

    player_names = [item["name"] for item in full_facts.get("playersNetOrder", [])]
    carnage_names = [item["name"] for item in full_facts.get("carnageOrder", [])]
    missing_players = [name for name in player_names if name not in players_by_name]
    missing_carnage = [name for name in carnage_names if name not in carnage_by_name]
    if missing_players or missing_carnage:
        raise RuntimeError(f"Incomplete batch assembly. Missing players={missing_players}; missing Carnage={missing_carnage}")
    return [players_by_name[name] for name in player_names], [carnage_by_name[name] for name in carnage_names]


def write_batched_recap(
    analysis: dict,
    config: dict,
    history: dict | None,
    model: str,
    *,
    checkpoint_dir: Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_new_batches: int = 0,
) -> tuple[dict, dict, dict]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")
    if batch_size < 1:
        raise RuntimeError("batch_size must be at least 1")

    facts = write_recap.build_fact_package(analysis, config, history)
    tournament_id = int((analysis.get("tournament") or {}).get("id"))
    player_groups = chunks(list(facts.get("playersNetOrder", [])), batch_size)
    client = OpenAI()
    batch_payloads: list[dict] = []
    generated_now = 0
    reused = 0

    for index, player_group in enumerate(player_groups, start=1):
        names = [player["name"] for player in player_group]
        batch_facts = subset_facts(facts, names)
        fingerprint = checkpoint_fingerprint("players-carnage", model, batch_facts, BATCH_SCHEMA, BATCH_INSTRUCTIONS)
        path = checkpoint_path(checkpoint_dir, tournament_id, f"batch-{index:03d}")
        payload = load_checkpoint(path, fingerprint=fingerprint)
        if payload is not None:
            try:
                validate_batch(payload, batch_facts)
                reused += 1
                batch_payloads.append(payload)
                print(f"Reused validated recap batch {index}/{len(player_groups)}: {', '.join(names)}")
                continue
            except Exception as exc:
                print(f"Checkpoint {path} failed current validation and will be regenerated: {exc}")

        print(f"Generating recap batch {index}/{len(player_groups)}: {', '.join(names)}")
        payload = generate_json(
            client,
            model=model,
            facts=batch_facts,
            schema=BATCH_SCHEMA,
            schema_name="sgt_recap_player_carnage_batch",
            mode_instructions=BATCH_INSTRUCTIONS,
            task="Write final player-by-player and Carnage copy for ONLY this batch.",
            validator=lambda value, bf=batch_facts: validate_batch(value, bf),
        )
        save_checkpoint(
            path,
            kind="players-carnage",
            tournament_id=tournament_id,
            model=model,
            fingerprint=fingerprint,
            payload=payload,
        )
        batch_payloads.append(payload)
        generated_now += 1
        print(f"Checkpointed validated recap batch {index}/{len(player_groups)} at {path}")
        if max_new_batches and generated_now >= max_new_batches and index < len(player_groups):
            raise RuntimeError(
                f"Intentional checkpoint pause after {generated_now} newly generated batch(es); "
                "rerun the same command to resume from validated checkpoints."
            )

    players, carnage = assemble_batch_copy(facts, batch_payloads)
    compact_narrative_facts = narrative_facts(facts)
    narrative_fp = checkpoint_fingerprint(
        "narrative", model, compact_narrative_facts, NARRATIVE_SCHEMA, NARRATIVE_INSTRUCTIONS
    )
    narrative_path = checkpoint_path(checkpoint_dir, tournament_id, "narrative")
    narrative = load_checkpoint(narrative_path, fingerprint=narrative_fp)

    def validate_narrative(value: dict) -> None:
        candidate = {
            "thirtySeconds": value.get("thirtySeconds", ""),
            "latestTournamentTeaser": value.get("latestTournamentTeaser", ""),
            "carnage": carnage,
            "players": players,
            "stateOfLeague": value.get("stateOfLeague", ""),
        }
        write_recap.validate_copy(candidate, facts)
        factual_validate(candidate, facts)

    if narrative is not None:
        try:
            validate_narrative(narrative)
            print("Reused validated tournament narrative checkpoint")
        except Exception as exc:
            print(f"Narrative checkpoint failed current validation and will be regenerated: {exc}")
            narrative = None

    if narrative is None:
        print("Generating compact tournament narrative")
        narrative = generate_json(
            client,
            model=model,
            facts=compact_narrative_facts,
            schema=NARRATIVE_SCHEMA,
            schema_name="sgt_recap_tournament_narrative",
            mode_instructions=NARRATIVE_INSTRUCTIONS,
            task="Write final tournament-level narrative copy only.",
            validator=validate_narrative,
        )
        save_checkpoint(
            narrative_path,
            kind="narrative",
            tournament_id=tournament_id,
            model=model,
            fingerprint=narrative_fp,
            payload=narrative,
        )
        print(f"Checkpointed validated tournament narrative at {narrative_path}")

    final_copy = {
        "thirtySeconds": narrative["thirtySeconds"],
        "latestTournamentTeaser": narrative["latestTournamentTeaser"],
        "carnage": carnage,
        "players": players,
        "stateOfLeague": narrative["stateOfLeague"],
    }
    write_recap.validate_copy(final_copy, facts)
    factual_validate(final_copy, facts)

    manifest = {
        "schemaVersion": CHECKPOINT_SCHEMA_VERSION,
        "tournamentId": tournament_id,
        "requestedModel": model,
        "batchSize": batch_size,
        "batchCount": len(player_groups),
        "players": len(players),
        "reusedBatches": reused,
        "newBatches": generated_now,
        "checkpointDir": str(checkpoint_dir),
        "complete": True,
    }
    manifest_path = checkpoint_path(checkpoint_dir, tournament_id, "manifest")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return final_copy, facts, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a recap in validated resumable AI batches.")
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--history", type=Path, default=Path("data/history.json"))
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--facts-output", type=Path)
    parser.add_argument("--checkpoint-dir", type=Path, default=Path("data/ai-checkpoints/recap"))
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("OPENAI_RECAP_BATCH_SIZE", str(DEFAULT_BATCH_SIZE))))
    parser.add_argument("--max-new-batches", type=int, default=0, help="Testing aid: intentionally stop after N newly generated player batches.")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"))
    args = parser.parse_args()

    ap = args.analysis if args.analysis.is_absolute() else ROOT / args.analysis
    hp = args.history if args.history.is_absolute() else ROOT / args.history
    cp = args.config if args.config.is_absolute() else ROOT / args.config
    checkpoint_dir = args.checkpoint_dir if args.checkpoint_dir.is_absolute() else ROOT / args.checkpoint_dir
    analysis = load_json(ap)
    config = load_json(cp)
    history = load_json(hp) if hp.exists() else None

    copy, facts, manifest = write_batched_recap(
        analysis,
        config,
        history,
        args.model,
        checkpoint_dir=checkpoint_dir,
        batch_size=args.batch_size,
        max_new_batches=args.max_new_batches,
    )
    tournament_id = int(analysis["tournament"]["id"])
    out = args.output or Path("data") / "copy" / f"{tournament_id}.json"
    out = out if out.is_absolute() else ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(copy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.facts_output:
        fp = args.facts_output if args.facts_output.is_absolute() else ROOT / args.facts_output
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Wrote complete batched recap for tournament {tournament_id} with model {args.model}: {out.relative_to(ROOT)}")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
