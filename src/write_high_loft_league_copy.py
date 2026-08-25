from __future__ import annotations

import re

import write_league_copy


HIGH_LOFT_PROFILE_EDITORIAL = r"""

HIGH LOFT SCOUTING-FILE OVERRIDES
These rules are more specific than the generic league-copy rules above.

SGT STROKES GAINED INTERPRETATION
- The SG fingerprint uses SGT-supplied values. Do NOT describe them as strokes gained versus scratch, par, PGA Tour, or GSPro Portal.
- Treat SG primarily as a RELATIVE PERFORMANCE SIGNAL.
- Within a player, the category relationships matter: which part of the game consistently carries them and which part gives strokes back.
- Across league players, category ranking/relative strength matters: who is stronger or weaker off the tee, on approach, around the green, or putting under SGT's benchmark.
- Across repeated starts, persistent direction and ordering of categories are strong scouting evidence.
- Exact values are valid, but do not over-interpret the magnitude. The comparison, rank, sign, and recurring pattern usually matter more than the raw number.
- Never infer handicap, scratch-equivalent ability, or expected gross score from an SG value.
- If prose needs to name the metric, call it "SGT SG" or say "against the SGT benchmark."

PLAYER PROFILE PROSE
- The player card ALREADY shows STARTS, AVG NET, GROSS WINS, NET WINS, and the four-category SG fingerprint. Do not restate those metrics unless one is absolutely central to the identity/story.
- The profile is not a statistical summary. It is a scouting note with a point of view.
- Lead with the player's repeatable golf identity, contradiction, strength, weakness, or recurring form of self-sabotage.
- Prefer golf-language synthesis and wit over numbers. Example: "The driver keeps writing checks the irons cannot cash." That is better than listing tee SG, approach SG, GIR, and putting.
- Normally use ZERO or ONE exact number in a profile. Two is the hard maximum.
- Do not enumerate SG categories. The bars are literally sitting underneath the paragraph.
- Do not mechanically state average finish, starts, wins, GIR, fairways, putts, proximity, birdies, doubles, and recent-event results in one paragraph.
- Use recent events only as evidence for a larger tendency, not as a chronological recap of results.
- Every profile should contain at least one line with personality/wit specific to that player's golf. Roast the golf when earned.
- Write like someone in the group who has watched this player for months and knows the bit. Not like an analyst reading a dashboard.
- Aim for roughly 65-110 words. Dense with character and insight, light on accounting.

LEAGUE SNAPSHOT
- Same principle: the leaderboard and cards carry the numbers. Use prose to explain what is changing, what keeps happening, and what is funny about the league right now.
""".strip()

write_league_copy.SYSTEM_PROMPT = write_league_copy.SYSTEM_PROMPT + "\n\n" + HIGH_LOFT_PROFILE_EDITORIAL

_original_validate = write_league_copy.validate_copy


def numeric_fact_count(text: str) -> int:
    return len(re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?", text))


def high_loft_validate(copy: dict, facts: dict) -> None:
    _original_validate(copy, facts)
    for profile in copy.get("profiles", []):
        body = (profile.get("profile") or "").strip()
        words = re.findall(r"\b\w+[’'-]?\w*\b", body)
        if len(words) > 130:
            raise RuntimeError(
                f"Scouting profile is too long for {profile.get('name')}: {len(words)} words; max 130"
            )
        if numeric_fact_count(body) > 2:
            raise RuntimeError(
                f"Scouting profile is too data-heavy for {profile.get('name')}: more than 2 explicit numeric facts. The card already shows the metrics."
            )


write_league_copy.validate_copy = high_loft_validate


if __name__ == "__main__":
    write_league_copy.main()
