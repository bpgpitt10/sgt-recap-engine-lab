from pathlib import Path

path = Path('src/render_high_loft_large_field.py')
text = path.read_text()

old = """        search = (\n            f'<label class=\"recap-header-search\">'\n            f'<span>Search player</span>'\n            f'<input type=\"search\" {data_attr} placeholder=\"Search player…\" autocomplete=\"off\" aria-label=\"Search player\">'\n            f'</label>'\n        )"""
new = """        search = (\n            f'<label class=\"recap-header-search\">'\n            f'<input type=\"search\" {data_attr} placeholder=\"Search player…\" autocomplete=\"off\" aria-label=\"Search player\">'\n            f'</label>'\n        )"""
if old not in text:
    raise SystemExit('Could not find recap header search markup')
text = text.replace(old, new, 1)

old_listener = """  document.addEventListener('input',e=>{{\n    if(e.target.matches('[data-carnage-search]'))applyCarnage();\n    if(e.target.matches('[data-round-player-search]'))applyPlayers();\n  }});"""
new_listener = """  function syncTournamentSearch(source){{\n    const carnage=document.querySelector('[data-carnage-search]');\n    const players=document.querySelector('[data-round-player-search]');\n    const q=source.value;\n    if(carnage&&carnage!==source)carnage.value=q;\n    if(players&&players!==source)players.value=q;\n    applyCarnage();\n    applyPlayers();\n  }}\n\n  document.addEventListener('input',e=>{{\n    if(e.target.matches('[data-carnage-search],[data-round-player-search]'))syncTournamentSearch(e.target);\n  }});"""
if old_listener not in text:
    raise SystemExit('Could not find tournament search listeners')
text = text.replace(old_listener, new_listener, 1)

path.write_text(text)
print('Linked Carnage and Player-by-Player search; removed redundant search label')
