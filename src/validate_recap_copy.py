from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ORDINAL_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
}
ORDINAL_TOKEN = r"(?:" + "|".join(ORDINAL_WORDS) + r"|\d{1,2}(?:st|nd|rd|th))"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ordinal_value(token: str) -> int | None:
    token = token.lower()
    if token in ORDINAL_WORDS:
        return ORDINAL_WORDS[token]
    match = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)", token)
    return int(match.group(1)) if match else None


def hole_references(commentary: str, player_name: str) -> set[int]:
    refs: set[int] = set()

    for match in re.finditer(r"\bhole\s*#?\s*(\d{1,2})\b", commentary, re.IGNORECASE):
        refs.add(int(match.group(1)))

    for match in re.finditer(rf"\bpar[- ]?\d+\s+({ORDINAL_TOKEN})\b", commentary, re.IGNORECASE):
        value = ordinal_value(match.group(1))
        if value is not None:
            refs.add(value)

    possessive = re.escape(player_name) + r"['’]s"
    for match in re.finditer(rf"\b{possessive}\s+({ORDINAL_TOKEN})\b", commentary, re.IGNORECASE):
        value = ordinal_value(match.group(1))
        if value is not None:
            refs.add(value)

    return refs


def par_references(commentary: str) -> set[int]:
    return {
        int(match.group(1))
        for match in re.finditer(r"\bpar[- ]?(\d+)\b", commentary, re.IGNORECASE)
    }


def validate(copy: dict, facts: dict) -> None:
    expected_players = [player["name"] for player in facts["playersNetOrder"]]
    actual_players = [player.get("name") for player in copy.get("players", [])]
    if actual_players != expected_players:
        raise RuntimeError(f"Player order mismatch: expected {expected_players}, got {actual_players}")

    expected_carnage = [item["name"] for item in facts["carnageOrder"]]
    actual_carnage = [item.get("name") for item in copy.get("carnage", [])]
    if actual_carnage != expected_carnage:
        raise RuntimeError(f"Carnage order mismatch: expected {expected_carnage}, got {actual_carnage}")

    fact_by_name = {item["name"]: item["hole"] for item in facts["carnageOrder"]}
    for item in copy.get("carnage", []):
        name = item["name"]
        commentary = item.get("commentary", "")
        fact = fact_by_name[name]
        expected_hole = int(fact["hole"])
        expected_par = int(fact["par"])

        refs = hole_references(commentary, name)
        wrong_holes = sorted(ref for ref in refs if ref != expected_hole)
        if wrong_holes:
            raise RuntimeError(
                f"Carnage commentary for {name} references wrong hole(s) {wrong_holes}; "
                f"verified worst hole is {expected_hole}. Commentary: {commentary!r}"
            )

        par_refs = par_references(commentary)
        wrong_pars = sorted(ref for ref in par_refs if ref != expected_par)
        if wrong_pars:
            raise RuntimeError(
                f"Carnage commentary for {name} references wrong par(s) {wrong_pars}; "
                f"verified par is {expected_par}. Commentary: {commentary!r}"
            )

    print(f"Validated {len(actual_players)} player writeups and {len(actual_carnage)} Carnage comments")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-check AI recap copy against verified deterministic facts.")
    parser.add_argument("copy", type=Path)
    parser.add_argument("facts", type=Path)
    args = parser.parse_args()

    copy_path = args.copy if args.copy.is_absolute() else ROOT / args.copy
    facts_path = args.facts if args.facts.is_absolute() else ROOT / args.facts
    validate(load_json(copy_path), load_json(facts_path))


if __name__ == "__main__":
    main()
