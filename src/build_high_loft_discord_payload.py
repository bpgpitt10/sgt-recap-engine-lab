from __future__ import annotations

import json

import build_discord_payload as discord

_original_build = discord.build


def competition_mode(analysis: dict) -> str:
    cfg = discord.load(discord.ROOT / "config.json")
    event_id = str((analysis.get("tournament") or {}).get("id"))
    return str((cfg.get("competitionOverrides") or {}).get(event_id, "net")).lower()


def build(analysis: dict, copy: dict, recap_url: str, raw: dict | None = None) -> dict:
    if competition_mode(analysis) != "gross":
        return _original_build(analysis, copy, recap_url, raw)

    # The base Heckler builder is intentionally net-primary. For an explicit
    # scratch event, feed it a copy with Gross in the primary leaderboard slot,
    # then relabel only the resulting Discord presentation.
    adjusted = json.loads(json.dumps(analysis))
    leaderboard = adjusted.get("leaderboard") or {}
    net = leaderboard.get("net", [])
    gross = leaderboard.get("gross", [])
    leaderboard["net"], leaderboard["gross"] = gross, net

    payload = _original_build(adjusted, copy, recap_url, raw)
    messages = []
    for message in payload.get("messages", []):
        message = message.replace("**NET:**", "**__PRIMARY_GROSS__:**")
        message = message.replace("**GROSS:**", "**NET:**")
        message = message.replace("**__PRIMARY_GROSS__:**", "**GROSS:**")
        message = message.replace("**NET RANKING**", "**GROSS RANKING**")
        message = message.replace("**NET RANKING · CONTINUED**", "**GROSS RANKING · CONTINUED**")
        messages.append(message)
    payload["messages"] = messages
    payload["characterCounts"] = [len(message) for message in messages]
    return payload


discord.build = build


if __name__ == "__main__":
    discord.main()
