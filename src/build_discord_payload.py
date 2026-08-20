from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def score(value: object) -> str:
    if value is None:
        return "—"
    value = str(value)
    return "E" if value in {"0", "+0", "-0", "E"} else value


def build(analysis: dict, copy: dict, recap_url: str) -> dict:
    net = analysis.get("leaderboard", {}).get("net", [])
    gross = analysis.get("leaderboard", {}).get("gross", [])
    taglines = {p["name"]: p.get("tagline", "") for p in copy.get("players", [])}

    lines = [
        "🏆 **New High Loft recap is live**",
        copy.get("latestTournamentTeaser", "").strip(),
        "",
    ]
    if net:
        lines.append(f"**Net:** {net[0]['name']} {score(net[0].get('total'))}")
    if gross:
        lines.append(f"**Gross:** {gross[0]['name']} {score(gross[0].get('total'))}")
    lines.extend(["", "**NET RANKING**"])
    for i, row in enumerate(net, 1):
        roast = taglines.get(row.get("name"), "").strip()
        lines.append(f"**{i}. {row.get('name')} · {score(row.get('total'))}** — {roast}")
    lines.extend(["", f"**Read the full carnage →** {recap_url}"])

    content = "\n".join(lines)
    if len(content) > 1950:
        # Keep every player, but remove the teaser before sacrificing any ranking/roast line.
        lines[1] = ""
        content = "\n".join(lines)
    if len(content) > 1950:
        raise RuntimeError(f"Discord recap message is too long ({len(content)} chars); shorten generated taglines")

    return {"content": content}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the High Loft Discord webhook payload from validated recap data.")
    parser.add_argument("analysis", type=Path)
    parser.add_argument("copy", type=Path)
    parser.add_argument("--recap-url", required=True)
    parser.add_argument("--output", type=Path, default=Path("data/discord-payload.json"))
    args = parser.parse_args()

    analysis_path = args.analysis if args.analysis.is_absolute() else ROOT / args.analysis
    copy_path = args.copy if args.copy.is_absolute() else ROOT / args.copy
    output = args.output if args.output.is_absolute() else ROOT / args.output
    payload = build(load(analysis_path), load(copy_path), args.recap_url)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(payload["content"])
    print(f"Discord payload chars: {len(payload['content'])}")


if __name__ == "__main__":
    main()
