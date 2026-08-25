from __future__ import annotations

import re

import write_recap


HIGH_LOFT_EDITORIAL = r"""

HIGH LOFT EDITORIAL OVERRIDES
These rules are more specific than the generic recap rules above and control the final style.

COMPETITION MODE OVERRIDE
- Inspect league.primaryCompetition in the VERIFIED FACT PACKAGE.
- Normally it is "net", and all normal High Loft net-primary rules apply.
- If it is "gross", this is an explicitly configured scratch/gross-primary event. GROSS determines the tournament winner, challenger(s), recap lead, teaser, and player-by-player order. Net is secondary context only.
- This gross-primary instruction overrides every generic instruction that says Net determines the tournament or player order.
- For backward compatibility the fact-package key playersNetOrder still contains the required primary player order; for a gross-primary event that list is intentionally in GROSS order.

SGT STROKES GAINED INTERPRETATION
- All SG values in the fact package are SGT-supplied values. Do NOT reinterpret them as strokes gained versus scratch, par, PGA Tour, or GSPro Portal.
- Treat SG primarily as a RELATIVE PERFORMANCE SIGNAL.
- Within one player's round, use category relationships to explain what carried the round and what hurt it: tee vs approach vs short game vs putting.
- Across league players, use category rankings/relationships to say who performed better or worse in the same area under SGT's benchmark.
- Across repeated starts, use the direction and persistence of categories to identify durable strengths, weaknesses, and changes.
- Exact SG values are valid evidence, but the comparison/ranking/relationship usually matters more than the magnitude itself.
- Never infer a player's handicap, scratch-equivalent ability, or expected gross score from an SG number.
- When useful, phrase it as "SGT SG" or "against the SGT benchmark" rather than implying a universal strokes-gained baseline.

LATEST TOURNAMENT TEASER
- This copy appears in VERY LARGE type on the landing page. It must be a headline, not a paragraph.
- Maximum 18 words. Prefer 10-16.
- One idea only: primary-competition winner + the funniest/most revealing hook from the round.
- Do NOT cram margin, secondary score, strokes gained, runner-up, and course story into the same teaser.
- The longer Tournament in 30 Seconds copy exists immediately below it and can carry the detail.
- Write it like a sharp headline someone would actually want to click, not a compressed box score.

CARNAGE COMMENTARY
- The renderer ALREADY shows the full shot trail immediately above the commentary. DO NOT narrate that trail back to the reader.
- Never walk through every shot in order. Never write a play-by-play recap such as "the drive went..., then..., then..., then...".
- Commentary should be 1-3 punchy sentences and normally 20-55 words.
- Pick only the one or two moments that define why the hole became ridiculous: a penalty, shank, bunker loop, zero/one-yard move, repeated failed recovery, four-putt, etc.
- If the trail itself is funny, summarize the pattern rather than restating distances.
- The job is interpretation + joke. The visible shot trail is the evidence.

PLAYER-BY-PLAYER BODY
- Write a STORY about the round, not an inventory of the fact package.
- Start from a clear thesis: what kind of round was this, what actually drove the primary result, and what does it say about this player's golf right now?
- Be aggressively selective. The reader can already see the leaderboard and other visible data. Most supplied numbers should NOT appear in prose.
- Normally use 0-2 exact numeric facts in the entire paragraph. A number earns its way in only if it is the reason the story works.
- Never march through SG categories, GIR, fairways, putts, birdies, doubles, and worst-hole details just because they exist.
- Prefer synthesis and jokes: "the irons carried him while the putter tried to file an injunction" over category-by-category reporting.
- Shot evidence is seasoning, not a transcript. Mention a specific hole/shot only when unusually funny, decisive, or revealing.
- Prior history should be used only when it adds a real comparison or trend. Do not mechanically append prior averages to every player.
- The paragraph should feel like somebody who watched the round and knows the player's tendencies, not somebody reading a spreadsheet aloud.
- Aim for roughly 80-135 words. More wit, judgment, and golf identity; less accounting.

FACT DISCIPLINE
- Do NOT mention handicap, strokes received, net adjustment, playing handicap, swing speed, club speed, or ball speed unless that exact fact is explicitly present in the supplied fact package.
- Net standings and net scores are safe to discuss. Do not invent an explanation for WHY a player's net score differs from gross unless the adjustment/handicap data is supplied.

OVERALL
- Assume the reader can see the leaderboard, shot trail, and metric cards on the page. Copy should add judgment, synthesis, context, and comedy rather than duplicate visible information.
- If a sentence could be generated by simply reading numbers left-to-right from the fact package, rewrite or delete it.
""".strip()

write_recap.SYSTEM_PROMPT = write_recap.SYSTEM_PROMPT + "\n\n" + HIGH_LOFT_EDITORIAL

_original_validate = write_recap.validate_copy
_original_build_fact_package = write_recap.build_fact_package


def competition_mode(config: dict, analysis: dict) -> str:
    tournament = analysis.get("tournament") or {}
    event_id = str(tournament.get("id"))
    return str((config.get("competitionOverrides") or {}).get(event_id, "net")).lower()


def high_loft_build_fact_package(analysis: dict, config: dict, history: dict | None) -> dict:
    facts = _original_build_fact_package(analysis, config, history)
    mode = competition_mode(config, analysis)
    facts.setdefault("league", {})["primaryCompetition"] = mode
    if mode == "gross":
        players = list(facts.get("playersNetOrder") or [])
        players.sort(
            key=lambda p: (
                (p.get("leaderboard") or {}).get("grossFinish")
                if (p.get("leaderboard") or {}).get("grossFinish") is not None
                else 999,
                str(p.get("name") or ""),
            )
        )
        facts["playersNetOrder"] = players
        facts["competitionOverride"] = (
            "This event is explicitly configured as scratch/gross-primary. Gross determines the tournament result and primary player order; net is secondary context."
        )
    return facts


write_recap.build_fact_package = high_loft_build_fact_package


def numeric_fact_count(text: str) -> int:
    # Editorial diagnostic only. Numeric density should influence prompting/review,
    # but must never block an otherwise factual tournament publication.
    return len(re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?", text))


def high_loft_validate(copy: dict, facts: dict) -> None:
    _original_validate(copy, facts)

    teaser = (copy.get("latestTournamentTeaser") or "").strip()
    teaser_words = re.findall(r"\b\w+[’'-]?\w*\b", teaser)
    if len(teaser_words) > 18:
        raise RuntimeError(
            f"Latest Tournament teaser is too long for the landing-page headline: {len(teaser_words)} words; max 18"
        )

    for item in copy.get("carnage", []):
        text = (item.get("commentary") or "").strip()
        words = re.findall(r"\b\w+[’'-]?\w*\b", text)
        if len(words) > 65:
            raise RuntimeError(
                f"Carnage commentary is too long / too play-by-play for {item.get('name')}: {len(words)} words; max 65"
            )
        sequence_hits = len(re.findall(r"\b(?:then|next|followed|after that|finally|before the|the next)\b", text, re.I))
        if sequence_hits >= 4:
            raise RuntimeError(
                f"Carnage commentary appears to narrate the shot sequence for {item.get('name')}; summarize the disaster instead"
            )

    for item in copy.get("players", []):
        body = (item.get("body") or "").strip()
        words = re.findall(r"\b\w+[’'-]?\w*\b", body)
        if len(words) > 160:
            raise RuntimeError(
                f"Player body is too long / insufficiently selective for {item.get('name')}: {len(words)} words; max 160"
            )
        # Numeric density remains a strong editorial preference in the prompt, but
        # it is intentionally not a hard validation failure. We learned in live
        # automation that one extra number can otherwise kill the entire publish.
        numeric_fact_count(body)


write_recap.validate_copy = high_loft_validate


if __name__ == "__main__":
    write_recap.main()
