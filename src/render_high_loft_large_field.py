from __future__ import annotations

import re

import render_high_loft_safe as safe

renderer = safe.renderer
_original_landing = renderer.landing
_original_recap_page = renderer.recap_page

PROFILE_PAGE_SIZE = 12
PLAYER_PAGE_SIZE = 10
CARNAGE_INITIAL = 10
ARCHIVE_INITIAL = 6
ARCHIVE_PAGE_SIZE = 10
SEASON_BOARD_VISIBLE = 15


def large_field_landing(html: str) -> str:
    profile_marker = '<div class="players" id="players-grid"></div>'
    profile_tools = f'''
<div class="large-field-tools profile-directory" data-profile-tools hidden>
  <label class="player-search"><span>Find a player</span><input type="search" data-profile-search placeholder="Type a player name…" autocomplete="off"></label>
  <div class="large-field-status" data-profile-count aria-live="polite"></div>
</div>
{profile_marker}
<div class="large-list-footer" data-profile-footer hidden><button type="button" class="large-list-button" data-profile-more>Show {PROFILE_PAGE_SIZE} more</button></div>'''
    if profile_marker not in html:
        raise RuntimeError("Could not find scouting grid for large-field controls")
    html = html.replace(profile_marker, profile_tools, 1)

    season_marker = '<div class="season-ranks" id="rolling-ranks"></div>'
    season_replacement = season_marker + '<div class="season-scroll-note" data-season-scroll-note hidden>Scroll for full average-finish table ↓</div>'
    if season_marker not in html:
        raise RuntimeError("Could not find average-finish board for scalable scrolling")
    html = html.replace(season_marker, season_replacement, 1)

    archive_match = re.search(
        r'(<section class="section" id="events">.*?<div class="events">)(.*?)(</div></div></section>)',
        html,
        flags=re.S,
    )
    if not archive_match:
        raise RuntimeError("Could not find tournament archive for progressive reveal")
    archive_open = archive_match.group(1).replace('<div class="events">', '<div class="events" data-archive-grid>', 1)
    archive_close = '<div class="large-list-footer" data-archive-footer hidden><button type="button" class="large-list-button" data-archive-more>Show older tournaments</button></div>' + archive_match.group(3)
    html = html[:archive_match.start()] + archive_open + archive_match.group(2) + archive_close + html[archive_match.end():]

    css = f'''
<style>
.large-field-tools{{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:0 0 18px}}
.large-field-tools[hidden],.large-list-footer[hidden],.season-scroll-note[hidden]{{display:none!important}}
.player-search{{display:grid;gap:7px;min-width:min(100%,320px)}}
.player-search span{{color:#9ba79d;font-size:10px;font-weight:900;letter-spacing:.08em;text-transform:uppercase}}
.player-search input{{width:100%;border:1px solid #314137;border-radius:12px;background:#0f1711;color:#f2f4ef;padding:12px 14px;font:inherit;font-size:14px;outline:none}}
.player-search input:focus{{border-color:#6c8c46;box-shadow:0 0 0 2px rgba(182,243,74,.08)}}
.player-search input::placeholder{{color:#6f7b72}}
.large-field-status{{color:#9ba79d;font-size:10px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;text-align:right}}
.large-list-footer{{display:flex;justify-content:center;margin-top:16px}}
.large-list-button{{border:1px solid #3e503f;border-radius:999px;background:#0f1711;color:#b6f34a;padding:11px 16px;font:inherit;font-size:10px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;cursor:pointer}}
.large-list-button:hover{{border-color:#6c8c46}}
.season-ranks.is-scrollable{{max-height:560px;overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable;padding-right:4px}}
.season-scroll-note{{padding-top:10px;color:#7f8b82;font-size:9px;font-weight:850;letter-spacing:.06em;text-transform:uppercase;text-align:center}}
@media(max-width:700px){{.large-field-tools{{align-items:stretch;flex-direction:column}}.large-field-status{{text-align:left}}.player-search{{min-width:100%}}}}
</style>
'''
    html = html.replace('</head>', css + '</head>', 1)

    js = f'''
<script>
(() => {{
  const PROFILE_PAGE_SIZE={PROFILE_PAGE_SIZE};
  const ARCHIVE_INITIAL={ARCHIVE_INITIAL};
  const ARCHIVE_PAGE_SIZE={ARCHIVE_PAGE_SIZE};
  const SEASON_BOARD_VISIBLE={SEASON_BOARD_VISIBLE};
  let profileVisible=PROFILE_PAGE_SIZE;
  let archiveVisible=ARCHIVE_INITIAL;

  function profileName(card){{
    return (card.querySelector('h3')?.textContent||'').trim().toLowerCase();
  }}

  function applyProfileDirectory(){{
    const grid=document.querySelector('#players-grid');
    const tools=document.querySelector('[data-profile-tools]');
    const footer=document.querySelector('[data-profile-footer]');
    const input=document.querySelector('[data-profile-search]');
    const count=document.querySelector('[data-profile-count]');
    const more=document.querySelector('[data-profile-more]');
    if(!grid||!tools||!footer||!input||!count||!more)return;
    const cards=[...grid.querySelectorAll('.scouting-card')];
    const total=cards.length;
    const q=input.value.trim().toLowerCase();
    tools.hidden=total<=PROFILE_PAGE_SIZE;
    let shown=0;
    let matches=0;
    cards.forEach((card,i)=>{{
      const match=!q||profileName(card).includes(q);
      if(q&&match)matches++;
      const visible=q?match:(i<profileVisible);
      card.hidden=!visible;
      if(visible)shown++;
    }});
    if(q){{
      count.textContent=`${{matches}} matching player${{matches===1?'':'s'}} · AVG NET order`;
      footer.hidden=true;
    }}else{{
      count.textContent=`Showing ${{Math.min(shown,total)}} of ${{total}} players · AVG NET order`;
      const remaining=Math.max(0,total-profileVisible);
      footer.hidden=remaining===0||total<=PROFILE_PAGE_SIZE;
      if(remaining>0)more.textContent=`Show ${{Math.min(PROFILE_PAGE_SIZE,remaining)}} more · ${{remaining}} remaining`;
    }}
  }}

  function resetProfileDirectory(){{
    profileVisible=PROFILE_PAGE_SIZE;
    const input=document.querySelector('[data-profile-search]');
    if(input)input.value='';
    applyProfileDirectory();
  }}

  function updateSeasonBoard(){{
    const board=document.querySelector('#rolling-ranks');
    const note=document.querySelector('[data-season-scroll-note]');
    if(!board||!note)return;
    const large=board.children.length>SEASON_BOARD_VISIBLE;
    board.classList.toggle('is-scrollable',large);
    note.hidden=!large;
  }}

  function applyArchive(){{
    const grid=document.querySelector('[data-archive-grid]');
    const footer=document.querySelector('[data-archive-footer]');
    const button=document.querySelector('[data-archive-more]');
    if(!grid||!footer||!button)return;
    const cards=[...grid.querySelectorAll('.event')];
    const total=cards.length;
    const large=total>ARCHIVE_INITIAL;
    const visible=Math.min(archiveVisible,total);
    cards.forEach((card,i)=>card.hidden=large&&i>=visible);
    const remaining=Math.max(0,total-visible);
    footer.hidden=!large||remaining===0;
    if(remaining>0){{
      const step=Math.min(ARCHIVE_PAGE_SIZE,remaining);
      button.textContent='Show '+step+' more tournament'+(step===1?'':'s')+' · '+remaining+' remaining';
    }}
  }}

  document.addEventListener('input',e=>{{
    if(e.target.matches('[data-profile-search]'))applyProfileDirectory();
  }});
  document.addEventListener('click',e=>{{
    if(e.target.closest('[data-profile-more]')){{profileVisible+=PROFILE_PAGE_SIZE;applyProfileDirectory();return;}}
    if(e.target.closest('[data-archive-more]')){{archiveVisible+=ARCHIVE_PAGE_SIZE;applyArchive();return;}}
    if(e.target.matches('[data-profile-scope]'))setTimeout(()=>{{resetProfileDirectory();updateSeasonBoard();}},0);
    if(e.target.matches('[data-season-board]'))setTimeout(updateSeasonBoard,0);
  }});

  setTimeout(()=>{{applyProfileDirectory();updateSeasonBoard();applyArchive();}},0);
}})();
</script>
'''
    return html.replace('</body>', js + '</body>', 1)


def landing(history: dict, league_copy: dict, analyses: dict[int, dict], latest_copy: dict, cfg: dict, production_root):
    return large_field_landing(_original_landing(history, league_copy, analyses, latest_copy, cfg, production_root))


def large_field_recap(html: str) -> str:
    order_label = 'GROSS' if 'Gross order. Net context.' in html else 'NET'

    carnage_marker = '<div class="hole-grid">'
    carnage_tools = f'''
<div class="large-field-tools carnage-directory" data-carnage-tools hidden>
  <div class="large-field-status" data-carnage-count aria-live="polite"></div>
</div>
<div class="hole-grid" data-carnage-grid>'''
    if carnage_marker not in html:
        raise RuntimeError("Could not find Carnage grid for progressive reveal")
    html = html.replace(carnage_marker, carnage_tools, 1)
    carnage_section = re.search(r'(<section class="section carnage-section".*?</div></div></section>)', html, flags=re.S)
    if not carnage_section:
        raise RuntimeError("Could not find Carnage section footer")
    block = carnage_section.group(1)
    close = '</div></div></section>'
    block = block[:-len(close)] + '<div class="large-list-footer" data-carnage-footer hidden><button type="button" class="large-list-button" data-carnage-more>Show the rest of the crime scenes</button></div>' + close
    html = html[:carnage_section.start()] + block + html[carnage_section.end():]

    player_marker = '<div class="recap-players expanded">'
    player_tools = f'''
<div class="large-field-tools player-directory" data-round-player-tools hidden>
  <label class="player-search"><span>Find your name</span><input type="search" data-round-player-search placeholder="Type a player name…" autocomplete="off"></label>
  <div class="large-field-status" data-round-player-count aria-live="polite"></div>
</div>
<div class="recap-players expanded" data-round-player-grid>'''
    if player_marker not in html:
        raise RuntimeError("Could not find player-by-player grid for search controls")
    html = html.replace(player_marker, player_tools, 1)
    player_section = re.search(r'(<section class="section player-section".*?</div></div></section>)', html, flags=re.S)
    if not player_section:
        raise RuntimeError("Could not find player-by-player section footer")
    block = player_section.group(1)
    close = '</div></div></section>'
    block = block[:-len(close)] + f'<div class="large-list-footer" data-round-player-footer hidden><button type="button" class="large-list-button" data-round-player-more>Show {PLAYER_PAGE_SIZE} more</button></div>' + close
    html = html[:player_section.start()] + block + html[player_section.end():]

    css = '''
<style>
.large-field-tools{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:0 0 16px}
.large-field-tools[hidden],.large-list-footer[hidden]{display:none!important}
.player-search{display:grid;gap:7px;min-width:min(100%,320px)}
.player-search span{color:#9ba79d;font-size:10px;font-weight:900;letter-spacing:.08em;text-transform:uppercase}
.player-search input{width:100%;border:1px solid #314137;border-radius:12px;background:#0f1711;color:#f2f4ef;padding:12px 14px;font:inherit;font-size:14px;outline:none}
.player-search input:focus{border-color:#6c8c46;box-shadow:0 0 0 2px rgba(182,243,74,.08)}
.player-search input::placeholder{color:#6f7b72}
.large-field-status{color:#9ba79d;font-size:10px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;text-align:right}
.carnage-directory{justify-content:flex-end;margin-top:-8px}
.large-list-footer{display:flex;justify-content:center;margin-top:16px}
.large-list-button{border:1px solid #3e503f;border-radius:999px;background:#0f1711;color:#b6f34a;padding:11px 16px;font:inherit;font-size:10px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;cursor:pointer}
.large-list-button:hover{border-color:#6c8c46}
[data-carnage-card][hidden],[data-player-card][hidden]{display:none!important}
@media(max-width:700px){.large-field-tools{align-items:stretch;flex-direction:column}.large-field-status{text-align:left}.player-search{min-width:100%}.carnage-directory{margin-top:0}}
</style>
'''
    html = html.replace('</head>', css + '</head>', 1)

    js = f'''
<script>
(() => {{
  const CARNAGE_INITIAL={CARNAGE_INITIAL};
  const PLAYER_PAGE_SIZE={PLAYER_PAGE_SIZE};
  const ORDER_LABEL='{order_label}';
  let carnageExpanded=false;
  let playerVisible=PLAYER_PAGE_SIZE;

  function applyCarnage(){{
    const grid=document.querySelector('[data-carnage-grid]');
    const tools=document.querySelector('[data-carnage-tools]');
    const footer=document.querySelector('[data-carnage-footer]');
    const count=document.querySelector('[data-carnage-count]');
    const button=document.querySelector('[data-carnage-more]');
    if(!grid||!tools||!footer||!count||!button)return;
    const cards=[...grid.querySelectorAll('[data-carnage-card]')];
    const total=cards.length;
    const large=total>CARNAGE_INITIAL;
    tools.hidden=!large;
    footer.hidden=!large;
    cards.forEach((card,i)=>card.hidden=large&&!carnageExpanded&&i>=CARNAGE_INITIAL);
    if(large){{
      const shown=carnageExpanded?total:CARNAGE_INITIAL;
      count.textContent=`Showing ${{shown}} worst of ${{total}}`;
      button.textContent=carnageExpanded?'Show only the 10 worst':`Show the rest of the crime scenes · ${{total-CARNAGE_INITIAL}} more`;
    }}
  }}

  function roundPlayerName(card){{
    const h3=card.querySelector('h3');
    return (h3?.firstChild?.textContent||h3?.textContent||'').trim().toLowerCase();
  }}

  function applyPlayers(){{
    const grid=document.querySelector('[data-round-player-grid]');
    const tools=document.querySelector('[data-round-player-tools]');
    const footer=document.querySelector('[data-round-player-footer]');
    const input=document.querySelector('[data-round-player-search]');
    const count=document.querySelector('[data-round-player-count]');
    const more=document.querySelector('[data-round-player-more]');
    if(!grid||!tools||!footer||!input||!count||!more)return;
    const cards=[...grid.querySelectorAll('[data-player-card]')];
    const total=cards.length;
    const q=input.value.trim().toLowerCase();
    const large=total>PLAYER_PAGE_SIZE;
    tools.hidden=!large;
    let shown=0;
    let matches=0;
    cards.forEach((card,i)=>{{
      const match=!q||roundPlayerName(card).includes(q);
      if(q&&match)matches++;
      const visible=q?match:(i<playerVisible);
      card.hidden=!visible;
      if(visible)shown++;
    }});
    if(q){{
      count.textContent=`${{matches}} matching player${{matches===1?'':'s'}} · ${{ORDER_LABEL}} order`;
      footer.hidden=true;
    }}else{{
      count.textContent=`Showing ${{Math.min(shown,total)}} of ${{total}} players · ${{ORDER_LABEL}} order`;
      const remaining=Math.max(0,total-playerVisible);
      footer.hidden=!large||remaining===0;
      if(remaining>0)more.textContent=`Show ${{Math.min(PLAYER_PAGE_SIZE,remaining)}} more · ${{remaining}} remaining`;
    }}
  }}

  document.addEventListener('input',e=>{{if(e.target.matches('[data-round-player-search]'))applyPlayers();}});
  document.addEventListener('click',e=>{{
    if(e.target.closest('[data-carnage-more]')){{carnageExpanded=!carnageExpanded;applyCarnage();return;}}
    if(e.target.closest('[data-round-player-more]')){{playerVisible+=PLAYER_PAGE_SIZE;applyPlayers();return;}}
  }});

  applyCarnage();
  applyPlayers();
}})();
</script>
'''
    return html.replace('</body>', js + '</body>', 1)


def recap_page(event: dict, analysis: dict, copy: dict, cfg: dict, excluded: bool) -> str:
    return large_field_recap(_original_recap_page(event, analysis, copy, cfg, excluded))


renderer.landing = landing
renderer.recap_page = recap_page


if __name__ == '__main__':
    renderer.main()
