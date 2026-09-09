from pathlib import Path
import re
import subprocess

TARGET = Path('lib/main.dart')


def class_span(source: str, class_name: str):
    match = re.search(rf'\bclass\s+{re.escape(class_name)}\b[^{{]*\{{', source)
    if not match:
        raise SystemExit(f'No se encontró la clase {class_name}')
    start = match.start()
    brace = source.find('{', match.start())
    depth = 0
    in_string = False
    quote = ''
    escaped = False
    for i in range(brace, len(source)):
        ch = source[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == quote:
                in_string = False
            continue
        if ch in ("'", '"'):
            in_string = True
            quote = ch
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise SystemExit(f'Llaves sin cerrar en {class_name}')


def extract_class(source: str, class_name: str) -> str:
    a, b = class_span(source, class_name)
    return source[a:b]


def replace_class(source: str, class_name: str, replacement: str) -> str:
    a, b = class_span(source, class_name)
    return source[:a] + replacement + source[b:]


current = TARGET.read_text()
try:
    baseline = subprocess.check_output(['git', 'show', 'HEAD:lib/main.dart'], text=True)
except subprocess.CalledProcessError as exc:
    raise SystemExit(f'No se pudo recuperar el main.dart base: {exc}')

# The 1.2.4 generator previously used a broad build() regex. That could hit
# LoginPage instead of DashboardPage. Restore ONLY LoginPageState from the
# untouched repository source; all Dashboard/TV/history changes remain intact.
current = replace_class(current, '_LoginPageState', extract_class(baseline, '_LoginPageState'))

# Keep version/update constants from the 1.2.4 generator.
current = current.replace("const String appVersion = '1.2.1+121';", "const String appVersion = '1.2.4+124';")
current = current.replace("const String updateManifestUrl = 'https://raw.githubusercontent.com/anparamo25-sketch/Billares-Don-Miguel-/main/update.json';", "const String updateManifestUrl = 'https://github.com/anparamo25-sketch/Billares-Don-Miguel-/raw/refs/heads/main/update.json';")

# Remove duplicate imports if any repair pass is ever repeated.
lines = current.splitlines()
out = []
seen = set()
for line in lines:
    if line.startswith('import '):
        if line in seen:
            continue
        seen.add(line)
    out.append(line)
current = '\n'.join(out) + ('\n' if current.endswith('\n') else '')

# Structural preflight: fail here with a precise message instead of allowing
# malformed class targeting to reach flutter analyze.
login = extract_class(current, '_LoginPageState')
for bad in ('checkingUpdate', 'showSettings', 'logout', 'dashboard()', 'historyPage()'):
    if bad in login:
        raise SystemExit(f'REPAIR PREFLIGHT FAILED: {bad} quedó dentro de _LoginPageState')

if "appVersion = '1.2.4+124'" not in current:
    raise SystemExit('REPAIR PREFLIGHT FAILED: versión 1.2.4+124 ausente')
if 'class _DashboardPageState' not in current:
    raise SystemExit('REPAIR PREFLIGHT FAILED: DashboardPage ausente')
if 'Pantalla exclusiva para TV' not in current:
    raise SystemExit('REPAIR PREFLIGHT FAILED: receptor TV ausente')

TARGET.write_text(current)
print('OK: 1.2.4 generated source repaired and structurally validated')
