from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def fmt_finish(value: object) -> str:
    if value is None:
        return "—"
    try:
        n = float(value)
    except (TypeError, ValueError):
        return esc(value)
    return f"{n:.1f}".rstrip("0").rstrip(".")


def score(value: object) -> str:
    if value is None:
        return "—"
    value = str(value)
    return "E" if value in {"0", "+0", "-0", "E"} else esc(value)


def config() -> dict:
    return load(ROOT / "config.json")


def recap_slug(event: dict, cfg: dict) -> str:
    mapped = ((cfg.get("site") or {}).get("recapSlugs") or {}).get(str(event["id"]))
    return mapped or slugify(event.get("tourName") or event.get("name") or f"event-{event['id']}")


def analysis_map() -> dict[int, dict]:
    out = {}
    for path in (ROOT / "data" / "analysis").glob("*.json"):
        data = load(path)
        out[int(data["tournament"]["id"])] = data
    return out


def copy_for(event_id: int) -> dict:
    path = ROOT / "data" / "copy" / f"{event_id}.json"
    if not path.exists():
        raise RuntimeError(f"Missing current recap copy: {path}")
    return load(path)


def standing_by_name(analysis: dict) -> dict[str, dict]:
    return {p["name"]: p for p in analysis.get("players", []) if p.get("completed")}


def board_html(rows: list[dict]) -> str:
    return "".join(
        f'<div class="metric-row"><span>{i} · {esc(row.get("name"))}</span><b>{score(row.get("total"))}</b></div>'
        for i, row in enumerate(rows, 1)
    )


def latest_cards(analysis: dict) -> tuple[str, str, str, str]:
    net = analysis.get("leaderboard", {}).get("net", [])
    gross = analysis.get("leaderboard", {}).get("gross", [])
    champion = net[0] if net else {}
    challenger = net[1] if len(net) > 1 else {}
    gross_winner = gross[0] if gross else {}
    gross_runner = gross[1] if len(gross) > 1 else {}
    return (
        f'{esc(champion.get("name"))} · {score(champion.get("total"))}',
        f'{esc(challenger.get("name"))} · {score(challenger.get("total"))}',
        f'{esc(gross_winner.get("name"))} · {score(gross_winner.get("total"))}',
        f'{esc(gross_runner.get("name"))} · {score(gross_runner.get("total"))}',
    )


def archive_html(history: dict, analyses: dict[int, dict], cfg: dict, production_root: Path, latest_id: int, latest_slug: str) -> str:
    excluded = {int(x["id"]) for x in history.get("excludedProfileEvents", [])}
    cards = []
    for event in history.get("completedEvents", []):
        event_id = int(event["id"])
        slug = recap_slug(event, cfg)
        if event_id != latest_id:
            existing = production_root / "recaps" / f"{slug}.html"
            if not existing.exists():
                raise RuntimeError(f"Historical recap is missing and would create a dead archive link: {existing}")
        analysis = analyses.get(event_id) or {}
        winners = analysis.get("winners") or {}
        net_name = (winners.get("net") or {}).get("name") or event.get("netWinner") or "—"
        gross_name = (winners.get("gross") or {}).get("name") or event.get("grossWinner") or "—"
        badge = '<span class="special">Team/special event · excluded from player DNA</span>' if event_id in excluded else ""
        cards.append(
            f'''<a class="event" href="recaps/{esc(slug)}.html">{badge}<div class="eyebrow">{esc(event.get('displayDate'))}</div><h3>{esc(event.get('tourName') or event.get('name'))}</h3><div class="course">{esc(event.get('course'))}</div><div class="winners"><div class="winner"><small>Net winner</small><b>{esc(net_name)}</b></div><div class="winner"><small>Gross winner</small><b>{esc(gross_name)}</b></div></div></a>'''
        )
    return "".join(cards)


def landing(history: dict, league_copy: dict, analyses: dict[int, dict], latest_copy: dict, cfg: dict, production_root: Path) -> str:
    latest_event = history["completedEvents"][0]
    latest_id = int(latest_event["id"])
    latest_analysis = analyses[latest_id]
    latest_slug = recap_slug(latest_event, cfg)
    net_champ, net_challenger, gross_winner, gross_runner = latest_cards(latest_analysis)
    archive = archive_html(history, analyses, cfg, production_root, latest_id, latest_slug)

    data_history = json.dumps(history, ensure_ascii=False).replace("</", "<\\/")
    data_copy = json.dumps(league_copy, ensure_ascii=False).replace("</", "<\\/")
    scope_buttons = "".join(
        f'<button type="button" data-profile-scope="{esc(s)}" aria-pressed="false">{"All Data" if s == "all" else "Last " + s}</button>'
        for s in history.get("availableScopes", [])
    )

    js = r'''
const HISTORY=window.HL_HISTORY, COPY=window.HL_COPY;
const fmt=n=>n==null?'—':Number(n).toFixed(1).replace(/\.0$/,'');
const scoreLabel=s=>s==='all'?'All Data':`Last ${s}`;
const escHtml=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function bar(label,v){const n=Number(v||0),w=Math.min(50,Math.abs(n)/8*50);return `<span>${label}</span><div class="bar"><i class="${n>=0?'pos':'neg'}" style="width:${w}%"></i></div><b>${n>=0?'+':''}${fmt(n)}</b>`}
function playerCard(p,c){const sg=p.sg||{};return `<article class="player"><div class="ghost">${fmt(p.avgNet)}</div><h3>${escHtml(p.name)}</h3><div class="tag">${escHtml(c?.tagline||'')}</div><div class="chips"><div class="chip"><b>${p.starts}</b><small>STARTS</small></div><div class="chip"><b>${fmt(p.avgNet)}</b><small>AVG NET</small></div><div class="chip"><b>${p.grossWins}</b><small>GROSS WINS</small></div><div class="chip"><b>${p.netWins}</b><small>NET WINS</small></div></div><p>${escHtml(c?.profile||'')}</p><div class="fingerprint">${bar('TEE',sg.tee)}${bar('APP',sg.approach)}${bar('SHORT',sg.shortGame)}${bar('PUTT',sg.putting)}</div></article>`}
function board(scope,kind){const h=HISTORY.scopes[scope];const players=[...h.players].sort((a,b)=>{const av=kind==='net'?a.avgNet:a.avgGross,bv=kind==='net'?b.avgNet:b.avgGross;return (av??999)-(bv??999)||(b.starts-a.starts)||String(a.name).localeCompare(String(b.name))});document.querySelectorAll('[data-season-board]').forEach(b=>{const active=b.dataset.seasonBoard===kind;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active))});document.querySelector('#rolling-ranks').innerHTML=players.map((p,i)=>`<div class="rank"><b>${i+1} · ${escHtml(p.name)}</b><span>${fmt(kind==='net'?p.avgNet:p.avgGross)} <em>${p.starts} starts</em></span></div>`).join('')}
function render(scope){const h=HISTORY.scopes[scope],c=COPY.scopes[scope];document.querySelectorAll('[data-profile-scope]').forEach(b=>{const active=b.dataset.profileScope===scope;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active))});document.querySelector('#scope-status').textContent=`Viewing ${scoreLabel(scope)} · ${h.eventCount} eligible event${h.eventCount===1?'':'s'}`;document.querySelector('#league-summary').textContent=c.leagueSummary;document.querySelector('#league-bullets').innerHTML=c.leagueBullets.map(x=>`<li>${escHtml(x)}</li>`).join('');const cp=Object.fromEntries(c.profiles.map(x=>[x.name,x]));document.querySelector('#players-grid').innerHTML=h.players.map(p=>playerCard(p,cp[p.name])).join('');board(scope,document.querySelector('[data-season-board].active')?.dataset.seasonBoard||'net')}
document.addEventListener('click',e=>{if(e.target.matches('[data-profile-scope]'))render(e.target.dataset.profileScope);if(e.target.matches('[data-season-board]'))board(document.querySelector('[data-profile-scope].active').dataset.profileScope,e.target.dataset.seasonBoard)});render(HISTORY.defaultScope);
'''

    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#0b120e"><title>High Loft / Low Standards</title><meta name="description" content="High Loft / Low Standards simulator golf recaps, rolling league analysis, and player scouting files."><link rel="stylesheet" href="assets/site.css"><link rel="stylesheet" href="assets/landing-v2.css"><style>.special{{display:inline-flex;margin-bottom:8px;padding:4px 8px;border:1px solid #5d4f31;border-radius:999px;color:#f4d35e;font-size:9px;font-weight:900;letter-spacing:.08em;text-transform:uppercase}}.fingerprint .bar{{height:9px;overflow:visible}}.fingerprint .bar:after{{content:'';position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:#78847b}}.fingerprint .bar i{{position:absolute;top:1px;height:7px;max-width:50%}}.fingerprint .bar i.pos{{left:50%;background:#7f966c}}.fingerprint .bar i.neg{{right:50%;background:#8b6f57}}</style></head><body class="landing-page"><nav class="nav"><div class="wrap navin"><a class="brand" href="#top">HIGH LOFT <span>/</span> LOW STANDARDS</a><div class="links"><a href="#latest">Latest</a><a href="#league">League Snapshot</a><a href="#players">Players</a><a href="#events">Tournaments</a></div></div></nav><main id="top">
<section class="section" id="latest"><div class="wrap"><div class="latest-intro"><div><div class="eyebrow">Latest tournament recap</div><h1>{esc(latest_event.get('tourName') or latest_event.get('name'))}</h1></div><p class="sectionlead">{esc(latest_copy.get('latestTournamentTeaser'))}</p></div><a class="latest-card featured" href="recaps/{esc(latest_slug)}.html"><div><div class="eyebrow">{esc(latest_event.get('displayDate'))} · {esc(latest_event.get('course'))}</div><h3>{esc(latest_copy.get('latestTournamentTeaser'))}</h3><p>{esc(latest_copy.get('thirtySeconds'))}</p><span class="cta">Read the full recap →</span></div><div class="latest-score"><div><small>🏆 Net champion</small><b>{net_champ}</b></div><div><small>Net challenger</small><b>{net_challenger}</b></div><div><small>Gross winner</small><b>{gross_winner}</b></div><div><small>Gross runner-up</small><b>{gross_runner}</b></div></div></a></div></section>
<section class="section" id="league"><div class="wrap"><div class="sectionhead"><div><div class="season-label">Rolling league snapshot</div><h2>The golf right now.</h2></div><p class="sectionlead">Net decides the league result. Gross and SGT strokes gained explain what the golf looks like underneath it. Rolling windows use eligible individual events; skips are neutral.</p></div><div class="stories"><div class="storybox season-story"><h3>What the numbers say</h3><p id="league-summary"></p><ul id="league-bullets"></ul></div><aside class="asidebox season-board"><div class="season-board-head"><h3>Average finish</h3><div class="season-toggle" role="group" aria-label="Average finish scoring"><button type="button" class="active" data-season-board="net" aria-pressed="true">Net</button><button type="button" data-season-board="gross" aria-pressed="false">Gross</button></div></div><div class="season-ranks" id="rolling-ranks"></div></aside></div></div></section>
<section class="section" id="players"><div class="wrap"><div class="sectionhead scouting-head"><div><div class="eyebrow">Scouting files</div><h2>Player profiles</h2></div><div class="scouting-meta"><div class="scope-block"><div class="profile-scope" role="group" aria-label="Player profile data scope">{scope_buttons}</div><span class="scope-status" id="scope-status" aria-live="polite"></span></div><p class="sectionlead">The numbers change. The tendencies linger. This is the closest thing we have to each player’s golfing DNA.</p></div></div><div class="players" id="players-grid"></div></div></section>
<section class="section" id="events"><div class="wrap"><div class="sectionhead"><div><div class="eyebrow">Tournament archive</div><h2>Every completed event.</h2></div></div><div class="events">{archive}</div></div></section>
</main><footer class="footer"><div class="wrap">High Loft / Low Standards · simulator golf with documentation.</div></footer><script>window.HL_HISTORY={data_history};window.HL_COPY={data_copy};{js}</script></body></html>'''


def shot_trail(hole: dict) -> str:
    shots = hole.get("shots") or []
    if not shots:
        return ""
    pieces = []
    for shot in shots[:7]:
        pieces.append(f'<span>{esc(shot.get("number"))} · {esc(shot.get("description"))}</span>')
    return '<div class="shot-trail">' + '<i>›</i>'.join(pieces) + '</div>'


def recap_page(event: dict, analysis: dict, copy: dict, cfg: dict, excluded: bool) -> str:
    net = analysis.get("leaderboard", {}).get("net", [])
    gross = analysis.get("leaderboard", {}).get("gross", [])
    player_map = standing_by_name(analysis)
    copy_players = {p["name"]: p for p in copy.get("players", [])}
    carnage_copy = {c["name"]: c["commentary"] for c in copy.get("carnage", [])}
    champion = net[0] if net else {}
    challenger = net[1] if len(net) > 1 else {}
    gross_winner = gross[0] if gross else {}
    gross_runner = gross[1] if len(gross) > 1 else {}

    carnage_cards = []
    for idx, item in enumerate(analysis.get("carnage", [])):
        name = item.get("name")
        hole = item.get("hole") or {}
        damage = int(hole.get("grossToPar") or 0)
        cls = " disaster" if damage >= 4 else " warning" if damage >= 3 else ""
        award = f'<div class="award-kicker">🏆 CARNAGE CHAMPION · +{damage}</div>' if idx == 0 else ""
        carnage_cards.append(
            f'''<article class="hole-card{cls}">{award}<div class="hole-top"><div><span class="player-name">{esc(name)}</span><small>Hole {esc(hole.get('hole'))} · Par {esc(hole.get('par'))}</small></div><div class="hole-score"><b>{esc(hole.get('gross'))}</b><span>{'+' if damage > 0 else ''}{damage}</span></div></div>{shot_trail(hole)}<p>{esc(carnage_copy.get(name, ''))}</p></article>'''
        )

    player_cards = []
    for place, row in enumerate(net, 1):
        name = row.get("name")
        player = player_map.get(name) or {}
        lb = player.get("leaderboard") or {}
        cp = copy_players.get(name) or {}
        player_cards.append(
            f'''<article><div class="place">{place}</div><h3>{esc(name)} <span>NET {score(lb.get('netTotal'))} · GROSS {score(lb.get('grossTotal'))}</span></h3><p class="player-roast">{esc(cp.get('tagline'))}</p><p>{esc(cp.get('body'))}</p></article>'''
        )

    special = " · Team/special format" if excluded else ""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#0b120e"><title>{esc(event.get('tourName') or event.get('name'))} Recap — High Loft / Low Standards</title><meta name="description" content="High Loft / Low Standards tournament recap."><link rel="stylesheet" href="../assets/site.css"><link rel="stylesheet" href="../assets/recap-v2.css"></head><body class="recap-page"><nav class="nav"><div class="wrap navin"><a class="brand" href="../index.html">HIGH LOFT <span>/</span> LOW STANDARDS</a><div class="links"><a href="#top">Recap</a><a href="#carnage">Carnage</a><a href="#players">Players</a><a href="../index.html#league">League</a></div></div></nav><main id="top">
<section class="recap-hero"><div class="wrap recap-hero-inner"><div class="eyebrow">Tournament recap · {esc(event.get('displayDate'))}{special}</div><div class="hero-title-row"><h1>{esc(event.get('tourName') or event.get('name'))}</h1><div class="hero-mark" aria-hidden="true">HL</div></div><p class="recap-dek">{esc(copy.get('latestTournamentTeaser'))}</p><div class="winner-grid"><div class="winner-card primary"><small>🏆 Net champion</small><b>{esc(champion.get('name'))}</b><strong>{score(champion.get('total'))}</strong></div><div class="winner-card primary"><small>Net challenger</small><b>{esc(challenger.get('name'))}</b><strong>{score(challenger.get('total'))}</strong></div><div class="winner-card"><small>Gross winner</small><b>{esc(gross_winner.get('name'))}</b><strong>{score(gross_winner.get('total'))}</strong></div><div class="winner-card"><small>Gross runner-up</small><b>{esc(gross_runner.get('name'))}</b><strong>{score(gross_runner.get('total'))}</strong></div></div></div></section>
<section class="section recap-summary"><div class="wrap"><div class="sectionhead marked"><div class="section-title"><span class="section-mark">01</span><div><div class="eyebrow">Tournament in 30 seconds</div><h2>The net race first. Then the wreckage underneath it.</h2></div></div><p class="sectionlead">Net determines the tournament. Gross and SGT strokes gained explain the golf underneath it.</p></div><div class="recap-grid"><div class="storybox feature-copy"><p class="big-copy">{esc(copy.get('thirtySeconds'))}</p></div><aside class="asidebox tourney-board"><div class="board-head"><h3>Tournament leaderboard</h3><div class="leader-toggle"><button type="button" class="active" data-board="net" aria-pressed="true">Net</button><button type="button" data-board="gross" aria-pressed="false">Gross</button></div></div><div class="leaderboard-view" data-view="net">{board_html(net)}</div><div class="leaderboard-view" data-view="gross" hidden>{board_html(gross)}</div></aside></div></div></section>
<section class="section carnage-section" id="carnage"><div class="wrap"><div class="sectionhead marked"><div class="section-title"><span class="section-mark">02</span><div><div class="eyebrow">Carnage Board</div><h2>Everybody's worst hole.</h2></div></div><p class="sectionlead">Ordered by score relative to par. Shot absurdity breaks ties. Nobody gets to hide.</p></div><div class="hole-grid">{''.join(carnage_cards)}</div></div></section>
<section class="section player-section" id="players"><div class="wrap"><div class="sectionhead marked"><div class="section-title"><span class="section-mark">03</span><div><div class="eyebrow">Player by player</div><h2>Net order. Gross context.</h2></div></div><p class="sectionlead">Roast first. Then enough data to explain what actually happened.</p></div><div class="recap-players expanded">{''.join(player_cards)}</div></div></section>
<section class="section state"><div class="wrap"><div class="sectionhead marked"><div class="section-title"><span class="section-mark">04</span><div><div class="eyebrow">State of the league</div><h2>What this one changes.</h2></div></div></div><p>{esc(copy.get('stateOfLeague'))}</p><div class="next-links"><a href="../index.html">← League home</a><a href="../index.html#events">Tournament archive</a></div></div></section>
</main><footer class="footer"><div class="wrap">High Loft / Low Standards · simulator golf with documentation.</div></footer><script>document.addEventListener('click',e=>{{if(!e.target.matches('[data-board]'))return;const kind=e.target.dataset.board;document.querySelectorAll('[data-board]').forEach(b=>{{const a=b.dataset.board===kind;b.classList.toggle('active',a);b.setAttribute('aria-pressed',String(a))}});document.querySelectorAll('[data-view]').forEach(v=>v.hidden=v.dataset.view!==kind)}});</script></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the production High Loft site without rewriting historical recaps.")
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("site-high-loft"))
    args = parser.parse_args()

    production_root = args.production_root.resolve()
    output = args.output if args.output.is_absolute() else (ROOT / args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "recaps").mkdir(parents=True, exist_ok=True)

    cfg = config()
    history = load(ROOT / "data" / "history.json")
    league_copy = load(ROOT / "data" / "league-copy.json")
    analyses = analysis_map()
    latest_event = history["completedEvents"][0]
    latest_id = int(latest_event["id"])
    latest_analysis = analyses[latest_id]
    latest_copy = copy_for(latest_id)
    latest_slug = recap_slug(latest_event, cfg)
    excluded = latest_id in {int(x["id"]) for x in history.get("excludedProfileEvents", [])}

    (output / "index.html").write_text(
        landing(history, league_copy, analyses, latest_copy, cfg, production_root),
        encoding="utf-8",
    )
    (output / "recaps" / f"{latest_slug}.html").write_text(
        recap_page(latest_event, latest_analysis, latest_copy, cfg, excluded),
        encoding="utf-8",
    )

    print(f"Rendered High Loft landing page and latest recap {latest_id} -> {latest_slug}.html")
    print("Historical recap files were intentionally not generated or rewritten.")


if __name__ == "__main__":
    main()
