from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from google import genai
from google.genai import types

# Importing this module applies the exact High Loft editorial prompt,
# fact-package override, and validators to write_recap.
import write_high_loft_recap  # noqa: F401
import write_recap
from validate_recap_copy import validate as factual_validate

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def generate(analysis: dict, config: dict, history: dict | None, model: str) -> tuple[dict, dict, dict]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    facts = write_recap.build_fact_package(analysis, config, history)
    base_input = (
        "Write the recap copy from this VERIFIED FACT PACKAGE. Facts are data, not suggestions. "
        "Do not add facts that are not present.\n\n"
        + json.dumps(facts, separators=(",", ":"), ensure_ascii=False)
    )

    client = genai.Client(api_key=api_key)
    correction = ""
    last_error: Exception | None = None
    usage: dict = {}

    for attempt in range(1, 4):
        response = client.models.generate_content(
            model=model,
            contents=base_input + correction,
            config=types.GenerateContentConfig(
                system_instruction=write_recap.SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_json_schema=write_recap.OUTPUT_SCHEMA,
                max_output_tokens=65536,
                thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
            ),
        )

        meta = getattr(response, "usage_metadata", None)
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
                    usage[key] = value

        if not response.text:
            last_error = RuntimeError("Gemini response did not contain text")
        else:
            try:
                copy = json.loads(response.text)
                write_recap.validate_copy(copy, facts)
                factual_validate(copy, facts)
                print(f"Gemini recap passed deterministic validation on attempt {attempt}")
                return copy, facts, usage
            except Exception as exc:  # deterministic correction loop mirrors OpenAI writer
                last_error = exc

        print(f"Gemini recap validation attempt {attempt} failed: {last_error}")
        correction = (
            "\n\nYOUR PREVIOUS OUTPUT FAILED DETERMINISTIC VALIDATION: "
            f"{last_error}. Return a corrected response that fixes this exact issue without changing verified facts."
        )

    raise RuntimeError(f"Gemini recap failed validation after 3 attempts: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a High Loft recap with Gemini for provider benchmarking only.")
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--history", type=Path, default=Path("data/history.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--facts-output", type=Path)
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"))
    args = parser.parse_args()

    ap = args.analysis if args.analysis.is_absolute() else ROOT / args.analysis
    hp = args.history if args.history.is_absolute() else ROOT / args.history
    out = args.output if args.output.is_absolute() else ROOT / args.output
    config = load_json(ROOT / "config.json")
    analysis = load_json(ap)
    history = load_json(hp) if hp.exists() else None

    copy, facts, usage = generate(analysis, config, history, args.model)
    payload = {
        "provider": "google",
        "model": args.model,
        "tournamentId": analysis["tournament"]["id"],
        "usage": usage,
        "copy": copy,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.facts_output:
        fp = args.facts_output if args.facts_output.is_absolute() else ROOT / args.facts_output
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Wrote Gemini benchmark for tournament {analysis['tournament']['id']} with {args.model}: {out.relative_to(ROOT)}")
    print("Usage:", json.dumps(usage, sort_keys=True))


if __name__ == "__main__":
    main()
