from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from analyze_tournament import parse_scorecard, parse_shots

ROOT = Path(__file__).resolve().parents[1]
MAX_CHARS = 1900
MAX_MESSAGES = 3
MAX_ROTATING_AWARDS = 3


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


def parse_made_putt(description: str | None) -> float | None:
    if not description:
        return None
    match = re.search(r"\bMade putt from\s+(\d+(?:\.\d+)?)\s*ft\b", description, re.I)
    return float(match.group(1)) if match else None


def yard_label(yards: float) -> str:
    return f"{int(round(yards))} yds" if abs(yards - round(yards)) < 0.05 else f"{yards:.1f} yds"


def foot_label(feet: float) -> str:
    return f"{int(round(feet))} ft" if abs(feet - round(feet)) < 0.05 else f"{feet:.1f} ft"


def carnage_award(analysis: dict) -> tuple[str | None, str | None]:
    carnage = analysis.get("carnage", [])
    if not carnage:
        return None, None
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
    name = king.get("name") or "—"
    return name, f"👑 **CARNAGE KING:** {name} · Hole {hole_no} · {gross} ({damage_label})"


def rotating_candidates(analysis: dict, raw: dict | None) -> list[dict]:
    if not raw:
        return []

    longest_drive: tuple[float, str, int] | None = None
    shortest_drive: tuple[float, str, int] | None = None
    longest_putt: tuple[float, str, int] | None = None
    weird_shots: list[tuple[int, str, int, str]] = []

    completed_names = {
        p.get("name")
        for p in analysis.get("players", [])
        if p.get("completed") and p.get("name")
    }

    for player in raw.get("players", []):
        name = player.get("name") or "—"
        if completed_names and name not in completed_names:
            continue
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

            # Tee-ball awards only use shot 1 on par 4/5 holes. We do not assume club choice.
            if par_by_hole.get((round_no, hole_no)) in {4, 5} and shots:
                first = next((s for s in shots if s.get("number") == 1), shots[0])
                yards = parse_yards(first.get("description"))
                if yards is not None:
                    if longest_drive is None or yards > longest_drive[0]:
                        longest_drive = (yards, name, hole_no)
                    if shortest_drive is None or yards < shortest_drive[0]:
                        shortest_drive = (yards, name, hole_no)

            for shot in shots:
                desc = (shot.get("description") or "").strip()
                made = parse_made_putt(desc)
                if made is not None and (longest_putt is None or made > longest_putt[0]):
                    longest_putt = (made, name, hole_no)

                lower = desc.lower()
                weirdness = 0
                reason = None
                if "shank" in lower:
                    weirdness, reason = 100, "shank"
                elif "0 yds" in lower or "0 yd" in lower:
                    weirdness, reason = 95, "0-yard shot"
                elif "1 yds" in lower or "1 yd" in lower:
                    weirdness, reason = 80, "1-yard shot"
                elif "penalty" in lower or re.search(r"\bob\b", lower):
                    weirdness, reason = 70, "penalty ball"
                if weirdness:
                    weird_shots.append((weirdness, name, hole_no, reason))

    candidates: list[dict] = []

    # Positive awards are deliberately high priority so Hardware does not become a
    # second leaderboard for the highest-handicap players.
    if longest_putt and longest_putt[0] >= 15:
        feet, name, hole_no = longest_putt
        candidates.append({
            "priority": 100 + feet,
            "name": name,
            "line": f"🎯 **SHOT OF THE DAY:** {name} · buried {foot_label(feet)} · Hole {hole_no}",
        })

    if longest_drive and longest_drive[0] >= 250:
        yards, name, hole_no = longest_drive
        candidates.append({
            "priority": 90 + yards / 1000,
            "name": name,
            "line": f"🔥 **SEND IT AWARD:** {name} · {yard_label(yards)} · Hole {hole_no}",
        })

    if weird_shots:
        weirdness, name, hole_no, reason = max(weird_shots, key=lambda item: item[0])
        candidates.append({
            "priority": 80 + weirdness / 1000,
            "name": name,
            "line": f"🤡 **WHAT WAS THAT?:** {name} · {reason} · Hole {hole_no}",
        })

    # Worm Burner only exists when the tee ball is actually ridiculous. A merely
    # short drive is not award-worthy, especially across mixed handicaps.
    if shortest_drive and shortest_drive[0] <= 150:
        yards, name, hole_no = shortest_drive
        candidates.append({
            "priority": 70 + (150 - yards) / 1000,
            "name": name,
            "line": f"🪱 **WORM BURNER:** {name} · {yard_label(yards)} · Hole {hole_no}",
        })

    return sorted(candidates, key=lambda item: item["priority"], reverse=True)


def verified_awards(analysis: dict, raw: dict | None) -> list[str]:
    awards: list[str] = []
    king_name, king_line = carnage_award(analysis)
    if king_line:
        awards.append(king_line)

    candidates = rotating_candidates(analysis, raw)
    selected: list[dict] = []
    used_names = {king_name} if king_name else set()

    # First pass favors different recipients so one player does not sweep every joke.
    for candidate in candidates:
        if len(selected) >= MAX_ROTATING_AWARDS:
            break
        if candidate["name"] in used_names:
            continue
        selected.append(candidate)
        used_names.add(candidate["name"])

    # If the event simply does not offer enough distinct qualifying moments, allow
    # another award for an existing recipient rather than inventing a filler category.
    if len(selected) < MAX_ROTATING_AWARDS:
        for candidate in candidates:
            if len(selected) >= MAX_ROTATING_AWARDS:
                break
            if candidate in selected:
                continue
            selected.append(candidate)

    awards.extend(item["line"] for item in selected)
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
        f"**{title}**",
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

    intro_lines.extend(["", f"**Read the full recap →** {recap_url}"])
    intro = "\n".join(intro_lines)
    if len(intro) > MAX_CHARS:
        raise RuntimeError(f"Discord intro/awards post is too long ({len(intro)} chars)")

    messages = [intro, *ranking_messages(net, taglines)]
    if len(messages) > MAX_MESSAGES:
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
