from pathlib import Path
import re
import subprocess

TARGET = Path('lib/main.dart')
STABLE_COMMIT = '5e5ec88e7f6c12f5c1dae006ad95da4b903f950d'

def class_span(source: str, class_name: str):
    match = re.search(rf'\bclass\s+{re.escape(class_name)}\b[^{{]*\{{', source)
    if not match: raise SystemExit(f'No se encontró la clase {class_name}')
    start = match.start(); brace = source.find('{', match.start()); depth = 0; in_string = False; quote = ''; escaped = False
    for i in range(brace, len(source)):
        ch = source[i]
        if in_string:
            if escaped: escaped = False
            elif ch == '\\': escaped = True
            elif ch == quote: in_string = False
            continue
        if ch in ("'", '"'): in_string = True; quote = ch; continue
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0: return start, i + 1
    raise SystemExit(f'Llaves sin cerrar en {class_name}')

def extract_class(source: str, class_name: str) -> str:
    a, b = class_span(source, class_name); return source[a:b]

def replace_class(source: str, class_name: str, replacement: str) -> str:
    a, b = class_span(source, class_name); return source[:a] + replacement + source[b:]

current = TARGET.read_text()
try:
    baseline = subprocess.check_output(['git', 'show', f'{STABLE_COMMIT}:lib/main.dart'], text=True)
except subprocess.CalledProcessError as exc:
    raise SystemExit(f'No se pudo recuperar el main.dart estable {STABLE_COMMIT}: {exc}')

current = replace_class(current, '_LoginPageState', extract_class(baseline, '_LoginPageState'))
current = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.5+125';", current, count=1)
current = re.sub(r"const String updateManifestUrl = '[^']+';", "const String updateManifestUrl = 'https://github.com/anparamo25-sketch/Billares-Don-Miguel-/raw/refs/heads/main/update.json';", current, count=1)

lines = current.splitlines(); out = []; seen = set()
for line in lines:
    if line.startswith('import '):
        if line in seen: continue
        seen.add(line)
    out.append(line)
current = '\n'.join(out) + '\n'

login = extract_class(current, '_LoginPageState')
for bad in ('checkingUpdate', 'showSettings', 'logout', 'dashboard()', 'historyPage()'):
    if bad in login: raise SystemExit(f'REPAIR PREFLIGHT FAILED: {bad} quedó dentro de _LoginPageState')
if "appVersion = '1.2.5+125'" not in current: raise SystemExit('REPAIR PREFLIGHT FAILED: versión 1.2.5+125 ausente')
if 'class _DashboardPageState' not in current: raise SystemExit('REPAIR PREFLIGHT FAILED: DashboardPage ausente')
if 'Pantalla exclusiva para TV' not in current: raise SystemExit('REPAIR PREFLIGHT FAILED: receptor TV ausente')

TARGET.write_text(current)
subprocess.check_call(['python3', 'scripts/repair_tv_1_2_4.py'])
current = TARGET.read_text()
current = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.5+125';", current, count=1)
current = current.replace('tv_web_receiver_disabled', 'tv_cast').replace('ACTION_CAST_SETTINGS_DISABLED', 'ACTION_CAST_SETTINGS')
TARGET.write_text(current)
print('OK: 1.2.5 source repaired with dedicated TV web receiver')
