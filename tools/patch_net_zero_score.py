from pathlib import Path

path = Path('src/analyze_tournament.py')
text = path.read_text()

old = '''        gross_values = None\n        net_values = None\n        for row in score_rows:'''
new = '''        gross_values = None\n        net_values = None\n        net_text_values = None\n        for row in score_rows:'''
if old not in text:
    raise SystemExit('score row declarations not found')
text = text.replace(old, new, 1)

old = '''            elif label == "NET":\n                net_values = values'''
new = '''            elif label == "NET":\n                net_values = values\n                net_text_values = [text(cell) for cell in cells][1:]'''
if old not in text:
    raise SystemExit('NET row parser not found')
text = text.replace(old, new, 1)

old = '''            net = net_values[idx] if net_values and idx < len(net_values) else None\n            item = {'''
new = '''            net = net_values[idx] if net_values and idx < len(net_values) else None\n            net_text = net_text_values[idx] if net_text_values and idx < len(net_text_values) else None\n            # SGT renders a legitimate net score of zero as "-". Only interpret\n            # that dash as zero when the gross hole was actually played; an\n            # unplayed hole has gross=None and must remain missing.\n            if gross is not None and net is None and net_text == "-":\n                net = 0\n            item = {'''
if old not in text:
    raise SystemExit('hole net assignment not found')
text = text.replace(old, new, 1)

old = '''    net_total = sum(round_["net"] for round_ in complete_rounds if round_["net"] is not None) if complete_rounds else None'''
new = '''    net_rounds = [round_ for round_ in complete_rounds if round_["net"] is not None]\n    net_total = sum(round_["net"] for round_ in net_rounds) if complete_rounds and len(net_rounds) == len(complete_rounds) else None'''
if old not in text:
    raise SystemExit('top-level net total not found')
text = text.replace(old, new, 1)

path.write_text(text)
print('Patched SGT NET dash-as-zero handling')
