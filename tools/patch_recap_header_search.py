from pathlib import Path
import re

path = Path('src/render_high_loft_large_field.py')
text = path.read_text()

new_function = r'''def large_field_recap(html: str) -> str:
    order_label = 'GROSS' if 'Gross order. Net context.' in html else 'NET'

    def add_header_search(section_class: str, data_attr: str) -> None:
        nonlocal html
        pattern = re.compile(
            rf'(<section class="section {section_class}"[^>]*><div class="wrap"><div class="sectionhead marked">)(.*?)(<p class="sectionlead">.*?</p>)(</div>)',
            flags=re.S,
        )
        match = pattern.search(html)
        if not match:
            raise RuntimeError(f"Could not find {section_class} header for inline search")
        opener = match.group(1).replace('sectionhead marked', 'sectionhead marked recap-search-head', 1)
        search = (
            f'<label class="recap-header-search">'
            f'<span>Search player</span>'
            f'<input type="search" {data_attr} placeholder="Search player…" autocomplete="off" aria-label="Search player">'
            f'</label>'
        )
        replacement = opener + match.group(2) + search + match.group(4)
        html = html[:match.start()] + replacement + html[match.end():]

    add_header_search('carnage-section', 'data-carnage-search')
    add_header_search('player-section', 'data-round-player-search')

    carnage_marker = '<div class="hole-grid">'
    if carnage_marker not in html:
        raise RuntimeError("Could not find Carnage grid for progressive reveal")
    html = html.replace(carnage_marker, '<div class="hole-grid" data-carnage-grid>', 1)
    carnage_section = re.search(r'(<section class="section carnage-section".*?</div></div></section>)', html, flags=re.S)
    if not carnage_section:
        raise RuntimeError("Could not find Carnage section footer")
    block = carnage_section.group(1)
    close = '</div></div></section>'
    block = block[:-len(close)] + '<div class="large-list-footer" data-carnage-footer hidden><button type="button" class="large-list-button" data-carnage-more>Show the rest of the crime scenes</button></div>' + close
    html = html[:carnage_section.start()] + block + html[carnage_section.end():]

    player_marker = '<div class="recap-players expanded">'
    if player_marker not in html:
        raise RuntimeError("Could not find player-by-player grid for search controls")
    html = html.replace(player_marker, '<div class="recap-players expanded" data-round-player-grid>', 1)
    player_section = re.search(r'(<section class="section player-section".*?</div></div></section>)', html, flags=re.S)
    if not player_section:
        raise RuntimeError("Could not find player-by-player section footer")
    block = player_section.group(1)
    close = '</div></div></section>'
    block = block[:-len(close)] + f'<div class="large-list-footer" data-round-player-footer hidden><button type="button" class="large-list-button" data-round-player-more>Show {PLAYER_PAGE_SIZE} more</button></div>' + close
    html = html[:player_section.start()] + block + html[player_section.end():]

    css = '''
<style>
.recap-search-head{align-items:flex-end;gap:20px}
.recap-search-head .section-title{min-width:0}
.recap-header-search{display:grid;gap:7px;flex:0 1 320px;width:min(320px,100%);margin-left:auto}
.recap-header-search span{color:#9ba79d;font-size:10px;font-weight:900;letter-spacing:.08em;text-transform:uppercase}
.recap-header-search input{width:100%;border:1px solid #314137;border-radius:12px;background:#0f1711;color:#f2f4ef;padding:12px 14px;font:inherit;font-size:14px;outline:none}
.recap-header-search input:focus{border-color:#6c8c46;box-shadow:0 0 0 2px rgba(182,243,74,.08)}
.recap-header-search input::placeholder{color:#6f7b72}
.large-list-footer[hidden]{display:none!important}
.large-list-footer{display:flex;justify-content:center;margin-top:16px}
.large-list-button{border:1px solid #3e503f;border-radius:999px;background:#0f1711;color:#b6f34a;padding:11px 16px;font:inherit;font-size:10px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;cursor:pointer}
.large-list-button:hover{border-color:#6c8c46}
[data-carnage-card][hidden],[data-player-card][hidden]{display:none!important}
@media(max-width:700px){.recap-search-head{align-items:stretch;flex-direction:column}.recap-header-search{width:100%;max-width:none;flex-basis:auto;margin-left:0}}
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

  function carnagePlayerName(card){{
    return (card.querySelector('.player-name')?.textContent||'').trim().toLowerCase();
  }}

  function applyCarnage(){{
    const grid=document.querySelector('[data-carnage-grid]');
    const footer=document.querySelector('[data-carnage-footer]');
    const input=document.querySelector('[data-carnage-search]');
    const button=document.querySelector('[data-carnage-more]');
    if(!grid||!footer||!input||!button)return;
    const cards=[...grid.querySelectorAll('[data-carnage-card]')];
    const total=cards.length;
    const q=input.value.trim().toLowerCase();
    const large=total>CARNAGE_INITIAL;
    cards.forEach((card,i)=>{{
      const match=!q||carnagePlayerName(card).includes(q);
      const visible=q?match:(!large||carnageExpanded||i<CARNAGE_INITIAL);
      card.hidden=!visible;
    }});
    if(q){{
      footer.hidden=true;
    }}else{{
      footer.hidden=!large;
      if(large)button.textContent=carnageExpanded?'Show only the 10 worst':`Show the rest of the crime scenes · ${{total-CARNAGE_INITIAL}} more`;
    }}
  }}

  function roundPlayerName(card){{
    const h3=card.querySelector('h3');
    return (h3?.firstChild?.textContent||h3?.textContent||'').trim().toLowerCase();
  }}

  function applyPlayers(){{
    const grid=document.querySelector('[data-round-player-grid]');
    const footer=document.querySelector('[data-round-player-footer]');
    const input=document.querySelector('[data-round-player-search]');
    const more=document.querySelector('[data-round-player-more]');
    if(!grid||!footer||!input||!more)return;
    const cards=[...grid.querySelectorAll('[data-player-card]')];
    const total=cards.length;
    const q=input.value.trim().toLowerCase();
    const large=total>PLAYER_PAGE_SIZE;
    cards.forEach((card,i)=>{{
      const match=!q||roundPlayerName(card).includes(q);
      const visible=q?match:(i<playerVisible);
      card.hidden=!visible;
    }});
    if(q){{
      footer.hidden=true;
    }}else{{
      const remaining=Math.max(0,total-playerVisible);
      footer.hidden=!large||remaining===0;
      if(remaining>0)more.textContent=`Show ${{Math.min(PLAYER_PAGE_SIZE,remaining)}} more · ${{remaining}} remaining`;
    }}
  }}

  document.addEventListener('input',e=>{{
    if(e.target.matches('[data-carnage-search]'))applyCarnage();
    if(e.target.matches('[data-round-player-search]'))applyPlayers();
  }});
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


'''

pattern = re.compile(r'def large_field_recap\(html: str\) -> str:.*?(?=def recap_page\()', flags=re.S)
text, count = pattern.subn(new_function, text, count=1)
if count != 1:
    raise SystemExit('Could not replace large_field_recap')
path.write_text(text)
print('Patched recap header search UI')
