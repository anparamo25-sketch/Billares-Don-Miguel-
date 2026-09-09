from pathlib import Path

path = Path('scripts/repair_tv_1_2_4.py')
s = path.read_text()
old_start = "tv = r'''"
new_start = 'tv = r"""'
if old_start not in s:
    raise SystemExit('No se encontró el inicio de la plantilla tv')
s = s.replace(old_start, new_start, 1)
old_end = "\n'''\ns2 = re.sub(r\"  String get tvHtml \\\\{.*?\\n  \\\\}\", tv, s, count=1, flags=re.S)"
new_end = '\n"""\ns2 = re.sub(r"  String get tvHtml \\{.*?\\n  \\}", tv, s, count=1, flags=re.S)'
if old_end not in s:
    raise SystemExit('No se encontró el cierre de la plantilla tv')
s = s.replace(old_end, new_end, 1)
path.write_text(s)
print('OK: reparación de sintaxis del script TV aplicada')
