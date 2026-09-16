from pathlib import Path

path = Path('src/render_high_loft_large_field.py')
text = path.read_text()

needle = "def large_field_landing(html: str) -> str:\n    profile_marker = '<div class=\"players\" id=\"players-grid\"></div>'"
replacement = """def large_field_landing(html: str) -> str:
    profile_tagline = '<p class=\"sectionlead\">The numbers change. The tendencies linger. This is the closest thing we have to each player’s golfing DNA.</p>'
    profile_header_search = '<label class=\"player-search scouting-player-search\"><input type=\"search\" data-profile-search placeholder=\"Search player…\" autocomplete=\"off\" aria-label=\"Search player\"></label>'
    if profile_tagline not in html:
        raise RuntimeError(\"Could not find scouting profile tagline for header search\")
    html = html.replace(profile_tagline, profile_header_search, 1)

    profile_marker = '<div class=\"players\" id=\"players-grid\"></div>'"""
if needle not in text:
    raise SystemExit('Could not find large_field_landing opening')
text = text.replace(needle, replacement, 1)

old_tools = """    profile_tools = f'''\n<div class=\"large-field-tools profile-directory\" data-profile-tools hidden>\n  <label class=\"player-search\"><span>Find a player</span><input type=\"search\" data-profile-search placeholder=\"Type a player name…\" autocomplete=\"off\"></label>\n  <div class=\"large-field-status\" data-profile-count aria-live=\"polite\"></div>\n</div>\n{profile_marker}\n<div class=\"large-list-footer\" data-profile-footer hidden><button type=\"button\" class=\"large-list-button\" data-profile-more>Show {PROFILE_PAGE_SIZE} more</button></div>'''"""
new_tools = """    profile_tools = f'''\n<div class=\"large-field-tools profile-directory\" data-profile-tools hidden>\n  <div class=\"large-field-status\" data-profile-count aria-live=\"polite\"></div>\n</div>\n{profile_marker}\n<div class=\"large-list-footer\" data-profile-footer hidden><button type=\"button\" class=\"large-list-button\" data-profile-more>Show {PROFILE_PAGE_SIZE} more</button></div>'''"""
if old_tools not in text:
    raise SystemExit('Could not find profile directory tools markup')
text = text.replace(old_tools, new_tools, 1)

css_needle = ".player-search input::placeholder{{color:#6f7b72}}\n.large-field-status"
css_replacement = ".player-search input::placeholder{{color:#6f7b72}}\n.scouting-head .scouting-meta{{max-width:none;gap:28px}}\n.scouting-head .scouting-player-search{{flex:0 1 320px;min-width:260px}}\n.profile-directory{{justify-content:flex-end}}\n.large-field-status"
if css_needle not in text:
    raise SystemExit('Could not find profile search CSS insertion point')
text = text.replace(css_needle, css_replacement, 1)

path.write_text(text)
print('Moved scouting profile search into header and removed tagline/label')
