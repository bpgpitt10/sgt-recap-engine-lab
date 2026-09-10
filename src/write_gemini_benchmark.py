from __future__ import annotations

import argparse
import copy as copylib
import json
import os
import re
import time
from pathlib import Path

from google import genai
from google.genai import types

# Importing this module applies the exact High Loft editorial prompt and
# fact-package override to write_recap.
import write_high_loft_recap  # noqa: F401
import write_recap
from validate_recap_copy import validate as factual_validate

ROOT = Path(__file__).resolve().parents[1]
MIN_CALL_INTERVAL_SECONDS = float(os.environ.get("GEMINI_MIN_CALL_INTERVAL_SECONDS", "13"))
_last_api_call_at = 0.0

BATCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
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
    },
    "required": ["players", "carnage"],
}

BATCH_PROMPT = write_recap.SYSTEM_PROMPT + r"""

BATCH MODE
- This request contains only a subset of completed players.
- Return ONLY the players and carnage keys required by the response schema.
- players: exactly one entry for every player in playersNetOrder, preserving that order.
- carnage: exactly one entry for every player in carnageOrder, preserving that order.
- Treat this as finished publishable copy, not notes or abbreviated placeholders.
"""


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def usage_dict(response) -> dict:
    meta = getattr(response, "usage_metadata", None)
    out: dict = {}
    if meta is not None:
        for key in (
            "prompt_token_count",
            "candidates_token_count",
            "thoughts_token_count",
            "total_token_count",
            "cached_content_token_count",
        ):
            value = getattr(meta, key, None)
            if value is not None:
                out[key] = value
    return out


def merge_usage(total: dict, add: dict) -> None:
    for key, value in add.items():
        total[key] = total.get(key, 0) + value


def wait_for_free_tier_slot() -> None:
    global _last_api_call_at
    elapsed = time.monotonic() - _last_api_call_at
    remaining = MIN_CALL_INTERVAL_SECONDS - elapsed
    if _last_api_call_at and remaining > 0:
        print(f"Free-tier rate governor: spacing Gemini calls by {MIN_CALL_INTERVAL_SECONDS:.0f}s")
        time.sleep(remaining)
    _last_api_call_at = time.monotonic()


def gemini_call(client, *, model: str, contents: str):
    last_error: Exception | None = None
    for api_attempt in range(1, 5):
        wait_for_free_tier_slot()
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=BATCH_PROMPT,
                    response_mime_type="application/json",
                    response_json_schema=BATCH_SCHEMA,
                    max_output_tokens=8192,
                    thinking_config=types.ThinkingConfig(thinking_level="MEDIUM"),
                ),
            )
        except Exception as exc:
            last_error = exc
            text = str(exc).upper()
            transient = any(marker in text for marker in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))
            if not transient or api_attempt == 4:
                raise
            print(f"Gemini transient API failure on call {api_attempt}/4; next retry remains rate-governed: {exc}")
    raise RuntimeError(f"Gemini call failed: {last_error}")


def batch_facts(full_facts: dict, names: list[str]) -> dict:
    wanted = set(names)
    facts = copylib.deepcopy(full_facts)
    facts["playersNetOrder"] = [p for p in full_facts["playersNetOrder"] if p["name"] in wanted]
    facts["carnageOrder"] = [c for c in full_facts["carnageOrder"] if c["name"] in wanted]
    return facts


def validate_batch(batch_copy: dict, facts: dict) -> None:
    write_recap.validate_copy(batch_copy, facts)
    factual_validate(batch_copy, facts)
    if re.search(r"\b(?:placeholder|todo|tbd)\b", " ".join(
        [p.get("body", "") for p in batch_copy.get("players", [])]
        + [c.get("commentary", "") for c in batch_copy.get("carnage", [])]
    ), re.I):
        raise RuntimeError("Batch copy contains placeholder text")


def generate_batch(client, *, model: str, facts: dict, batch_number: int) -> tuple[dict, dict]:
    base_input = (
        "Write publishable recap copy for ONLY the players in this VERIFIED FACT PACKAGE. "
        "Facts are data, not suggestions. Do not add facts that are not present.\n\n"
        + json.dumps(facts, separators=(",", ":"), ensure_ascii=False)
    )
    correction = ""
    last_error: Exception | None = None

    for attempt in range(1, 4):
        response = gemini_call(client, model=model, contents=base_input + correction)
        if not response.text:
            last_error = RuntimeError("Gemini response did not contain text")
        else:
            try:
                result = json.loads(response.text)
                validate_batch(result, facts)
                print(f"Gemini batch {batch_number} passed deterministic validation on attempt {attempt}")
                return result, usage_dict(response)
            except Exception as exc:
                last_error = exc

        print(f"Gemini batch {batch_number} validation attempt {attempt} failed: {last_error}")
        correction = (
            "\n\nYOUR PREVIOUS OUTPUT FAILED DETERMINISTIC VALIDATION: "
            f"{last_error}. Return corrected JSON that fixes this exact issue without changing verified facts."
        )

    raise RuntimeError(f"Gemini batch {batch_number} failed validation after 3 attempts: {last_error}")


def generate(analysis: dict, config: dict, history: dict | None, model: str, batch_size: int, max_batches: int | None) -> tuple[dict, dict, dict]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    full_facts = write_recap.build_fact_package(analysis, config, history)
    client = genai.Client(api_key=api_key)
    all_players: list[dict] = []
    carnage_by_name: dict[str, dict] = {}
    usage: dict = {}
    batches: list[dict] = []
    ordered_names = [p["name"] for p in full_facts["playersNetOrder"]]
    selected_names = ordered_names[: batch_size * max_batches] if max_batches else ordered_names
    selected_set = set(selected_names)

    for start in range(0, len(selected_names), batch_size):
        names = selected_names[start:start + batch_size]
        facts = batch_facts(full_facts, names)
        batch_number = start // batch_size + 1
        print(f"Generating Gemini batch {batch_number}: {', '.join(names)}")
        result, batch_usage = generate_batch(client, model=model, facts=facts, batch_number=batch_number)
        merge_usage(usage, batch_usage)
        all_players.extend(result["players"])
        for item in result["carnage"]:
            carnage_by_name[item["name"]] = item
        batches.append({"batch": batch_number, "players": names, "usage": batch_usage})

    selected_carnage_facts = [c for c in full_facts["carnageOrder"] if c["name"] in selected_set]
    merged_carnage = [carnage_by_name[c["name"]] for c in selected_carnage_facts]
    merged = {"players": all_players, "carnage": merged_carnage}
    actual_players = [p["name"] for p in merged["players"]]
    if actual_players != selected_names:
        raise RuntimeError(f"Merged player order mismatch: expected {selected_names}, got {actual_players}")
    expected_carnage = [c["name"] for c in selected_carnage_facts]
    actual_carnage = [c["name"] for c in merged["carnage"]]
    if actual_carnage != expected_carnage:
        raise RuntimeError(f"Merged Carnage order mismatch: expected {expected_carnage}, got {actual_carnage}")

    return merged, full_facts, {"total": usage, "batches": batches, "selectedPlayers": selected_names}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate batched High Loft player/Carnage copy with Gemini for provider benchmarking only.")
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--history", type=Path, default=Path("data/history.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--facts-output", type=Path)
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"))
    parser.add_argument("--batch-size", type=int, default=3)
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()
    if args.batch_size < 1:
        raise RuntimeError("--batch-size must be at least 1")
    if args.max_batches is not None and args.max_batches < 1:
        raise RuntimeError("--max-batches must be at least 1")

    ap = args.analysis if args.analysis.is_absolute() else ROOT / args.analysis
    hp = args.history if args.history.is_absolute() else ROOT / args.history
    out = args.output if args.output.is_absolute() else ROOT / args.output
    config = load_json(ROOT / "config.json")
    analysis = load_json(ap)
    history = load_json(hp) if hp.exists() else None

    batch_copy, facts, usage = generate(analysis, config, history, args.model, args.batch_size, args.max_batches)
    payload = {
        "provider": "google",
        "model": args.model,
        "mode": "batched-player-carnage-benchmark",
        "batchSize": args.batch_size,
        "maxBatches": args.max_batches,
        "minCallIntervalSeconds": MIN_CALL_INTERVAL_SECONDS,
        "tournamentId": analysis["tournament"]["id"],
        "usage": usage,
        "copy": batch_copy,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.facts_output:
        fp = args.facts_output if args.facts_output.is_absolute() else ROOT / args.facts_output
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Wrote batched Gemini benchmark for tournament {analysis['tournament']['id']} with {args.model}: {out.relative_to(ROOT)}")
    print("Usage:", json.dumps(usage, sort_keys=True))


if __name__ == "__main__":
    main()
