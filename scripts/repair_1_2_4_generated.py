from pathlib import Path
import re
import subprocess
import py_compile

TARGET = Path('lib/main.dart')
STABLE_COMMIT = '5e5ec88e7f6c12f5c1dae006ad95da4b903f950d'

SCRIPTS = (
    'scripts/prepare_1_2_4.py',
    'scripts/repair_1_2_4_generated.py',
    'scripts/repair_tv_1_2_4.py',
    'scripts/repair_tv_hostname_1_2_5.py',
    'scripts/ensure_mdns_1_2_5.py',
    'scripts/repair_tv_final_safety.py',
)
for script in SCRIPTS:
    py_compile.compile(script, doraise=True)


def class_span(source: str, class_name: str):
    match = re.search(rf'\bclass\s+{re.escape(class_name)}\b[^{{]*\{{', source)
    if not match:
        raise SystemExit(f'No se encontró la clase {class_name}')
    start = match.start()
    brace = source.find('{', match.start())
    depth = 0
    quote = None
    triple = False
    i = brace
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
                continue
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
        if source[i] in ("'", '"'):
            quote, triple = source[i], False
            i += 1
            continue
        if source.startswith('//', i):
            end = source.find('\n', i + 2)
            i = len(source) if end < 0 else end + 1
            continue
        if source.startswith('/*', i):
            end = source.find('*/', i + 2)
            i = len(source) if end < 0 else end + 2
            continue
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    raise SystemExit(f'Llaves sin cerrar en {class_name}')


def extract_class(source: str, class_name: str) -> str:
    a, b = class_span(source, class_name)
    return source[a:b]


def replace_class(source: str, class_name: str, replacement: str) -> str:
    a, b = class_span(source, class_name)
    return source[:a] + replacement + source[b:]


def mask_strings_and_comments(source: str) -> str:
    """Oculta literales y comentarios conservando posiciones para validar Dart real."""
    out = list(source)
    i = 0
    n = len(source)
    quote = None
    triple = False
    while i < n:
        if quote:
            token = quote * 3 if triple else quote
            if source.startswith(token, i):
                for j in range(i, min(i + len(token), n)):
                    out[j] = ' '
                i += len(token)
                quote = None
                triple = False
                continue
            out[i] = '\n' if source[i] == '\n' else ' '
            if source[i] == '\\' and not triple and i + 1 < n:
                out[i + 1] = '\n' if source[i + 1] == '\n' else ' '
                i += 2
            else:
                i += 1
            continue
        if source.startswith('//', i):
            out[i] = ' '
            out[i + 1] = ' '
            i += 2
            while i < n and source[i] != '\n':
                out[i] = ' '
                i += 1
            continue
        if source.startswith('/*', i):
            out[i] = ' '
            out[i + 1] = ' '
            i += 2
            while i < n:
                if source.startswith('*/', i):
                    out[i] = ' '
                    out[i + 1] = ' '
                    i += 2
                    break
                out[i] = '\n' if source[i] == '\n' else ' '
                i += 1
            continue
        if source.startswith("'''", i):
            quote, triple = "'", True
            out[i:i + 3] = [' ', ' ', ' ']
            i += 3
            continue
        if source.startswith('"""', i):
            quote, triple = '"', True
            out[i:i + 3] = [' ', ' ', ' ']
            i += 3
            continue
        if source[i] in ("'", '"'):
            quote, triple = source[i], False
            out[i] = ' '
            i += 1
            continue
        i += 1
    return ''.join(out)


current = TARGET.read_text()
baseline = subprocess.check_output(['git', 'show', f'{STABLE_COMMIT}:lib/main.dart'], text=True)
current = replace_class(current, '_LoginPageState', extract_class(baseline, '_LoginPageState'))
current = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.5+125';", current, count=1)
current = re.sub(
    r"const String updateManifestUrl = '[^']+';",
    "const String updateManifestUrl = 'https://github.com/anparamo25-sketch/Billares-Don-Miguel-/raw/refs/heads/main/update.json';",
    current,
    count=1,
)

# Elimina imports duplicados sin alterar el orden ni el resto de la fuente.
lines = current.splitlines()
out = []
seen = set()
for line in lines:
    if line.startswith('import '):
        if line in seen:
            continue
        seen.add(line)
    out.append(line)
current = '\n'.join(out) + '\n'

login = extract_class(current, '_LoginPageState')
for bad in ('checkingUpdate', 'showSettings', 'logout', 'dashboard()', 'historyPage()'):
    if bad in login:
        raise SystemExit(f'REPAIR PREFLIGHT FAILED: {bad} quedó dentro de _LoginPageState')
if "appVersion = '1.2.5+125'" not in current:
    raise SystemExit('REPAIR PREFLIGHT FAILED: versión ausente')
if not re.search(r'\bMap<String,\s*dynamic>\s+stateMap\s*\(\)', current):
    raise SystemExit('REPAIR PREFLIGHT FAILED: stateMap del Dashboard ausente')
if not re.search(r'\bFuture\s*<\s*void\s*>\s+showTvConnection\s*\(', current):
    raise SystemExit('REPAIR PREFLIGHT FAILED: conexión TV ausente')

TARGET.write_text(current)
subprocess.check_call(['python3', 'scripts/repair_tv_1_2_4.py'])
subprocess.check_call(['python3', 'scripts/repair_tv_hostname_1_2_5.py'])
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
    if marker not in normalized:
        raise SystemExit(f'REPAIR TV FAILED: {message}')

binds = re.findall(r'HttpServer\.bind\s*\(\s*InternetAddress\.anyIPv4\s*,\s*([^,\)]+)', normalized)
if not binds or not any(arg.strip() == '80' for arg in binds):
    raise SystemExit(f'REPAIR TV FAILED: HttpServer.bind no está correctamente configurado en puerto 80: {binds}')
if 'billaresdonmiguel.local' not in normalized:
    raise SystemExit('REPAIR TV FAILED: hostname TV ausente')

# Validación estructural: primero ocultamos strings y comentarios para que los
# textos de mensajes, HTML y JavaScript jamás puedan contarse como código Dart.
code_only = mask_strings_and_comments(current)
show_tv_declarations = re.findall(
    r'\bFuture\s*<\s*void\s*>\s+showTvConnection\s*\(\s*\)\s+async\s*\{',
    code_only,
)
if len(show_tv_declarations) != 1:
    raise SystemExit(f'REPAIR TV FAILED: showTvConnection quedó {len(show_tv_declarations)} declaraciones reales')

tv_getter_matches = list(re.finditer(r'(?m)^\s*String\s+get\s+tvHtml\s*=>\s*', code_only))
if len(tv_getter_matches) != 1:
    raise SystemExit(f'REPAIR TV FAILED: tvHtml quedó {len(tv_getter_matches)} veces')
start = tv_getter_matches[0].start()
end = current.find('\n', start)
if end < 0:
    end = len(current)
tv_getter = current[start:end]
if not tv_getter.rstrip().endswith(';'):
    raise SystemExit('REPAIR TV FAILED: getter tvHtml no termina correctamente')
if '<!doctype html>' not in tv_getter.lower():
    raise SystemExit('REPAIR TV FAILED: HTML TV ausente')
if '/api/state?ts=' not in tv_getter:
    raise SystemExit('REPAIR TV FAILED: actualización TV ausente')
if 'C&#36;' not in tv_getter:
    raise SystemExit('REPAIR TV FAILED: formato monetario TV ausente')

# El JavaScript solo puede existir dentro del getter TV. Se inspecciona el código
# ya sin strings/comentarios, por lo que === dentro del HTML nunca dispara este check.
for line in code_only.splitlines():
    if '===' in line:
        raise SystemExit('REPAIR TV FAILED: JavaScript quedó fuera del getter TV')
if 'return r"""' in current or "return r'''" in current:
    raise SystemExit('REPAIR TV FAILED: triple comillas TV detectadas')
if 'String get tvHtml {' in current:
    raise SystemExit('REPAIR TV FAILED: getter tvHtml antiguo detectado')

TARGET.write_text(current)
print('OK: fuente 1.2.5 final; TV y mDNS validados estructural y semánticamente')
