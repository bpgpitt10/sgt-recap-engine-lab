from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from analyze_tournament import parse_scorecard, parse_shots

ROOT = Path(__file__).resolve().parents[1]
MAX_CHARS = 1900
MAX_MESSAGES = 3


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def score(value: object) -> str:
    if value is None:
        return "—"
    value = str(value)
    return "E" if value in {"0", "+0", "-0", "E"} else value


def parse_yards(description: str | None) -> float | None:
    if not description:
        return None
    match = re.match(r"\s*(\d+(?:\.\d+)?)\s*yds?\b", description, re.I)
    return float(match.group(1)) if match else None


def verified_awards(analysis: dict, raw: dict | None) -> list[str]:
    awards: list[str] = []

    carnage = analysis.get("carnage", [])
    if carnage:
        king = carnage[0]
        hole = king.get("hole")
        if isinstance(hole, dict):
            hole_no = hole.get("hole")
            gross = hole.get("gross")
            damage = hole.get("grossToPar")
        else:
            hole_no = king.get("hole")
            gross = king.get("gross")
            damage = king.get("grossToPar")
        damage_label = f"+{damage}" if isinstance(damage, (int, float)) and damage > 0 else str(damage or "—")
        awards.append(f"👑 **CARNAGE KING:** {king.get('name')} · Hole {hole_no} · {gross} ({damage_label})")

    if not raw:
        return awards

    shortest_drive: tuple[float, str, int] | None = None

    for player in raw.get("players", []):
        name = player.get("name") or "—"
        scorecard = parse_scorecard(player.get("scorecard"))
        par_by_hole = {
            (int(h.get("round") or 1), int(h["hole"])): h.get("par")
            for h in scorecard.get("holes", [])
            if h.get("hole") is not None
        }
        for hole in parse_shots(player.get("shots")):
            round_no = int(hole.get("round") or 1)
            hole_no = int(hole.get("hole"))
            shots = hole.get("shots") or []

            # 'Shortest drive' = shortest first tee ball on a par 4 or par 5.
            # We intentionally do not assume which club was used.
            if par_by_hole.get((round_no, hole_no)) in {4, 5} and shots:
                first = next((s for s in shots if s.get("number") == 1), shots[0])
                yards = parse_yards(first.get("description"))
                if yards is not None and (shortest_drive is None or yards < shortest_drive[0]):
                    shortest_drive = (yards, name, hole_no)

    if shortest_drive:
        yards, name, hole_no = shortest_drive
        yard_label = f"{int(round(yards))} yds" if abs(yards - round(yards)) < 0.05 else f"{yards:.1f} yds"
        awards.append(f"🪱 **WORM BURNER:** {name} · {yard_label} · Hole {hole_no}")

    return awards


def ranking_messages(net: list[dict], taglines: dict[str, str]) -> list[str]:
    messages: list[str] = []
    current = "**NET RANKING**"
    for i, row in enumerate(net, 1):
        name = row.get("name", "—")
        roast = taglines.get(name, "").strip()
        line = f"**{i}. {name} · {score(row.get('total'))}** — {roast}"
        candidate = current + "\n" + line
        if len(candidate) <= MAX_CHARS:
            current = candidate
            continue
        messages.append(current)
        current = "**NET RANKING · CONTINUED**\n" + line
    messages.append(current)
    return messages


def build(analysis: dict, copy: dict, recap_url: str, raw: dict | None = None) -> dict:
    net = analysis.get("leaderboard", {}).get("net", [])
    gross = analysis.get("leaderboard", {}).get("gross", [])
    taglines = {p["name"]: p.get("tagline", "") for p in copy.get("players", [])}
    title = (analysis.get("tournament") or {}).get("name") or "High Loft tournament"
    teaser = (copy.get("latestTournamentTeaser") or "").strip()

    intro_lines = [
        "🏆 **New High Loft recap is live**",
        f"**{title}** — {recap_url}",
    ]
    if teaser:
        intro_lines.extend([teaser, ""])
    if net:
        intro_lines.append(f"**NET:** {net[0]['name']} · {score(net[0].get('total'))}")
    if gross:
        intro_lines.append(f"**GROSS:** {gross[0]['name']} · {score(gross[0].get('total'))}")

    awards = verified_awards(analysis, raw)
    if awards:
        intro_lines.extend(["", "**THE HECKLER'S HARDWARE**", *awards])

    intro = "\n".join(intro_lines)
    if len(intro) > MAX_CHARS:
        raise RuntimeError(f"Discord intro/awards post is too long ({len(intro)} chars)")

    messages = [intro, *ranking_messages(net, taglines)]
    if len(messages) > MAX_MESSAGES:
        # This should only happen with an unusually huge field or absurdly long taglines.
        # Keep the complete player list rather than silently dropping people.
        raise RuntimeError(f"Discord payload needs {len(messages)} messages; max is {MAX_MESSAGES}. Shorten roast taglines.")

    return {"messages": messages, "characterCounts": [len(m) for m in messages]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build High Loft Discord webhook messages from validated recap data.")
    parser.add_argument("analysis", type=Path)
    parser.add_argument("copy", type=Path)
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--recap-url", required=True)
    parser.add_argument("--output", type=Path, default=Path("data/discord-payload.json"))
    args = parser.parse_args()

    analysis_path = args.analysis if args.analysis.is_absolute() else ROOT / args.analysis
    copy_path = args.copy if args.copy.is_absolute() else ROOT / args.copy
    raw_path = None if args.raw is None else (args.raw if args.raw.is_absolute() else ROOT / args.raw)
    output = args.output if args.output.is_absolute() else ROOT / args.output

    payload = build(
        load(analysis_path),
        load(copy_path),
        args.recap_url,
        load(raw_path) if raw_path and raw_path.exists() else None,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for i, message in enumerate(payload["messages"], 1):
        print(f"--- Discord post {i} · {len(message)} chars ---")
        print(message)
    print(f"Discord posts: {len(payload['messages'])}")


if __name__ == "__main__":
    main()
