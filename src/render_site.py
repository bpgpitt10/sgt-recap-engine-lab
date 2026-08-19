from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CSS = r'''
:root{--bg:#0b120e;--panel:#121b15;--panel2:#172219;--text:#f3f1e8;--muted:#9ba79d;--lime:#b6f34a;--sage:#7f966c;--brown:#8b6f57;--yellow:#f4d35e;--line:#27362c;--max:1180px}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 85% -10%,#1a2c20 0,transparent 30%),var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.5}a{color:inherit;text-decoration:none}.wrap{max-width:var(--max);margin:auto;padding:0 24px}.nav{position:sticky;top:0;z-index:20;background:rgba(11,18,14,.9);backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}.navin{height:64px;display:flex;align-items:center;justify-content:space-between}.brand{font-weight:900;letter-spacing:.04em}.brand span{color:var(--lime)}.links{display:flex;gap:22px;color:var(--muted);font-size:14px}.section{padding:60px 0;border-top:1px solid var(--line)}#latest{border-top:0;padding-top:54px;background:radial-gradient(circle at 86% 0,rgba(182,243,74,.07),transparent 27%)}.eyebrow,.scope-label{color:var(--lime);font-weight:800;letter-spacing:.12em;text-transform:uppercase;font-size:12px}.latest-intro,.sectionhead{display:flex;align-items:end;justify-content:space-between;gap:24px;margin-bottom:28px}.latest-intro h1{font-size:clamp(54px,8vw,100px);line-height:.9;letter-spacing:-.06em;margin:8px 0 0}.section h2{font-size:clamp(34px,5vw,58px);letter-spacing:-.04em;margin:0}.sectionlead{color:var(--muted);max-width:560px}.latest-card{display:grid;grid-template-columns:1.15fr .85fr;gap:18px;background:linear-gradient(145deg,var(--panel2),var(--panel));border:1px solid #46632c;border-radius:24px;padding:32px;box-shadow:0 22px 54px rgba(0,0,0,.14)}.latest-card h3{font-size:clamp(30px,4vw,50px);letter-spacing:-.04em;margin:4px 0 12px}.latest-card p{color:#d6ddd7;font-size:17px}.latest-score{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;align-content:start}.latest-score div{background:#0f1711;border:1px solid var(--line);border-radius:14px;padding:16px}.latest-score small{display:block;color:var(--muted);text-transform:uppercase;font-size:10px}.latest-score b{display:block;font-size:21px;margin-top:5px}.cta{display:inline-flex;margin-top:12px;color:var(--lime);font-weight:900;font-size:13px;text-transform:uppercase;letter-spacing:.06em}.stories{display:grid;grid-template-columns:1.3fr .7fr;gap:18px}.storybox,.asidebox{background:var(--panel);border:1px solid var(--line);border-radius:22px;padding:28px}.storybox h3,.asidebox h3{margin:0 0 16px;font-size:24px}.storybox p{font-size:18px;line-height:1.62;color:#d9e0da}.storybox li{margin:10px 0;color:#d1d9d3}.storybox li::marker{color:var(--lime)}.board-head,.scouting-meta{display:flex;align-items:center;justify-content:space-between;gap:14px}.toggle{display:inline-flex;padding:3px;background:#0d150f;border:1px solid #344638;border-radius:11px}.toggle button{border:0;background:transparent;color:var(--muted);font:inherit;font-size:11px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;padding:7px 11px;border-radius:8px;cursor:pointer}.toggle button.active{background:var(--lime);color:#0b120e}.rank{display:flex;justify-content:space-between;gap:14px;padding:9px 0;border-bottom:1px solid var(--line)}.rank:last-child{border-bottom:0}.rank span{color:var(--muted);font-size:12px}.rank em{font-style:normal;color:#69766d;font-size:10px;margin-left:5px}.players{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.player{position:relative;overflow:hidden;background:linear-gradient(160deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:24px;padding:28px;min-height:465px}.ghost{position:absolute;right:20px;top:-32px;font-size:120px;font-weight:900;color:#223127;opacity:.8;line-height:1}.player h3{font-size:32px;margin:0 0 4px}.tag{color:var(--lime);font-weight:800;text-transform:uppercase;letter-spacing:.06em;font-size:12px}.chips{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:22px 0}.chip{background:#101812;border:1px solid var(--line);border-radius:14px;padding:13px 10px}.chip b{display:block;font-size:22px}.chip small{color:var(--muted);font-size:10px;text-transform:uppercase}.player p{color:#dbe1dc}.fingerprint{margin-top:24px;display:grid;grid-template-columns:58px 1fr 48px;gap:10px 12px;align-items:center;font-size:12px;color:var(--muted)}.bar{height:9px;background:#202c24;border-radius:5px;position:relative}.bar:after{content:'';position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:#78847b}.bar i{position:absolute;top:1px;height:7px;border-radius:4px;max-width:50%}.bar i.pos{left:50%;background:var(--sage)}.bar i.neg{right:50%;background:var(--brown)}.fingerprint b{text-align:right;color:#aeb9b1}.events{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.event{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:20px}.event .course{color:var(--muted);font-size:13px}.special{display:inline-flex;padding:4px 8px;border:1px solid #5d4f31;border-radius:999px;color:var(--yellow);font-size:9px;font-weight:900;letter-spacing:.08em;text-transform:uppercase}.winners{display:flex;gap:10px;margin-top:14px}.winner{flex:1;padding:11px;background:#0f1711;border-radius:12px}.winner small{display:block;color:var(--muted);font-size:9px;text-transform:uppercase}.winner b{font-size:14px}.footer{padding:42px 0 60px;color:var(--muted);font-size:13px}
.recap-hero{padding:76px 0 54px;border-bottom:1px solid var(--line);background:linear-gradient(145deg,#0b120e 12%,#101a13 58%,#0c140f 100%)}.recap-hero h1{font-size:clamp(58px,10vw,112px);line-height:.86;letter-spacing:-.06em;margin:12px 0 22px}.recap-dek{font-size:clamp(19px,2.2vw,27px);color:#d6ddd7;max-width:850px}.winner-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:28px}.winner-card{background:linear-gradient(145deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:20px;padding:19px}.winner-card.primary{border-color:#436126}.winner-card small{display:block;color:var(--muted);text-transform:uppercase;font-size:10px}.winner-card b{display:block;font-size:21px;margin-top:7px}.winner-card strong{display:block;color:var(--lime);font-size:32px}.recap-grid{display:grid;grid-template-columns:1.3fr .7fr;gap:18px}.big-copy{font-size:20px;line-height:1.6}.hole-grid,.recap-players{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.hole-card,.recap-player{background:linear-gradient(155deg,#162018,#101712);border:1px solid #314137;border-radius:20px;padding:22px}.hole-card.champ{border-color:#705436}.hole-top{display:flex;justify-content:space-between;gap:15px}.hole-score{font-size:28px;font-weight:900;color:var(--yellow)}.recap-player h3{margin:0;font-size:24px}.roast{color:var(--sage);font-weight:800;font-size:13px;margin:4px 0 10px}.state p{font-size:19px;color:#d6ddd7;max-width:850px}
@media(max-width:820px){.links{display:none}.latest-intro,.sectionhead{align-items:flex-start;flex-direction:column}.latest-card,.stories,.recap-grid{grid-template-columns:1fr}.players,.hole-grid,.recap-players{grid-template-columns:1fr}.events{grid-template-columns:1fr}.winner-grid{grid-template-columns:repeat(2,1fr)}.chips{grid-template-columns:repeat(2,1fr)}.player{min-height:0}.scouting-meta{align-items:flex-start;flex-direction:column}.section{padding:42px 0}}
'''

JS = r'''
const HISTORY=window.HISTORY, COPY=window.LEAGUE_COPY;
const fmt=n=>n==null?'—':Number(n).toFixed(1).replace(/\.0$/,'');
function scopeLabel(s){return s==='all'?'All Data':`Last ${s}`}
function profileCard(p,c){const sg=p.sg||{};const vals=[['TEE',sg.tee],['APP',sg.approach],['SHORT',sg.shortGame],['PUTT',sg.putting]];const max=8;const bars=vals.map(([k,v])=>{const n=Number(v||0),w=Math.min(50,Math.abs(n)/max*50);return `<span>${k}</span><div class="bar"><i class="${n>=0?'pos':'neg'}" style="width:${w}%"></i></div><b>${n>=0?'+':''}${fmt(n)}</b>`}).join('');return `<article class="player"><div class="ghost">${fmt(p.avgNet)}</div><h3>${p.name}</h3><div class="tag">${p.evidenceLevel==='strong_trend'?'Established file':p.evidenceLevel==='trend'?'Trend forming':'Small sample'}</div><div class="chips"><div class="chip"><b>${p.starts}</b><small>Starts</small></div><div class="chip"><b>${fmt(p.avgNet)}</b><small>Avg Net</small></div><div class="chip"><b>${p.grossWins}</b><small>Gross Wins</small></div><div class="chip"><b>${p.netWins}</b><small>Net Wins</small></div></div><p>${c?.profile||''}</p><div class="fingerprint">${bars}</div></article>`}
function renderScope(scope){const h=HISTORY.scopes[scope],c=COPY.scopes[scope];document.querySelectorAll('[data-scope]').forEach(b=>b.classList.toggle('active',b.dataset.scope===scope));document.querySelector('#scope-status').textContent=`Viewing ${scopeLabel(scope)} · ${h.eventCount} eligible events`;document.querySelector('#league-summary').textContent=c.leagueSummary;document.querySelector('#league-bullets').innerHTML=c.leagueBullets.map(x=>`<li>${x}</li>`).join('');const profileByName=Object.fromEntries(c.profiles.map(x=>[x.name,x]));document.querySelector('#players-grid').innerHTML=h.players.map(p=>profileCard(p,profileByName[p.name])).join('');renderBoard(scope,document.querySelector('[data-board].active')?.dataset.board||'net')}
function renderBoard(scope,kind){const h=HISTORY.scopes[scope];document.querySelectorAll('[data-board]').forEach(b=>b.classList.toggle('active',b.dataset.board===kind));document.querySelector('#ranks').innerHTML=h.players.map((p,i)=>`<div class="rank"><b>${i+1} · ${p.name}</b><span>${fmt(kind==='net'?p.avgNet:p.avgGross)} <em>${p.starts} starts</em></span></div>`).join('')}
document.addEventListener('click',e=>{if(e.target.matches('[data-scope]'))renderScope(e.target.dataset.scope);if(e.target.matches('[data-board]'))renderBoard(document.querySelector('[data-scope].active').dataset.scope,e.target.dataset.board)});renderScope(HISTORY.defaultScope);
'''


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def e(value: object) -> str:
    return html.escape("" if value is None else str(value))


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def display_total(value: object) -> str:
    return e(value if value is not None else "—")


def standings_cards(analysis: dict) -> tuple[str, str, str, str]:
    net = analysis.get("leaderboard", {}).get("net", [])
    gross = analysis.get("leaderboard", {}).get("gross", [])
    champion = net[0] if net else {}
    challenger = net[1] if len(net) > 1 else {}
    gross_winner = gross[0] if gross else {}
    gross_runner = gross[1] if len(gross) > 1 else {}
    return (
        f"{e(champion.get('name'))} · {display_total(champion.get('total'))}",
        f"{e(challenger.get('name'))} · {display_total(challenger.get('total'))}",
        f"{e(gross_winner.get('name'))} · {display_total(gross_winner.get('total'))}",
        f"{e(gross_runner.get('name'))} · {display_total(gross_runner.get('total'))}",
    )


def landing(history: dict, league_copy: dict, analyses: dict[int, dict], copies: dict[int, dict]) -> str:
    latest = history["completedEvents"][0]
    latest_id = int(latest["id"])
    if latest_id not in analyses or latest_id not in copies:
        raise RuntimeError(f"Latest completed event {latest_id} is missing analysis or recap copy")
    analysis, copy = analyses[latest_id], copies[latest_id]
    net_champ, net_challenger, gross_winner, gross_runner = standings_cards(analysis)
    archive = []
    excluded = {int(x["id"]) for x in history.get("excludedProfileEvents", [])}
    for event in history["completedEvents"]:
        event_id = int(event["id"])
        link = f"recaps/{event_id}.html" if event_id in copies else "#"
        special = '<span class="special">Excluded from player DNA</span>' if event_id in excluded else ''
        archive.append(f'''<a class="event" href="{link}">{special}<div class="eyebrow">{e(event.get('displayDate'))}</div><h3>{e(event.get('tourName'))}</h3><div class="course">{e(event.get('course'))}</div><div class="winners"><div class="winner"><small>Net winner</small><b>{e(event.get('netWinner'))}</b></div><div class="winner"><small>Gross winner</small><b>{e(event.get('grossWinner'))}</b></div></div></a>''')
    scope_buttons = ''.join(f'<button data-scope="{s}">{"All" if s=="all" else "Last "+s}</button>' for s in history["availableScopes"])
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(history['tour']['name'])}</title><style>{CSS}</style></head><body><nav class="nav"><div class="wrap navin"><a class="brand" href="#latest">HIGH LOFT <span>/</span> LOW STANDARDS</a><div class="links"><a href="#latest">Latest</a><a href="#league">League Snapshot</a><a href="#players">Scouting Files</a><a href="#events">Tournaments</a></div></div></nav><main><section class="section" id="latest"><div class="wrap"><div class="latest-intro"><div><div class="eyebrow">Latest tournament</div><h1>{e(latest.get('tourName'))}</h1></div><p class="sectionlead">{e(copy['latestTournamentTeaser'])}</p></div><a class="latest-card" href="recaps/{latest_id}.html"><div><div class="eyebrow">{e(latest.get('displayDate'))} · {e(latest.get('course'))}</div><h3>{e(copy['thirtySeconds'].split('.')[0])}.</h3><p>{e(copy['thirtySeconds'])}</p><span class="cta">Read full recap →</span></div><div class="latest-score"><div><small>🏆 Net champion</small><b>{net_champ}</b></div><div><small>Net challenger</small><b>{net_challenger}</b></div><div><small>Gross winner</small><b>{gross_winner}</b></div><div><small>Gross runner-up</small><b>{gross_runner}</b></div></div></a></div></section><section class="section" id="league"><div class="wrap"><div class="sectionhead"><div><div class="scope-label">Rolling league snapshot</div><h2>The golf right now.</h2></div><p class="sectionlead">Rolling windows follow the league's latest eligible events. Skips are neutral; team/special events can stay in the archive without contaminating individual player DNA.</p></div><div class="stories"><div class="storybox"><h3>What the numbers say</h3><p id="league-summary"></p><ul id="league-bullets"></ul></div><aside class="asidebox"><div class="board-head"><h3>Average finish</h3><div class="toggle"><button class="active" data-board="net">Net</button><button data-board="gross">Gross</button></div></div><div id="ranks"></div></aside></div></div></section><section class="section" id="players"><div class="wrap"><div class="sectionhead"><div><div class="eyebrow">Scouting files</div><h2>Player profiles</h2></div><div class="scouting-meta"><div><div class="toggle">{scope_buttons}</div><div id="scope-status" class="sectionlead"></div></div><p class="sectionlead">The numbers change. The tendencies linger. This is the closest thing we have to each player’s golfing DNA.</p></div></div><div class="players" id="players-grid"></div></div></section><section class="section" id="events"><div class="wrap"><div class="sectionhead"><div><div class="eyebrow">Tournament archive</div><h2>Every completed event.</h2></div></div><div class="events">{''.join(archive)}</div></div></section></main><footer class="footer"><div class="wrap">High Loft / Low Standards · automated lab build</div></footer><script>window.HISTORY={json.dumps(history, separators=(',',':'))};window.LEAGUE_COPY={json.dumps(league_copy, separators=(',',':'))};{JS}</script></body></html>'''


def recap(event: dict, analysis: dict, copy: dict) -> str:
    net_champ, net_challenger, gross_winner, gross_runner = standings_cards(analysis)
    carnage = []
    carnage_copy = {x["name"]: x["commentary"] for x in copy.get("carnage", [])}
    for i, item in enumerate(analysis.get("carnage", [])):
        classes = "hole-card champ" if i == 0 else "hole-card"
        carnage.append(f'''<article class="{classes}"><div class="hole-top"><div><div class="eyebrow">{'🏆 Carnage Champion' if i==0 else 'Worst hole'}</div><span class="player-name">{e(item.get('name'))}</span><div>Hole {e(item.get('hole'))} · Par {e(item.get('par'))}</div></div><div class="hole-score">{e(item.get('gross'))} <small>({item.get('grossToPar'):+d})</small></div></div><p>{e(carnage_copy.get(item.get('name'),'') )}</p></article>''')
    by_copy = {x["name"]: x for x in copy.get("players", [])}
    players = []
    for p in analysis.get("players", []):
        if not p.get("completed"): continue
        c = by_copy.get(p.get("name"), {})
        lb = p.get("leaderboard", {})
        players.append(f'''<article class="recap-player"><div class="eyebrow">Net {e(lb.get('netPosition'))} · Gross {e(lb.get('grossPosition'))}</div><h3>{e(p.get('name'))}</h3><div class="roast">{e(c.get('tagline'))}</div><p>{e(c.get('body'))}</p></article>''')
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(event.get('tourName'))} recap</title><style>{CSS}</style></head><body><nav class="nav"><div class="wrap navin"><a class="brand" href="../index.html">HIGH LOFT <span>/</span> LOW STANDARDS</a><div class="links"><a href="../index.html">League home</a></div></div></nav><header class="recap-hero"><div class="wrap"><div class="eyebrow">Tournament recap · {e(event.get('displayDate'))}</div><h1>{e(event.get('tourName'))}</h1><p class="recap-dek">{e(copy.get('latestTournamentTeaser'))}</p><div class="winner-grid"><div class="winner-card primary"><small>🏆 Net champion</small><b>{net_champ}</b></div><div class="winner-card"><small>Net challenger</small><b>{net_challenger}</b></div><div class="winner-card"><small>Gross winner</small><b>{gross_winner}</b></div><div class="winner-card"><small>Gross runner-up</small><b>{gross_runner}</b></div></div></div></header><main><section class="section"><div class="wrap recap-grid"><div class="storybox"><div class="eyebrow">Tournament in 30 seconds</div><p class="big-copy">{e(copy.get('thirtySeconds'))}</p></div><aside class="asidebox"><h3>Tournament leaderboard</h3><div>{''.join(f'<div class="rank"><b>{r.get("position")} · {e(r.get("name"))}</b><span>{e(r.get("total"))}</span></div>' for r in analysis.get('leaderboard',{}).get('net',[]))}</div></aside></div></section><section class="section"><div class="wrap"><div class="sectionhead"><div><div class="eyebrow">Carnage Board</div><h2>Everybody’s worst hole.</h2></div></div><div class="hole-grid">{''.join(carnage)}</div></div></section><section class="section"><div class="wrap"><div class="sectionhead"><div><div class="eyebrow">Player by player</div><h2>The individual damage report.</h2></div></div><div class="recap-players">{''.join(players)}</div></div></section><section class="section state"><div class="wrap"><div class="eyebrow">State of the league</div><h2>What changed?</h2><p>{e(copy.get('stateOfLeague'))}</p></div></section></main><footer class="footer"><div class="wrap"><a class="cta" href="../index.html">← Back to league home</a></div></footer></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("site"))
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    history = load(ROOT / "data/history.json")
    league_copy = load(ROOT / "data/league-copy.json")
    analyses, copies = {}, {}
    for event in history["completedEvents"]:
        event_id = int(event["id"])
        ap = ROOT / "data/analysis" / f"{event_id}.json"
        cp = ROOT / "data/copy" / f"{event_id}.json"
        if ap.exists(): analyses[event_id] = load(ap)
        if cp.exists(): copies[event_id] = load(cp)
    output.mkdir(parents=True, exist_ok=True)
    (output / "recaps").mkdir(exist_ok=True)
    (output / "index.html").write_text(landing(history, league_copy, analyses, copies), encoding="utf-8")
    for event in history["completedEvents"]:
        event_id = int(event["id"])
        if event_id in analyses and event_id in copies:
            (output / "recaps" / f"{event_id}.html").write_text(recap(event, analyses[event_id], copies[event_id]), encoding="utf-8")
    print(f"Rendered {output.relative_to(ROOT)} with {len(copies)} recap pages")

if __name__ == "__main__": main()
