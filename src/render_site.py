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
/* scalable league UI */
.scouting-card{min-height:0;padding:24px}.scouting-card .scouting-details[hidden],.round-details[hidden]{display:none}.scouting-card .ghost{opacity:.55}.expand-control{margin-top:16px;width:100%;display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid #314137;border-radius:11px;background:#0f1711;color:var(--lime);padding:9px 11px;font:inherit;font-size:10px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;cursor:pointer}.expand-control span{font-size:17px;line-height:1}
.player-search,.recap-header-search{display:block;flex:0 1 320px;width:min(320px,100%);margin-left:auto}.player-search input,.recap-header-search input{width:100%;border:1px solid #314137;border-radius:12px;background:#0f1711;color:var(--text);padding:12px 14px;font:inherit;font-size:14px;outline:none}.player-search input:focus,.recap-header-search input:focus{border-color:#6c8c46;box-shadow:0 0 0 2px rgba(182,243,74,.08)}.player-search input::placeholder,.recap-header-search input::placeholder{color:#6f7b72}
.profile-directory{display:flex;justify-content:flex-end;margin:0 0 18px}.large-field-status{color:var(--muted);font-size:10px;font-weight:900;letter-spacing:.07em;text-transform:uppercase}.large-list-footer{display:flex;justify-content:center;margin-top:16px}.large-list-footer[hidden]{display:none!important}.large-list-button{border:1px solid #3e503f;border-radius:999px;background:#0f1711;color:var(--lime);padding:11px 16px;font:inherit;font-size:10px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;cursor:pointer}
#ranks.is-scrollable{max-height:560px;overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable;padding-right:4px}.season-scroll-note{padding-top:10px;color:#7f8b82;font-size:9px;font-weight:850;letter-spacing:.06em;text-transform:uppercase;text-align:center}.season-scroll-note[hidden]{display:none!important}
.recap-search-head{align-items:flex-end}.recap-player,.hole-card{min-height:0}.recap-player .roast{margin-bottom:8px}.recap-player .expand-control{margin-top:8px}
[data-profile-card][hidden],[data-player-card][hidden],[data-carnage-card][hidden],.event[hidden]{display:none!important}
@media(max-width:820px){.player-search,.recap-header-search{flex:0 0 auto;width:100%;max-width:none;margin-left:0}.profile-directory{justify-content:flex-start}.recap-search-head{align-items:stretch}}
'''

JS = r'''
const HISTORY=window.HISTORY, COPY=window.LEAGUE_COPY;
const PROFILE_PAGE_SIZE=12, ARCHIVE_INITIAL=6, ARCHIVE_PAGE_SIZE=10, SEASON_BOARD_VISIBLE=15;
let profileVisible=PROFILE_PAGE_SIZE, archiveVisible=ARCHIVE_INITIAL;
const fmt=n=>n==null?'—':Number(n).toFixed(1).replace(/\.0$/,'');
const escHtml=s=>String(s??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
function scopeLabel(s){return s==='all'?'All Data':`Last ${s}`}
function sgScale(players){let m=0;for(const p of players||[]){const sg=p.sg||{};for(const v of [sg.tee,sg.approach,sg.shortGame,sg.putting]){if(v!=null&&Number.isFinite(Number(v)))m=Math.max(m,Math.abs(Number(v)))}}return Math.max(3,Math.ceil(m))}
function profileCard(p,c,scale){
  const sg=p.sg||{}, vals=[['TEE',sg.tee],['APP',sg.approach],['SHORT',sg.shortGame],['PUTT',sg.putting]];
  const bars=vals.map(([k,v])=>{if(v==null||!Number.isFinite(Number(v)))return `<span>${k}</span><div class="bar"></div><b>—</b>`;const n=Number(v),w=Math.min(50,Math.abs(n)/scale*50);return `<span>${k}</span><div class="bar"><i class="${n>=0?'pos':'neg'}" style="width:${w}%"></i></div><b>${n>=0?'+':''}${fmt(n)}</b>`}).join('');
  return `<article class="player scouting-card" data-profile-card><div class="ghost">${fmt(p.avgNet)}</div><h3>${escHtml(p.name)}</h3><div class="tag">${escHtml(c?.tagline||'')}</div><div class="chips"><div class="chip"><b>${p.starts}</b><small>Starts</small></div><div class="chip"><b>${fmt(p.avgNet)}</b><small>Avg Net</small></div><div class="chip"><b>${p.grossWins}</b><small>Gross Wins</small></div><div class="chip"><b>${p.netWins}</b><small>Net Wins</small></div></div><div class="fingerprint">${bars}</div><div class="scouting-details" hidden><p>${escHtml(c?.profile||'')}</p></div><button type="button" class="expand-control" data-profile-expand aria-expanded="false">Read scouting file <span>+</span></button></article>`;
}
function renderBoard(scope,kind){
  const h=HISTORY.scopes[scope];
  const ps=[...h.players].sort((a,b)=>{const av=kind==='net'?a.avgNet:a.avgGross,bv=kind==='net'?b.avgNet:b.avgGross;return (av??999)-(bv??999)||(b.starts-a.starts)||String(a.name).localeCompare(String(b.name))});
  document.querySelectorAll('[data-board]').forEach(b=>b.classList.toggle('active',b.dataset.board===kind));
  document.querySelector('#ranks').innerHTML=ps.map((p,i)=>`<div class="rank"><b>${i+1} · ${escHtml(p.name)}</b><span>${fmt(kind==='net'?p.avgNet:p.avgGross)} <em>${p.starts} starts</em></span></div>`).join('');
  updateSeasonBoard();
}
function renderScope(scope){
  const h=HISTORY.scopes[scope],c=COPY.scopes[scope];
  document.querySelectorAll('[data-scope]').forEach(b=>b.classList.toggle('active',b.dataset.scope===scope));
  document.querySelector('#scope-status').textContent=`Viewing ${scopeLabel(scope)} · ${h.eventCount} eligible event${h.eventCount===1?'':'s'}`;
  document.querySelector('#league-summary').textContent=c.leagueSummary;
  document.querySelector('#league-bullets').innerHTML=c.leagueBullets.map(x=>`<li>${escHtml(x)}</li>`).join('');
  const profileByName=Object.fromEntries(c.profiles.map(x=>[x.name,x]));
  const scale=sgScale(h.players);
  document.querySelector('#players-grid').innerHTML=h.players.map(p=>profileCard(p,profileByName[p.name],scale)).join('');
  profileVisible=PROFILE_PAGE_SIZE;
  const input=document.querySelector('[data-profile-search]'); if(input)input.value='';
  applyProfiles();
  renderBoard(scope,document.querySelector('[data-board].active')?.dataset.board||'net');
}
function profileName(card){return (card.querySelector('h3')?.textContent||'').trim().toLowerCase()}
function applyProfiles(){
  const cards=[...document.querySelectorAll('[data-profile-card]')],input=document.querySelector('[data-profile-search]'),count=document.querySelector('[data-profile-count]'),footer=document.querySelector('[data-profile-footer]'),more=document.querySelector('[data-profile-more]');
  if(!input||!count||!footer||!more)return;
  const q=input.value.trim().toLowerCase(),total=cards.length; let shown=0,matches=0;
  cards.forEach((card,i)=>{const match=!q||profileName(card).includes(q);if(q&&match)matches++;const visible=q?match:i<profileVisible;card.hidden=!visible;if(visible)shown++});
  count.textContent=q?`${matches} matching player${matches===1?'':'s'} · AVG NET order`:`Showing ${shown} of ${total} players · AVG NET order`;
  const remaining=Math.max(0,total-profileVisible); footer.hidden=!!q||remaining===0||total<=PROFILE_PAGE_SIZE;
  if(!footer.hidden)more.textContent=`Show ${Math.min(PROFILE_PAGE_SIZE,remaining)} more · ${remaining} remaining`;
}
function updateSeasonBoard(){const board=document.querySelector('#ranks'),note=document.querySelector('[data-season-scroll-note]');if(!board||!note)return;const large=board.children.length>SEASON_BOARD_VISIBLE;board.classList.toggle('is-scrollable',large);note.hidden=!large}
function applyArchive(){const cards=[...document.querySelectorAll('[data-archive-grid] .event')],footer=document.querySelector('[data-archive-footer]'),more=document.querySelector('[data-archive-more]');if(!footer||!more)return;const total=cards.length,visible=Math.min(archiveVisible,total);cards.forEach((card,i)=>card.hidden=i>=visible);const remaining=Math.max(0,total-visible);footer.hidden=remaining===0||total<=ARCHIVE_INITIAL;if(!footer.hidden)more.textContent=`Show ${Math.min(ARCHIVE_PAGE_SIZE,remaining)} more tournaments · ${remaining} remaining`}
document.addEventListener('input',e=>{if(e.target.matches('[data-profile-search]'))applyProfiles()});
document.addEventListener('click',e=>{
  if(e.target.matches('[data-scope]'))renderScope(e.target.dataset.scope);
  if(e.target.matches('[data-board]'))renderBoard(document.querySelector('[data-scope].active').dataset.scope,e.target.dataset.board);
  if(e.target.closest('[data-profile-more]')){profileVisible+=PROFILE_PAGE_SIZE;applyProfiles()}
  if(e.target.closest('[data-archive-more]')){archiveVisible+=ARCHIVE_PAGE_SIZE;applyArchive()}
  const btn=e.target.closest('[data-profile-expand]');if(btn){const card=btn.closest('[data-profile-card]'),details=card.querySelector('.scouting-details'),open=btn.getAttribute('aria-expanded')==='true';btn.setAttribute('aria-expanded',String(!open));details.hidden=open;btn.innerHTML=!open?'Close scouting file <span>−</span>':'Read scouting file <span>+</span>'}
});
renderScope(HISTORY.defaultScope);applyArchive();
'''

RECAP_JS = r'''
(() => {
 const PLAYER_PAGE_SIZE=10,CARNAGE_INITIAL=10;let playerVisible=PLAYER_PAGE_SIZE,carnageExpanded=false;
 const carnageInput=document.querySelector('[data-carnage-search]'),playerInput=document.querySelector('[data-round-player-search]');
 function cname(card){return (card.querySelector('.player-name')?.textContent||'').trim().toLowerCase()}
 function pname(card){return (card.querySelector('h3')?.textContent||'').trim().toLowerCase()}
 function applyCarnage(){const cards=[...document.querySelectorAll('[data-carnage-card]')],q=(carnageInput?.value||'').trim().toLowerCase(),footer=document.querySelector('[data-carnage-footer]'),more=document.querySelector('[data-carnage-more]');cards.forEach((card,i)=>card.hidden=q?!cname(card).includes(q):(!carnageExpanded&&cards.length>CARNAGE_INITIAL&&i>=CARNAGE_INITIAL));if(footer){footer.hidden=!!q||cards.length<=CARNAGE_INITIAL;if(!footer.hidden)more.textContent=carnageExpanded?'Show only the 10 worst':`Show the rest of the crime scenes · ${cards.length-CARNAGE_INITIAL} more`}}
 function applyPlayers(){const cards=[...document.querySelectorAll('[data-player-card]')],q=(playerInput?.value||'').trim().toLowerCase(),footer=document.querySelector('[data-player-footer]'),more=document.querySelector('[data-player-more]');cards.forEach((card,i)=>card.hidden=q?!pname(card).includes(q):i>=playerVisible);const remaining=Math.max(0,cards.length-playerVisible);if(footer){footer.hidden=!!q||remaining===0||cards.length<=PLAYER_PAGE_SIZE;if(!footer.hidden)more.textContent=`Show ${Math.min(PLAYER_PAGE_SIZE,remaining)} more · ${remaining} remaining`}}
 function sync(source){const q=source.value;if(carnageInput&&carnageInput!==source)carnageInput.value=q;if(playerInput&&playerInput!==source)playerInput.value=q;applyCarnage();applyPlayers()}
 document.addEventListener('input',e=>{if(e.target.matches('[data-carnage-search],[data-round-player-search]'))sync(e.target)});
 document.addEventListener('click',e=>{if(e.target.closest('[data-carnage-more]')){carnageExpanded=!carnageExpanded;applyCarnage();return}if(e.target.closest('[data-player-more]')){playerVisible+=PLAYER_PAGE_SIZE;applyPlayers();return}const btn=e.target.closest('[data-round-expand]');if(btn){const d=btn.closest('[data-player-card]').querySelector('.round-details'),open=btn.getAttribute('aria-expanded')==='true';btn.setAttribute('aria-expanded',String(!open));d.hidden=open;btn.innerHTML=!open?'Close breakdown <span>−</span>':'Read full breakdown <span>+</span>'}});
 applyCarnage();applyPlayers();
})();
'''


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def e(value: object) -> str:
    return html.escape("" if value is None else str(value))


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def display_total(value: object) -> str:
    return e(value if value is not None else "—")


def site_settings(config: dict) -> dict:
    site = config.get("site") or {}
    title = site.get("title") or config.get("tourName") or "SGT League"
    brand = site.get("brand") or title
    footer = site.get("footer") or f"{title} · simulator golf with documentation."
    return {"title": title, "brand": brand, "footer": footer}


def brand_markup(config: dict) -> str:
    brand = e(site_settings(config)["brand"])
    return brand.replace(" / ", " <span>/</span> ")


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


def landing(history: dict, league_copy: dict, analyses: dict[int, dict], copies: dict[int, dict], config: dict) -> str:
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
    site = site_settings(config)
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(site['title'])}</title><style>{CSS}</style></head><body><nav class="nav"><div class="wrap navin"><a class="brand" href="#latest">{brand_markup(config)}</a><div class="links"><a href="#latest">Latest</a><a href="#league">League Snapshot</a><a href="#players">Scouting Files</a><a href="#events">Tournaments</a></div></div></nav><main><section class="section" id="latest"><div class="wrap"><div class="latest-intro"><div><div class="eyebrow">Latest tournament</div><h1>{e(latest.get('tourName'))}</h1></div><p class="sectionlead">{e(copy['latestTournamentTeaser'])}</p></div><a class="latest-card" href="recaps/{latest_id}.html"><div><div class="eyebrow">{e(latest.get('displayDate'))} · {e(latest.get('course'))}</div><h3>{e(copy['thirtySeconds'].split('.')[0])}.</h3><p>{e(copy['thirtySeconds'])}</p><span class="cta">Read full recap →</span></div><div class="latest-score"><div><small>🏆 Net champion</small><b>{net_champ}</b></div><div><small>Net challenger</small><b>{net_challenger}</b></div><div><small>Gross winner</small><b>{gross_winner}</b></div><div><small>Gross runner-up</small><b>{gross_runner}</b></div></div></a></div></section><section class="section" id="league"><div class="wrap"><div class="sectionhead"><div><div class="scope-label">Rolling league snapshot</div><h2>The golf right now.</h2></div><p class="sectionlead">Rolling windows follow the league's latest eligible events. Skips are neutral; team/special events can stay in the archive without contaminating individual player DNA.</p></div><div class="stories"><div class="storybox"><h3>What the numbers say</h3><p id="league-summary"></p><ul id="league-bullets"></ul></div><aside class="asidebox"><div class="board-head"><h3>Average finish</h3><div class="toggle"><button class="active" data-board="net">Net</button><button data-board="gross">Gross</button></div></div><div id="ranks"></div><div class="season-scroll-note" data-season-scroll-note hidden>Scroll for full average-finish table ↓</div></aside></div></div></section><section class="section" id="players"><div class="wrap"><div class="sectionhead"><div><div class="eyebrow">Scouting files</div><h2>Player profiles</h2></div><div class="scouting-meta"><div><div class="toggle">{scope_buttons}</div><div id="scope-status" class="sectionlead"></div></div><label class="player-search"><input type="search" data-profile-search placeholder="Search player…" autocomplete="off" aria-label="Search player"></label></div></div><div class="profile-directory"><div class="large-field-status" data-profile-count aria-live="polite"></div></div><div class="players" id="players-grid"></div><div class="large-list-footer" data-profile-footer hidden><button type="button" class="large-list-button" data-profile-more>Show 12 more</button></div></div></section><section class="section" id="events"><div class="wrap"><div class="sectionhead"><div><div class="eyebrow">Tournament archive</div><h2>Every completed event.</h2></div></div><div class="events" data-archive-grid>{''.join(archive)}<div class="large-list-footer" data-archive-footer hidden><button type="button" class="large-list-button" data-archive-more>Show older tournaments</button></div></div></div></section></main><footer class="footer"><div class="wrap">{e(site['footer'])}</div></footer><script>window.HISTORY={json.dumps(history, separators=(',',':'))};window.LEAGUE_COPY={json.dumps(league_copy, separators=(',',':'))};{JS}</script></body></html>'''


def recap(event: dict, analysis: dict, copy: dict, config: dict) -> str:
    net_champ, net_challenger, gross_winner, gross_runner = standings_cards(analysis)
    carnage = []
    carnage_copy = {x["name"]: x["commentary"] for x in copy.get("carnage", [])}
    for i, item in enumerate(analysis.get("carnage", [])):
        classes = "hole-card champ" if i == 0 else "hole-card"
        damage = int(item.get("grossToPar") or 0)
        carnage.append(f'''<article class="{classes}" data-carnage-card><div class="hole-top"><div><div class="eyebrow">{'🏆 Carnage Champion' if i==0 else 'Worst hole'}</div><span class="player-name">{e(item.get('name'))}</span><div>Hole {e(item.get('hole'))} · Par {e(item.get('par'))}</div></div><div class="hole-score">{e(item.get('gross'))} <small>({damage:+d})</small></div></div><p>{e(carnage_copy.get(item.get('name'),'') )}</p></article>''')
    by_copy = {x["name"]: x for x in copy.get("players", [])}
    players = []
    for p in analysis.get("players", []):
        if not p.get("completed"): continue
        c = by_copy.get(p.get("name"), {})
        lb = p.get("leaderboard", {})
        players.append(f'''<article class="recap-player" data-player-card><div class="eyebrow">Net {e(lb.get('netPosition'))} · Gross {e(lb.get('grossPosition'))}</div><h3>{e(p.get('name'))}</h3><div class="roast">{e(c.get('tagline'))}</div><div class="round-details" hidden><p>{e(c.get('body'))}</p></div><button type="button" class="expand-control" data-round-expand aria-expanded="false">Read full breakdown <span>+</span></button></article>''')
    site = site_settings(config)
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(event.get('tourName'))} recap — {e(site['title'])}</title><style>{CSS}</style></head><body><nav class="nav"><div class="wrap navin"><a class="brand" href="../index.html">{brand_markup(config)}</a><div class="links"><a href="../index.html">League home</a></div></div></nav><header class="recap-hero"><div class="wrap"><div class="eyebrow">Tournament recap · {e(event.get('displayDate'))}</div><h1>{e(event.get('tourName'))}</h1><p class="recap-dek">{e(copy.get('latestTournamentTeaser'))}</p><div class="winner-grid"><div class="winner-card primary"><small>🏆 Net champion</small><b>{net_champ}</b></div><div class="winner-card"><small>Net challenger</small><b>{net_challenger}</b></div><div class="winner-card"><small>Gross winner</small><b>{gross_winner}</b></div><div class="winner-card"><small>Gross runner-up</small><b>{gross_runner}</b></div></div></div></header><main><section class="section"><div class="wrap recap-grid"><div class="storybox"><div class="eyebrow">Tournament in 30 seconds</div><p class="big-copy">{e(copy.get('thirtySeconds'))}</p></div><aside class="asidebox"><h3>Tournament leaderboard</h3><div>{''.join(f'<div class="rank"><b>{r.get("position")} · {e(r.get("name"))}</b><span>{e(r.get("total"))}</span></div>' for r in analysis.get('leaderboard',{}).get('net',[]))}</div></aside></div></section><section class="section carnage-section" id="carnage"><div class="wrap"><div class="sectionhead recap-search-head"><div><div class="eyebrow">Everybody’s worst hole</div><h2>Carnage Board</h2></div><label class="recap-header-search"><input type="search" data-carnage-search placeholder="Search player…" autocomplete="off" aria-label="Search player"></label></div><div class="hole-grid" data-carnage-grid>{''.join(carnage)}</div><div class="large-list-footer" data-carnage-footer hidden><button type="button" class="large-list-button" data-carnage-more>Show the rest of the crime scenes</button></div></div></section><section class="section player-section" id="players"><div class="wrap"><div class="sectionhead recap-search-head"><div><div class="eyebrow">Net order · Gross context</div><h2>Player by player</h2></div><label class="recap-header-search"><input type="search" data-round-player-search placeholder="Search player…" autocomplete="off" aria-label="Search player"></label></div><div class="recap-players" data-player-grid>{''.join(players)}</div><div class="large-list-footer" data-player-footer hidden><button type="button" class="large-list-button" data-player-more>Show 10 more</button></div></div></section><section class="section state"><div class="wrap"><div class="eyebrow">State of the league</div><h2>What changed?</h2><p>{e(copy.get('stateOfLeague'))}</p></div></section></main><footer class="footer"><div class="wrap"><a class="cta" href="../index.html">← Back to league home</a></div></footer><script>{RECAP_JS}</script></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a configured SGT league site.")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("site"))
    args = parser.parse_args()

    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    data_root = args.data_root if args.data_root.is_absolute() else ROOT / args.data_root
    output = args.output if args.output.is_absolute() else ROOT / args.output

    config = load(config_path)
    history = load(data_root / "history.json")
    league_copy = load(data_root / "league-copy.json")
    analyses, copies = {}, {}
    for event in history["completedEvents"]:
        event_id = int(event["id"])
        ap = data_root / "analysis" / f"{event_id}.json"
        cp = data_root / "copy" / f"{event_id}.json"
        if ap.exists():
            analyses[event_id] = load(ap)
        if cp.exists():
            copies[event_id] = load(cp)

    output.mkdir(parents=True, exist_ok=True)
    (output / "recaps").mkdir(exist_ok=True)
    (output / "index.html").write_text(
        landing(history, league_copy, analyses, copies, config),
        encoding="utf-8",
    )
    for event in history["completedEvents"]:
        event_id = int(event["id"])
        if event_id in analyses and event_id in copies:
            (output / "recaps" / f"{event_id}.html").write_text(
                recap(event, analyses[event_id], copies[event_id], config),
                encoding="utf-8",
            )
    display = output.relative_to(ROOT) if output.is_relative_to(ROOT) else output
    print(f"Rendered {display} with {len(copies)} recap pages for {site_settings(config)['title']}")

if __name__ == "__main__":
    main()
