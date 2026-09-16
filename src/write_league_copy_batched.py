from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

import write_league_copy

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_SCHEMA_VERSION = 1
DEFAULT_BATCH_SIZE = 6

PROFILE_BATCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
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
        }
    },
    "required": ["profiles"],
}

SUMMARY_SCHEMA = {
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
    },
    "required": ["leagueSummary", "leagueBullets"],
}

PROFILE_BATCH_INSTRUCTIONS = r"""
BATCHED SCOUTING-FILE MODE
- This request is ONLY for the supplied subset of players.
- Return exactly one profiles entry for every player in playersAvgNetFinishOrder, in that exact order.
- NEVER return a profile for any player not supplied in this batch.
- Do NOT write leagueSummary or leagueBullets in this request.
- Treat these as final publishable scouting files, not notes for another writer.
""".strip()

SUMMARY_INSTRUCTIONS = r"""
LEAGUE-SUMMARY-ONLY MODE
- Return ONLY leagueSummary and exactly three leagueBullets.
- Do NOT write player profiles in this request.
- The supplied package is intentionally compact and league-wide. Use only facts present in it.
- Lead with NET competition, then explain useful underlying gross/SG patterns.
- Do not treat SGT benchmark values as field averages.
""".strip()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def chunks(items: list[dict], size: int) -> list[list[dict]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def profile_batch_facts(full_facts: dict, names: list[str]) -> dict:
    wanted = set(names)
    return {
        "league": full_facts.get("league"),
        "rollingWindow": full_facts.get("rollingWindow"),
        "playersAvgNetFinishOrder": [
            player for player in full_facts.get("playersAvgNetFinishOrder", []) if player.get("name") in wanted
        ],
    }


def summary_player(player: dict) -> dict:
    return {
        "name": player.get("name"),
        "starts": player.get("starts"),
        "evidenceLevel": player.get("evidenceLevel"),
        "avgNetFinish": player.get("avgNetFinish"),
        "avgGrossFinish": player.get("avgGrossFinish"),
        "netWins": player.get("netWins"),
        "grossWins": player.get("grossWins"),
        "sgPerAppearance": player.get("sgPerAppearance"),
        "statsPerAppearance": player.get("statsPerAppearance"),
    }


def sg_extremes(players: list[dict]) -> dict:
    categories = ("tee", "approach", "shortGame", "putting", "teeToGreen", "total")
    result = {}
    for category in categories:
        values: list[tuple[float, str]] = []
        for player in players:
            value = (player.get("sgPerAppearance") or {}).get(category)
            if isinstance(value, (int, float)) and player.get("name"):
                values.append((float(value), player["name"]))
        if values:
            values.sort(key=lambda item: item[0])
            result[category] = {
                "lowest": {"name": values[0][1], "value": values[0][0]},
                "highest": {"name": values[-1][1], "value": values[-1][0]},
            }
    return result


def recent_events(players: list[dict]) -> list[dict]:
    by_id: dict[int, dict] = {}
    for player in players:
        for event in player.get("events", []):
            event_id = event.get("tournamentId")
            if event_id is None:
                continue
            event_id = int(event_id)
            by_id.setdefault(event_id, {
                "tournamentId": event_id,
                "name": event.get("name"),
                "date": event.get("date"),
                "course": event.get("course"),
            })
    return sorted(by_id.values(), key=lambda item: (item.get("date") or "", item["tournamentId"]), reverse=True)


def summary_facts(full_facts: dict) -> dict:
    players = list(full_facts.get("playersAvgNetFinishOrder", []))
    gross_order = sorted(
        players,
        key=lambda player: (
            player.get("avgGrossFinish") if isinstance(player.get("avgGrossFinish"), (int, float)) else 10**9,
            player.get("avgNetFinish") if isinstance(player.get("avgNetFinish"), (int, float)) else 10**9,
            player.get("name") or "",
        ),
    )
    net_win_leaders = sorted(
        players,
        key=lambda player: (
            -(player.get("netWins") or 0),
            player.get("avgNetFinish") if isinstance(player.get("avgNetFinish"), (int, float)) else 10**9,
            player.get("name") or "",
        ),
    )
    gross_win_leaders = sorted(
        players,
        key=lambda player: (
            -(player.get("grossWins") or 0),
            player.get("avgGrossFinish") if isinstance(player.get("avgGrossFinish"), (int, float)) else 10**9,
            player.get("name") or "",
        ),
    )
    return {
        "league": full_facts.get("league"),
        "rollingWindow": full_facts.get("rollingWindow"),
        "playerCount": len(players),
        "recentEvents": recent_events(players),
        "avgNetTop10": [summary_player(player) for player in players[:10]],
        "avgGrossTop10": [summary_player(player) for player in gross_order[:10]],
        "netWinLeaders": [summary_player(player) for player in net_win_leaders[:5] if (player.get("netWins") or 0) > 0],
        "grossWinLeaders": [summary_player(player) for player in gross_win_leaders[:5] if (player.get("grossWins") or 0) > 0],
        "sgCategoryExtremes": sg_extremes(players),
    }


def checkpoint_fingerprint(kind: str, model: str, facts: dict, schema: dict, instructions: str) -> str:
    return canonical_hash({
        "checkpointSchema": CHECKPOINT_SCHEMA_VERSION,
        "kind": kind,
        "model": model,
        "systemPrompt": write_league_copy.SYSTEM_PROMPT,
        "modeInstructions": instructions,
        "outputSchema": schema,
        "facts": facts,
    })


def window_key(facts: dict) -> str:
    event_ids = list((facts.get("rollingWindow") or {}).get("eventIds") or [])
    return f"window-{len(event_ids)}-{canonical_hash(event_ids)[:12]}"


def checkpoint_path(root: Path, key: str, name: str) -> Path:
    return root / key / f"{name}.json"


def save_checkpoint(path: Path, *, kind: str, key: str, model: str, fingerprint: str, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schemaVersion": CHECKPOINT_SCHEMA_VERSION,
        "kind": kind,
        "windowKey": key,
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


def validate_profile_batch(payload: dict, facts: dict) -> None:
    candidate = {
        "leagueSummary": "",
        "leagueBullets": [],
        "profiles": payload.get("profiles", []),
    }
    write_league_copy.validate_copy(candidate, facts)


def validate_summary(payload: dict, full_facts: dict) -> None:
    bullets = payload.get("leagueBullets")
    if not isinstance(bullets, list) or len(bullets) != 3:
        raise RuntimeError("League summary must contain exactly 3 bullets")
    validation_facts = {
        **full_facts,
        "playersAvgNetFinishOrder": [],
    }
    candidate = {
        "leagueSummary": payload.get("leagueSummary", ""),
        "leagueBullets": bullets,
        "profiles": [],
    }
    write_league_copy.validate_copy(candidate, validation_facts)


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
            instructions=write_league_copy.SYSTEM_PROMPT + "\n\n" + mode_instructions,
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


def assemble_profiles(full_facts: dict, payloads: list[dict]) -> list[dict]:
    by_name = {}
    for payload in payloads:
        for profile in payload.get("profiles", []):
            by_name[profile["name"]] = profile
    expected = [player["name"] for player in full_facts.get("playersAvgNetFinishOrder", [])]
    missing = [name for name in expected if name not in by_name]
    if missing:
        raise RuntimeError(f"Incomplete profile batch assembly. Missing profiles={missing}")
    return [by_name[name] for name in expected]


def scope_groups(history: dict) -> list[tuple[tuple[int, ...], list[str]]]:
    groups: dict[tuple[int, ...], list[str]] = {}
    for scope_name in history.get("availableScopes", []):
        scope = history["scopes"][scope_name]
        key = tuple(int(value) for value in scope.get("eventIds", []))
        groups.setdefault(key, []).append(scope_name)
    return list(groups.items())


def write_batched_all(
    history: dict,
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

    groups = scope_groups(history)
    client = OpenAI()
    output_scopes: dict[str, dict] = {}
    facts_scopes: dict[str, dict] = {}
    manifest_windows: list[dict] = []
    total_new_batches = 0
    total_reused_batches = 0

    for group_index, (event_ids, scope_names) in enumerate(groups, start=1):
        canonical = scope_names[0]
        scope = history["scopes"][canonical]
        facts = write_league_copy.fact_package(history, scope_names, scope)
        key = window_key(facts)
        players = list(facts.get("playersAvgNetFinishOrder", []))
        player_groups = chunks(players, batch_size)
        batch_payloads: list[dict] = []
        reused = 0
        generated = 0

        print(
            f"Writing rolling window {scope_names}: events={list(event_ids)} "
            f"players={len(players)} batches={len(player_groups)} key={key}"
        )

        for index, player_group in enumerate(player_groups, start=1):
            names = [player["name"] for player in player_group]
            batch_facts = profile_batch_facts(facts, names)
            fingerprint = checkpoint_fingerprint(
                "profiles", model, batch_facts, PROFILE_BATCH_SCHEMA, PROFILE_BATCH_INSTRUCTIONS
            )
            path = checkpoint_path(checkpoint_dir, key, f"batch-{index:03d}")
            payload = load_checkpoint(path, fingerprint=fingerprint)
            if payload is not None:
                try:
                    validate_profile_batch(payload, batch_facts)
                    batch_payloads.append(payload)
                    reused += 1
                    total_reused_batches += 1
                    print(f"Reused profile batch {index}/{len(player_groups)}: {', '.join(names)}")
                    continue
                except Exception as exc:
                    print(f"Checkpoint {path} failed current validation and will be regenerated: {exc}")

            print(f"Generating profile batch {index}/{len(player_groups)}: {', '.join(names)}")
            payload = generate_json(
                client,
                model=model,
                facts=batch_facts,
                schema=PROFILE_BATCH_SCHEMA,
                schema_name="sgt_league_profile_batch",
                mode_instructions=PROFILE_BATCH_INSTRUCTIONS,
                task="Write final scouting-file copy for ONLY this player batch.",
                validator=lambda value, bf=batch_facts: validate_profile_batch(value, bf),
            )
            save_checkpoint(
                path,
                kind="profiles",
                key=key,
                model=model,
                fingerprint=fingerprint,
                payload=payload,
            )
            batch_payloads.append(payload)
            generated += 1
            total_new_batches += 1
            print(f"Checkpointed validated profile batch {index}/{len(player_groups)} at {path}")

            remaining_profile_work = index < len(player_groups) or group_index < len(groups)
            if max_new_batches and total_new_batches >= max_new_batches and remaining_profile_work:
                raise RuntimeError(
                    f"Intentional checkpoint pause after {total_new_batches} newly generated profile batch(es); "
                    "rerun the same command to resume from validated checkpoints."
                )

        profiles = assemble_profiles(facts, batch_payloads)
        compact_summary_facts = summary_facts(facts)
        summary_fp = checkpoint_fingerprint(
            "summary", model, compact_summary_facts, SUMMARY_SCHEMA, SUMMARY_INSTRUCTIONS
        )
        summary_path = checkpoint_path(checkpoint_dir, key, "summary")
        summary = load_checkpoint(summary_path, fingerprint=summary_fp)
        if summary is not None:
            try:
                validate_summary(summary, facts)
                print(f"Reused league summary checkpoint for {scope_names}")
            except Exception as exc:
                print(f"Summary checkpoint failed current validation and will be regenerated: {exc}")
                summary = None

        if summary is None:
            print(f"Generating compact league summary for {scope_names}")
            summary = generate_json(
                client,
                model=model,
                facts=compact_summary_facts,
                schema=SUMMARY_SCHEMA,
                schema_name="sgt_league_window_summary",
                mode_instructions=SUMMARY_INSTRUCTIONS,
                task="Write final rolling league summary and exactly three useful bullets.",
                validator=lambda value, ff=facts: validate_summary(value, ff),
            )
            save_checkpoint(
                summary_path,
                kind="summary",
                key=key,
                model=model,
                fingerprint=summary_fp,
                payload=summary,
            )
            print(f"Checkpointed validated league summary at {summary_path}")

        final_copy = {
            "leagueSummary": summary["leagueSummary"],
            "leagueBullets": summary["leagueBullets"],
            "profiles": profiles,
        }
        write_league_copy.validate_copy(final_copy, facts)

        for scope_name in scope_names:
            output_scopes[scope_name] = {
                "generatedFromScope": canonical,
                "eventIds": list(event_ids),
                **final_copy,
            }
            facts_scopes[scope_name] = facts

        manifest_windows.append({
            "windowKey": key,
            "scopes": scope_names,
            "eventIds": list(event_ids),
            "players": len(profiles),
            "batchCount": len(player_groups),
            "reusedBatches": reused,
            "newBatches": generated,
            "complete": True,
        })

    output = {
        "schemaVersion": 3,
        "model": model,
        "defaultScope": history.get("defaultScope"),
        "availableScopes": history.get("availableScopes"),
        "scopes": output_scopes,
    }
    facts_output = {
        "schemaVersion": 3,
        "defaultScope": history.get("defaultScope"),
        "scopes": facts_scopes,
    }
    manifest = {
        "schemaVersion": CHECKPOINT_SCHEMA_VERSION,
        "requestedModel": model,
        "batchSize": batch_size,
        "windowCount": len(groups),
        "newBatches": total_new_batches,
        "reusedBatches": total_reused_batches,
        "windows": manifest_windows,
        "complete": True,
    }
    manifest_path = checkpoint_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output, facts_output, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Write rolling league copy in validated resumable AI batches.")
    parser.add_argument("history", type=Path, default=Path("data/history.json"), nargs="?")
    parser.add_argument("--output", type=Path, default=Path("data/league-copy.json"))
    parser.add_argument("--facts-output", type=Path, default=Path("data/league-facts.json"))
    parser.add_argument("--checkpoint-dir", type=Path, default=Path("data/ai-checkpoints/league"))
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("OPENAI_LEAGUE_BATCH_SIZE", str(DEFAULT_BATCH_SIZE))))
    parser.add_argument("--max-new-batches", type=int, default=0, help="Testing aid: intentionally stop after N newly generated profile batches.")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"))
    args = parser.parse_args()

    history_path = args.history if args.history.is_absolute() else ROOT / args.history
    output = args.output if args.output.is_absolute() else ROOT / args.output
    facts_output = args.facts_output if args.facts_output.is_absolute() else ROOT / args.facts_output
    checkpoint_dir = args.checkpoint_dir if args.checkpoint_dir.is_absolute() else ROOT / args.checkpoint_dir

    copy, facts, manifest = write_batched_all(
        load_json(history_path),
        args.model,
        checkpoint_dir=checkpoint_dir,
        batch_size=args.batch_size,
        max_new_batches=args.max_new_batches,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(copy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    facts_output.parent.mkdir(parents=True, exist_ok=True)
    facts_output.write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    display_output = output.relative_to(ROOT) if output.is_relative_to(ROOT) else output
    print(f"Wrote complete batched league copy using {args.model}: {display_output}")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
