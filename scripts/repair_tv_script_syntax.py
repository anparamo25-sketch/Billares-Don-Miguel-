from pathlib import Path

path = Path('scripts/repair_tv_1_2_4.py')
s = path.read_text()
old_start = "tv = r'''"
new_start = 'tv = r"""'
start = s.find(old_start)
if start < 0:
    raise SystemExit('No se encontró el inicio de la plantilla tv')
end = s.rfind("\n'''")
if end <= start:
    raise SystemExit('No se encontró el cierre de la plantilla tv')
s = s[:start] + new_start + s[start + len(old_start):end] + '\n"""' + s[end + len("\n'''"):]
path.write_text(s)
print('OK: reparación de sintaxis del script TV aplicada')
