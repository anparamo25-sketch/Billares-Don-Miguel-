from pathlib import Path
import re
import subprocess
import py_compile

TARGET = Path('lib/main.dart')
STABLE = '5e5ec88e7f6c12f5c1dae006ad95da4b903f950d'
SCRIPTS = ('scripts/prepare_1_2_4.py','scripts/repair_1_2_4_generated.py','scripts/repair_tv_1_2_4.py','scripts/repair_tv_hostname_1_2_5.py','scripts/ensure_mdns_1_2_5.py','scripts/repair_tv_final_safety.py')
for script in SCRIPTS:
    py_compile.compile(script, doraise=True)

def class_span(source, name):
    m = re.search(rf'\bclass\s+{re.escape(name)}\b[^{{]*\{{', source)
    if not m: raise SystemExit(f'REPAIR PREFLIGHT FAILED: clase {name} ausente')
    start = m.start(); i = source.find('{', m.start(), m.end()); depth = 0; quote = None; triple = False
    while i < len(source):
        if quote:
            token = quote * 3 if triple else quote
            if source.startswith(token, i): i += len(token); quote = None; triple = False; continue
            if source[i] == '\\' and not triple: i += 2
            else: i += 1
            continue
        if source.startswith("'''", i): quote, triple = "'", True; i += 3; continue
        if source.startswith('"""', i): quote, triple = '"', True; i += 3; continue
        if source[i] in "'\"": quote, triple = source[i], False; i += 1; continue
        if source.startswith('//', i):
            e = source.find('\n', i + 2); i = len(source) if e < 0 else e + 1; continue
        if source.startswith('/*', i):
            e = source.find('*/', i + 2); i = len(source) if e < 0 else e + 2; continue
        if source[i] == '{': depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0: return start, i + 1
        i += 1
    raise SystemExit(f'REPAIR PREFLIGHT FAILED: llaves sin cerrar en {name}')

def extract_class(source, name):
    a, b = class_span(source, name); return source[a:b]

def replace_class(source, name, replacement):
    a, b = class_span(source, name); return source[:a] + replacement + source[b:]

current = TARGET.read_text()
baseline = subprocess.check_output(['git', 'show', f'{STABLE}:lib/main.dart'], text=True)
current = replace_class(current, '_LoginPageState', extract_class(baseline, '_LoginPageState'))
current = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.5+125';", current, count=1)
current = re.sub(r"const String updateManifestUrl = '[^']+';", "const String updateManifestUrl = 'https://github.com/anparamo25-sketch/Billares-Don-Miguel-/raw/refs/heads/main/update.json';", current, count=1)
seen_imports = set(); clean_lines = []
for line in current.splitlines():
    if line.startswith('import '):
        if line in seen_imports: continue
        seen_imports.add(line)
    clean_lines.append(line)
current = '\n'.join(clean_lines) + '\n'
login = extract_class(current, '_LoginPageState')
for forbidden in ('checkingUpdate', 'showSettings', 'logout', 'dashboard()', 'historyPage()'):
    if forbidden in login: raise SystemExit(f'REPAIR PREFLIGHT FAILED: {forbidden} dentro de _LoginPageState')
if not re.search(r'\bMap<String,\s*dynamic>\s+stateMap\s*\(\)', current): raise SystemExit('REPAIR PREFLIGHT FAILED: stateMap ausente')
TARGET.write_text(current)
subprocess.check_call(['python3', 'scripts/repair_tv_1_2_4.py'])
subprocess.check_call(['python3', 'scripts/repair_tv_hostname_1_2_5.py'])
subprocess.check_call(['python3', 'scripts/ensure_mdns_1_2_5.py'])
current = TARGET.read_text()
current = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.5+125';", current, count=1)

# Validate the producer's actual declaration line. This deliberately does not
# mask strings/comments and does not require a specific indentation style.
show_lines = []
for line_no, line in enumerate(current.splitlines(), 1):
    n = re.sub(r'\s+', ' ', line.strip())
    if re.match(r'^Future\s*<\s*void\s*>\s+showTvConnection\s*\(\s*\)\s+async\s*(?:\{)?\s*$', n):
        show_lines.append(line_no)
if len(show_lines) != 1:
    raise SystemExit(f'REPAIR TV FAILED: declaración estructural de showTvConnection detectada {len(show_lines)} veces')
lines = current.splitlines()
body_window = '\n'.join(lines[show_lines[0] - 1:show_lines[0] + 100])
if 'showDialog<void>' not in body_window:
    raise SystemExit('REPAIR TV FAILED: cuerpo de showTvConnection inválido')

tv_getters = []
for line_no, line in enumerate(lines, 1):
    n = re.sub(r'\s+', ' ', line.strip())
    if re.match(r'^String\s+get\s+tvHtml\s*=>', n):
        tv_getters.append((line_no, line))
if len(tv_getters) != 1:
    raise SystemExit(f'REPAIR TV FAILED: tvHtml quedó {len(tv_getters)} veces')
tv_line = tv_getters[0][1]
if not tv_line.rstrip().endswith(';'):
    raise SystemExit('REPAIR TV FAILED: getter tvHtml inválido')

normalized = re.sub(r'\s+', ' ', current)
required = {
    'String get tvHtml =>':'tvHtml ausente',
    'Billares Don Miguel - TV':'título TV ausente',
    "fetch('/api/state?ts='+Date.now()":'actualización TV ausente',
    'RawDatagramSocket? _billaresMdnsSocket;':'mDNS ausente',
    'Future<void> _startBillaresMdns() async':'método mDNS ausente',
    'await _startBillaresMdns();':'arranque mDNS ausente',
    "function money(n){return 'C&#36; ":'formato monetario ausente'
}
for marker, message in required.items():
    if marker not in normalized:
        raise SystemExit(f'REPAIR TV FAILED: {message}')
binds = re.findall(r'HttpServer\.bind\s*\(\s*InternetAddress\.anyIPv4\s*,\s*([^,\)]+)', normalized)
if not any(argument.strip() == '80' for argument in binds):
    raise SystemExit(f'REPAIR TV FAILED: puerto 80 no reconocido: {binds}')
if 'billaresdonmiguel.local' not in normalized:
    raise SystemExit('REPAIR TV FAILED: hostname TV ausente')
if 'return r"""' in current or "return r'''" in current or 'String get tvHtml {' in current:
    raise SystemExit('REPAIR TV FAILED: TV heredada detectada')
# Remove exactly the getter line for this syntax-only check so JavaScript tokens
# inside the JSON-escaped HTML cannot affect the Dart source validation.
outside_tv = current.replace(tv_line, '', 1)
if '===' in outside_tv:
    raise SystemExit('REPAIR TV FAILED: JavaScript fuera del getter TV')
TARGET.write_text(current)
print('OK: fuente 1.2.5; reconstrucción TV y mDNS reconocidas sin falso negativo')
