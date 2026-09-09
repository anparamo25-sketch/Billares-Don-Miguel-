from pathlib import Path
import re
import subprocess
import py_compile

TARGET = Path('lib/main.dart')
STABLE = '5e5ec88e7f6c12f5c1dae006ad95da4b903f950d'

# Orquestador único: prepara la versión y llama UNA SOLA VEZ al productor
# canónico de TV/LAN/mDNS. Este archivo nunca reconstruye TV ni mDNS.
SCRIPT_ORDER = (
    'scripts/prepare_1_2_4.py',
    'scripts/repair_tv_1_2_4.py',
    'scripts/repair_tv_hostname_1_2_5.py',
    'scripts/ensure_mdns_1_2_5.py',
    'scripts/repair_tv_final_safety.py',
)
for script in SCRIPT_ORDER:
    py_compile.compile(script, doraise=True)


def class_span(source: str, name: str):
    m = re.search(rf'\bclass\s+{re.escape(name)}\b[^{{]*\{{', source)
    if not m:
        raise SystemExit(f'REPAIR PREFLIGHT FAILED: clase {name} ausente')
    start = m.start()
    depth = 0
    quote = None
    triple = False
    i = source.find('{', m.start(), m.end())
    while i < len(source):
        if quote:
            token = quote * 3 if triple else quote
            if source.startswith(token, i):
                i += len(token)
                quote = None
                triple = False
                continue
            if source[i] == '\\' and not triple:
                i += 2
            else:
                i += 1
            continue
        if source.startswith("'''", i):
            quote, triple = "'", True
            i += 3
            continue
        if source.startswith('"""', i):
            quote, triple = '"', True
            i += 3
            continue
        if source[i] in "'\"":
            quote, triple = source[i], False
            i += 1
            continue
        if source.startswith('//', i):
            e = source.find('\n', i + 2)
            i = len(source) if e < 0 else e + 1
            continue
        if source.startswith('/*', i):
            e = source.find('*/', i + 2)
            i = len(source) if e < 0 else e + 2
            continue
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    raise SystemExit(f'REPAIR PREFLIGHT FAILED: llaves sin cerrar en {name}')


def extract_class(source: str, name: str) -> str:
    a, b = class_span(source, name)
    return source[a:b]


def replace_class(source: str, name: str, replacement: str) -> str:
    a, b = class_span(source, name)
    return source[:a] + replacement + source[b:]


current = TARGET.read_text()
baseline = subprocess.check_output(['git', 'show', f'{STABLE}:lib/main.dart'], text=True)
current = replace_class(current, '_LoginPageState', extract_class(baseline, '_LoginPageState'))
current = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.5+125';", current, count=1)
current = re.sub(
    r"const String updateManifestUrl = '[^']+';",
    "const String updateManifestUrl = 'https://github.com/anparamo25-sketch/Billares-Don-Miguel-/raw/refs/heads/main/update.json';",
    current,
    count=1,
)

# Elimina únicamente imports repetidos; no toca lógica Dart.
seen = set()
clean = []
for line in current.splitlines():
    if line.startswith('import '):
        if line in seen:
            continue
        seen.add(line)
    clean.append(line)
current = '\n'.join(clean) + '\n'

login = extract_class(current, '_LoginPageState')
for forbidden in ('checkingUpdate', 'showSettings', 'logout', 'dashboard()', 'historyPage()'):
    if forbidden in login:
        raise SystemExit(f'REPAIR PREFLIGHT FAILED: {forbidden} dentro de _LoginPageState')

if not re.search(r'\bMap\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap\s*\(\s*\)', current):
    raise SystemExit('REPAIR PREFLIGHT FAILED: stateMap ausente en la base generada')

TARGET.write_text(current)

# El productor canónico es el único que modifica la estructura TV/LAN/mDNS.
subprocess.check_call(['python3', 'scripts/repair_tv_1_2_4.py'])
subprocess.check_call(['python3', 'scripts/repair_tv_hostname_1_2_5.py'])
subprocess.check_call(['python3', 'scripts/ensure_mdns_1_2_5.py'])
subprocess.check_call(['python3', 'scripts/repair_tv_final_safety.py'])

source = TARGET.read_text()
normalized = re.sub(r'\s+', ' ', source)

# Validación semántica final. No depende de indentación, mensajes del propio
# validador ni fragmentos internos de JavaScript.
checks = (
    (len(re.findall(r'\bFuture\s*<\s*void\s*>\s+startLanServer\s*\(\s*\)\s+async\s*\{', source)) == 1, 'servidor LAN'),
    (len(re.findall(r'\bFuture\s*<\s*void\s*>\s+showTvConnection\s*\(\s*\)\s+async\s*\{', source)) == 1, 'conexión TV'),
    (len(re.findall(r'(?m)^\s*String\s+get\s+tvHtml\s*=>', source)) == 1, 'receptor TV'),
    ('HttpServer.bind(InternetAddress.anyIPv4, 80' in normalized, 'puerto LAN 80'),
    ('http://billaresdonmiguel.local/tv' in source, 'hostname TV'),
    ('/api/state?ts=' in source, 'actualización TV'),
    ('Billares Don Miguel' in source, 'título TV'),
    (source.count('await _startBillaresMdns();') == 1, 'arranque mDNS'),
    (source.count('RawDatagramSocket? _billaresMdnsSocket;') == 1, 'socket mDNS'),
)
for ok, name in checks:
    if not ok:
        raise SystemExit(f'REPAIR FINAL FAILED: estructura {name} incompleta')

if "appVersion = '1.2.5+125'" not in source:
    raise SystemExit('REPAIR FINAL FAILED: versión 1.2.5+125 ausente')

print('OK: generación 1.2.5 completada con un único productor TV/LAN/mDNS')
