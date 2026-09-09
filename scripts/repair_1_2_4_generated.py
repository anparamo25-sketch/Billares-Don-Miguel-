from pathlib import Path
import re
import subprocess
import py_compile

TARGET = Path('lib/main.dart')
STABLE_COMMIT = '5e5ec88e7f6c12f5c1dae006ad95da4b903f950d'

for script in ('scripts/prepare_1_2_4.py', 'scripts/repair_1_2_4_generated.py', 'scripts/repair_tv_1_2_4.py', 'scripts/repair_tv_hostname_1_2_5.py', 'scripts/ensure_mdns_1_2_5.py', 'scripts/repair_tv_final_safety.py'):
    try:
        py_compile.compile(script, doraise=True)
    except py_compile.PyCompileError as exc:
        raise SystemExit(f'PREFLIGHT PYTHON FAILED: {script}: {exc}')


def class_span(source: str, class_name: str):
    match = re.search(rf'\bclass\s+{re.escape(class_name)}\b[^{{]*\{{', source)
    if not match:
        raise SystemExit(f'No se encontró la clase {class_name}')
    start = match.start(); brace = source.find('{', match.start()); depth = 0
    quote = None; triple = False; i = brace
    while i < len(source):
        if quote:
            token = quote * 3 if triple else quote
            if source.startswith(token, i):
                i += len(token); quote = None; triple = False; continue
            if source[i] == '\\' and not triple: i += 2; continue
            i += 1; continue
        if source.startswith("'''", i): quote, triple = "'", True; i += 3; continue
        if source.startswith('"""', i): quote, triple = '"', True; i += 3; continue
        if source[i] in ("'", '"'): quote, triple = source[i], False; i += 1; continue
        if source.startswith('//', i):
            end = source.find('\n', i + 2); i = len(source) if end < 0 else end + 1; continue
        if source.startswith('/*', i):
            end = source.find('*/', i + 2); i = len(source) if end < 0 else end + 2; continue
        if source[i] == '{': depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0: return start, i + 1
        i += 1
    raise SystemExit(f'Llaves sin cerrar en {class_name}')


def extract_class(source: str, class_name: str) -> str:
    a, b = class_span(source, class_name); return source[a:b]


def replace_class(source: str, class_name: str, replacement: str) -> str:
    a, b = class_span(source, class_name); return source[:a] + replacement + source[b:]


current = TARGET.read_text()
baseline = subprocess.check_output(['git', 'show', f'{STABLE_COMMIT}:lib/main.dart'], text=True)
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
if "appVersion = '1.2.5+125'" not in current: raise SystemExit('REPAIR PREFLIGHT FAILED: versión ausente')
if 'class _DashboardPageState' not in current: raise SystemExit('REPAIR PREFLIGHT FAILED: Dashboard ausente')

TARGET.write_text(current)
subprocess.check_call(['python3', 'scripts/repair_tv_1_2_4.py'])
py_compile.compile('scripts/repair_tv_hostname_1_2_5.py', doraise=True)
subprocess.check_call(['python3', 'scripts/repair_tv_hostname_1_2_5.py'])
# Una sola reconstrucción canónica del servidor HTTP + mDNS.
# No se ejecuta una segunda pasada que pueda volver a insertar el mismo método.
subprocess.check_call(['python3', 'scripts/ensure_mdns_1_2_5.py'])

current = TARGET.read_text()
current = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.5+125';", current, count=1)
current = current.replace('tv_web_receiver_disabled', 'tv_cast').replace('ACTION_CAST_SETTINGS_DISABLED', 'ACTION_CAST_SETTINGS')

normalized = re.sub(r'\s+', ' ', current)
required = {
    'String get tvHtml =>': 'tvHtml ausente',
    'Billares Don Miguel - TV': 'título TV ausente',
    "fetch('/api/state?ts='+Date.now()": 'actualización TV ausente',
    'RawDatagramSocket? _billaresMdnsSocket;': 'mDNS ausente',
    'Future<void> _startBillaresMdns() async': 'método mDNS ausente',
    'await _startBillaresMdns();': 'arranque mDNS ausente',
    "function money(n){return 'C&#36; '": 'formato monetario TV ausente',
}
for marker, message in required.items():
    if marker not in normalized: raise SystemExit(f'REPAIR TV FAILED: {message}')

binds = re.findall(r'HttpServer\.bind\s*\(\s*InternetAddress\.anyIPv4\s*,\s*([^,\)]+)', normalized)
if not binds:
    raise SystemExit('REPAIR TV FAILED: no se encontró HttpServer.bind para el receptor TV')
if not any(arg.strip() == '80' for arg in binds):
    raise SystemExit(f'REPAIR TV FAILED: HttpServer.bind encontrado pero ningún puerto 80: {binds}')
if 'billaresdonmiguel.local' not in normalized:
    raise SystemExit('REPAIR TV FAILED: hostname TV ausente')

tv_getter_lines = [line for line in current.splitlines() if line.startswith('  String get tvHtml => ')]
if len(tv_getter_lines) != 1:
    raise SystemExit(f'REPAIR TV FAILED: tvHtml quedó {len(tv_getter_lines)} veces')
tv_getter = tv_getter_lines[0]
if not tv_getter.rstrip().endswith(';'):
    raise SystemExit('REPAIR TV FAILED: getter tvHtml no termina correctamente en ;')
if '<!doctype html>' not in tv_getter.lower():
    raise SystemExit('REPAIR TV FAILED: el getter TV no contiene HTML válido')
if '/api/state?ts=' not in tv_getter:
    raise SystemExit('REPAIR TV FAILED: el receptor TV perdió su actualización de estado')
if tv_getter.count('C&#36;') < 1:
    raise SystemExit('REPAIR TV FAILED: el receptor TV perdió el formato monetario')
if '===' in '\n'.join(line for line in current.splitlines() if not line.startswith('  String get tvHtml => ')):
    raise SystemExit('REPAIR TV FAILED: JavaScript quedó fuera del getter TV')

if len(re.findall(r'(?m)^\s*Future<void>\s+showTvConnection\s*\(\)\s+async\s*\{', current)) != 1:
    raise SystemExit('REPAIR TV FAILED: showTvConnection no quedó exactamente una vez')
if re.search(r'(?m)^\s*(?:Future<void>\s+showTvConnectionLegacy\d+|String\s+get\s+tvHtmlLegacy\d+)', current):
    raise SystemExit('REPAIR TV FAILED: quedaron definiciones heredadas')
if 'return r"""' in current or "return r'''" in current:
    raise SystemExit('REPAIR TV FAILED: todavía existe HTML con triple comillas')
if 'String get tvHtml {' in current:
    raise SystemExit('REPAIR TV FAILED: quedó getter tvHtml con bloque Dart antiguo')

TARGET.write_text(current)
print('OK: fuente 1.2.5 final; TV y mDNS validados estructural y semánticamente')
