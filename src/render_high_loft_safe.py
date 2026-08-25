from __future__ import annotations

import re

import render_high_loft as renderer

# Capture original functions before monkey-patching them below.
_original_analysis_map = renderer.analysis_map
_original_landing = renderer.landing
_original_recap_page = renderer.recap_page


def competition_mode(event: dict, cfg: dict) -> str:
    event_id = str(event.get("id"))
    return str((cfg.get("competitionOverrides") or {}).get(event_id, "net")).lower()


def normalized_analysis_map() -> dict[int, dict]:
    analyses = _original_analysis_map()
    cfg = renderer.config()
    for analysis in analyses.values():
        players = {
            player.get("name"): player
            for player in analysis.get("players", [])
            if player.get("completed")
        }
        normalized = []
        for original in analysis.get("carnage", []):
            item = dict(original)
            raw_hole = item.get("hole")
            if not isinstance(raw_hole, dict):
                player = players.get(item.get("name")) or {}
                worst_hole = player.get("worstHole")
                if isinstance(worst_hole, dict):
                    item["hole"] = worst_hole
                else:
                    raise RuntimeError(
                        f"Carnage entry for {item.get('name')} has numeric/invalid hole "
                        f"{raw_hole!r} and no authoritative worstHole object"
                    )
            normalized.append(item)
        analysis["carnage"] = normalized

        if competition_mode(analysis.get("tournament") or {}, cfg) == "gross":
            leaderboard = analysis.get("leaderboard") or {}
            net = leaderboard.get("net", [])
            gross = leaderboard.get("gross", [])
            leaderboard["net"], leaderboard["gross"] = gross, net

    return analyses


def scalable_landing_layout(html: str) -> str:
    # All cards in the currently selected scope share one SG scale. This keeps
    # player-to-player/category comparisons honest while avoiding a permanently
    # under-filled fixed +/-8 axis. Ceiling = largest absolute visible category,
    # rounded up to the next whole stroke, with a minimum +/-3.
    replacement = r'''function sgScale(players){let m=0;for(const p of players||[]){const sg=p.sg||{};for(const v of [sg.tee,sg.approach,sg.shortGame,sg.putting]){const n=Math.abs(Number(v||0));if(Number.isFinite(n))m=Math.max(m,n)}}return Math.max(3,Math.ceil(m))}
function bar(label,v,max){const n=Number(v||0),w=Math.min(50,Math.abs(n)/max*50);return `<span>${label}</span><div class="bar"><i class="${n>=0?'pos':'neg'}" style="width:${w}%"></i></div><b>${n>=0?'+':''}${fmt(n)}</b>`}
function playerCard(p,c,max){const sg=p.sg||{};const safeName=escHtml(p.name);return `<article class="player scouting-card"><div class="ghost">${fmt(p.avgNet)}</div><h3>${safeName}</h3><div class="tag">${escHtml(c?.tagline||'')}</div><div class="chips"><div class="chip"><b>${p.starts}</b><small>STARTS</small></div><div class="chip"><b>${fmt(p.avgNet)}</b><small>AVG NET</small></div><div class="chip"><b>${p.grossWins}</b><small>GROSS WINS</small></div><div class="chip"><b>${p.netWins}</b><small>NET WINS</small></div></div><div class="fingerprint">${bar('TEE',sg.tee,max)}${bar('APP',sg.approach,max)}${bar('SHORT',sg.shortGame,max)}${bar('PUTT',sg.putting,max)}</div><div class="scouting-details" hidden><p>${escHtml(c?.profile||'')}</p></div><button type="button" class="expand-control" data-profile-expand aria-expanded="false">Read scouting file <span>+</span></button></article>`}
function board'''
    html, count = re.subn(
        r"function bar\(label,v\)\{.*?\}\nfunction playerCard\(p,c\)\{.*?\}\nfunction board",
        replacement,
        html,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("Could not upgrade landing-page scouting cards")

    html, count = re.subn(
        r"const cp=Object\.fromEntries\(c\.profiles\.map\(x=>\[x\.name,x\]\)\);document\.querySelector\('#players-grid'\)\.innerHTML=h\.players\.map\(p=>playerCard\(p,cp\[p\.name\]\)\)\.join\(''\);",
        "const cp=Object.fromEntries(c.profiles.map(x=>[x.name,x]));const max=sgScale(h.players);document.querySelector('#players-grid').innerHTML=h.players.map(p=>playerCard(p,cp[p.name],max)).join('');",
        html,
        count=1,
    )
    if count != 1:
        raise RuntimeError("Could not wire scope-wide SG scale into profile render")

    click_hook = r'''
document.addEventListener('click',e=>{const btn=e.target.closest('[data-profile-expand]');if(!btn)return;const card=btn.closest('.scouting-card');const details=card?.querySelector('.scouting-details');if(!details)return;const open=btn.getAttribute('aria-expanded')==='true';btn.setAttribute('aria-expanded',String(!open));details.hidden=open;card.classList.toggle('is-open',!open);btn.innerHTML=!open?'Close scouting file <span>−</span>':'Read scouting file <span>+</span>';});
'''
    html = html.replace("render(HISTORY.defaultScope);", click_hook + "render(HISTORY.defaultScope);", 1)

    landing_css = r'''
<style>
.scouting-card{min-height:0}
.scouting-card .fingerprint{margin-top:18px}
.scouting-card .scouting-details[hidden]{display:none}
.scouting-card .scouting-details p{margin:18px 0 0}
.expand-control{margin-top:18px;width:100%;display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid #314137;border-radius:12px;background:#0f1711;color:#b6f34a;padding:11px 13px;font:inherit;font-size:11px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;cursor:pointer}
.expand-control span{font-size:18px;line-height:1}
.scouting-card.is-open .expand-control{border-color:#46632c}
@media(min-width:1080px){.players{grid-template-columns:repeat(3,minmax(0,1fr))}.scouting-card .chips{grid-template-columns:repeat(2,1fr)}}
</style>
'''
    return html.replace("</head>", landing_css + "</head>", 1)


def gross_primary_landing(history: dict, league_copy: dict, analyses: dict[int, dict], latest_copy: dict, cfg: dict, production_root):
    html = _original_landing(history, league_copy, analyses, latest_copy, cfg, production_root)
    latest_event = history["completedEvents"][0]
    if competition_mode(latest_event, cfg) == "gross":
        html = (
            html.replace("🏆 Net champion", "🏆 Gross champion")
            .replace("Net challenger", "Gross challenger")
            .replace("Gross winner</small>", "Net standings leader</small>", 1)
            .replace("Gross runner-up", "Net standings runner-up", 1)
        )
    return scalable_landing_layout(html)


def compact_recap_cards(html: str) -> str:
    carnage_index = 0

    def carnage_card(match: re.Match) -> str:
        nonlocal carnage_index
        card = match.group(0)
        initially_open = carnage_index < 2
        carnage_index += 1
        card = card.replace(
            "<article ",
            '<article data-carnage-card class="initial-open" ' if initially_open else '<article data-carnage-card ',
            1,
        )
        if initially_open:
            card = card.replace(' class="initial-open" class="', ' class="initial-open ', 1)
        button_text = 'Close crime scene <span>−</span>' if initially_open else 'Open crime scene <span>+</span>'
        expanded = "true" if initially_open else "false"
        card = card[:-10] + f'<button type="button" class="expand-control recap-expand" data-carnage-expand aria-expanded="{expanded}">{button_text}</button></article>'
        return card

    html = re.sub(
        r'<article class="hole-card[^"]*">.*?</article>',
        carnage_card,
        html,
        flags=re.S,
    )

    player_index = 0

    def player_card(match: re.Match) -> str:
        nonlocal player_index
        card = match.group(0)
        initially_open = player_index < 2
        player_index += 1
        details_hidden = "" if initially_open else " hidden"
        card = re.sub(
            r'(<p class="player-roast">.*?</p>)(<p>.*?</p>)',
            rf'\1<div class="round-details"{details_hidden}>\2</div>',
            card,
            count=1,
            flags=re.S,
        )
        article_class = ' class="is-open"' if initially_open else ""
        card = card.replace("<article>", f'<article data-player-card{article_class}>', 1)
        button_text = 'Close breakdown <span>−</span>' if initially_open else 'Read full breakdown <span>+</span>'
        expanded = "true" if initially_open else "false"
        card = card[:-10] + f'<button type="button" class="expand-control recap-expand" data-player-expand aria-expanded="{expanded}">{button_text}</button></article>'
        return card

    player_block = re.search(
        r'(<div class="recap-players expanded">)(.*?)(</div></div></section>)',
        html,
        flags=re.S,
    )
    if player_block:
        compact = re.sub(r"<article>.*?</article>", player_card, player_block.group(2), flags=re.S)
        html = html[:player_block.start(2)] + compact + html[player_block.end(2):]

    recap_js = r'''
<script>
document.querySelectorAll('[data-carnage-card].initial-open').forEach(card=>card.classList.add('is-open'));
document.addEventListener('click',e=>{
  const carnageBtn=e.target.closest('[data-carnage-expand]');
  if(carnageBtn){
    const card=carnageBtn.closest('[data-carnage-card]');
    const open=carnageBtn.getAttribute('aria-expanded')==='true';
    carnageBtn.setAttribute('aria-expanded',String(!open));
    card?.classList.toggle('is-open',!open);
    carnageBtn.innerHTML=!open?'Close crime scene <span>−</span>':'Open crime scene <span>+</span>';
    return;
  }
  const playerBtn=e.target.closest('[data-player-expand]');
  if(playerBtn){
    const card=playerBtn.closest('[data-player-card]');
    const details=card?.querySelector('.round-details');
    if(!details)return;
    const open=playerBtn.getAttribute('aria-expanded')==='true';
    playerBtn.setAttribute('aria-expanded',String(!open));
    details.hidden=open;
    card?.classList.toggle('is-open',!open);
    playerBtn.innerHTML=!open?'Close breakdown <span>−</span>':'Read full breakdown <span>+</span>';
  }
});
</script>
'''
    return html.replace("</body>", recap_js + "</body>", 1)


def scalable_recap_layout(html: str, analysis: dict) -> str:
    html = re.sub(
        r'<div class="eyebrow">Tournament in 30 seconds</div><h2>(The (?:net|gross) race first\. Then the wreckage underneath it\.)</h2>',
        r'<div class="section-kicker">\1</div><h2>Tournament in 30 seconds</h2>',
        html,
        count=1,
    )
    html = html.replace(
        '<div class="eyebrow">Carnage Board</div><h2>Everybody\'s worst hole.</h2>',
        '<div class="section-kicker">Everybody\'s worst hole.</div><h2>Carnage Board</h2>',
        1,
    )
    html = re.sub(
        r'<div class="eyebrow">Player by player</div><h2>((?:Net|Gross) order\. (?:Gross|Net) context\.)</h2>',
        r'<div class="section-kicker">\1</div><h2>Player by player</h2>',
        html,
        count=1,
    )

    html = re.sub(
        r'<p class="sectionlead">(?:Net determines the tournament\. Gross and SGT strokes gained explain the golf underneath it\.|Gross determines this scratch tournament\. Net is secondary; SGT strokes gained explains the golf underneath it\.)</p>',
        "",
        html,
        count=1,
    )

    leaderboard_size = max(
        len((analysis.get("leaderboard") or {}).get("net", [])),
        len((analysis.get("leaderboard") or {}).get("gross", [])),
    )
    if leaderboard_size > 15:
        html = html.replace(
            "</aside></div></div></section>",
            '<div class="leader-scroll-note">Scroll for full leaderboard ↓</div></aside></div></div></section>',
            1,
        )

    html = compact_recap_cards(html)

    recap_css = r'''
<style>
.sectionhead.marked .section-kicker{color:#b6f34a;font-weight:850;letter-spacing:.015em;font-size:clamp(16px,1.6vw,22px);margin-bottom:8px}
@media (min-width:821px){
  .recap-summary .tourney-board{margin-top:-150px;position:relative;z-index:2}
}
.recap-summary .leaderboard-view{max-height:750px;overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable}
.recap-summary .leader-scroll-note{padding-top:12px;color:#9ba79d;font-size:11px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;text-align:center}
.hole-grid{gap:10px}
.hole-card{padding:12px 16px}
.hole-card.is-open{padding:18px 20px}
.hole-card .shot-trail{display:none}
.hole-card>p{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:1;overflow:hidden;margin:6px 0 0}
.hole-card.is-open .shot-trail{display:flex}
.hole-card.is-open>p{display:block;-webkit-line-clamp:unset;overflow:visible;margin-top:12px}
.recap-players{gap:10px}
.recap-players article{padding:12px 16px;min-height:0}
.recap-players article.is-open{padding:18px 20px}
.recap-players .player-roast{margin-bottom:8px}
.recap-players .round-details[hidden]{display:none}
.recap-players .round-details p{margin-bottom:0}
.recap-expand{margin-top:8px}
.is-open .recap-expand{margin-top:12px}
.expand-control{width:100%;display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid #314137;border-radius:11px;background:#0f1711;color:#b6f34a;padding:8px 11px;font:inherit;font-size:10px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;cursor:pointer}
.expand-control span{font-size:17px;line-height:1}
@media (max-width:820px){
  .recap-summary .tourney-board{margin-top:0}
  .recap-summary .leaderboard-view{max-height:750px}
}
</style>
'''
    return html.replace("</head>", recap_css + "</head>", 1)


def gross_primary_recap_page(event: dict, analysis: dict, copy: dict, cfg: dict, excluded: bool) -> str:
    html = _original_recap_page(event, analysis, copy, cfg, excluded)
    if competition_mode(event, cfg) == "gross":
        html = (
            html.replace("🏆 Net champion", "🏆 Gross champion")
            .replace("Net challenger", "Gross challenger")
            .replace("Gross winner", "Net standings leader", 1)
            .replace("Gross runner-up", "Net standings runner-up", 1)
            .replace("The net race first. Then the wreckage underneath it.", "The gross race first. Then the wreckage underneath it.")
            .replace(
                "Net determines the tournament. Gross and SGT strokes gained explain the golf underneath it.",
                "Gross determines this scratch tournament. Net is secondary; SGT strokes gained explains the golf underneath it.",
            )
            .replace('data-board="net" aria-pressed="true">Net</button>', 'data-board="net" aria-pressed="true">Gross</button>')
            .replace('data-board="gross" aria-pressed="false">Gross</button>', 'data-board="gross" aria-pressed="false">Net</button>')
            .replace("Net order. Gross context.", "Gross order. Net context.")
        )
        html = re.sub(
            r"<span>NET ([^<]+?) · GROSS ([^<]+?)</span>",
            r"<span>GROSS \2 · NET \1</span>",
            html,
        )

    return scalable_recap_layout(html, analysis)


renderer.analysis_map = normalized_analysis_map
renderer.landing = gross_primary_landing
renderer.recap_page = gross_primary_recap_page


if __name__ == "__main__":
    renderer.main()
