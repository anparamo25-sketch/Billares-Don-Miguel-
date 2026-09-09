from pathlib import Path
import re
import subprocess
import py_compile

TARGET = Path('lib/main.dart')
STABLE = '5e5ec88e7f6c12f5c1dae006ad95da4b903f950d'
SCRIPTS = ('scripts/prepare_1_2_4.py', 'scripts/rebuild_tv_1_2_5.py', 'scripts/repair_tv_hostname_1_2_5.py', 'scripts/ensure_mdns_1_2_5.py', 'scripts/repair_tv_final_safety.py')
for script in SCRIPTS:
    py_compile.compile(script, doraise=True)


def class_span(source, name):
    m = re.search(rf'\bclass\s+{re.escape(name)}\b[^{{]*\{{', source)
    if not m:
        raise SystemExit(f'REPAIR PREFLIGHT FAILED: clase {name} ausente')
    depth = 0
    quote = None
    i = source.find('{', m.start(), m.end())
    while i < len(source):
        if quote:
            if source[i] == '\\':
                i += 2
                continue
            if source[i] == quote:
                quote = None
            i += 1
            continue
        if source.startswith("'''", i) or source.startswith('"""', i):
            quote = source[i]
            i += 3
            continue
        if source[i] in "'\"":
            quote = source[i]
        elif source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return m.start(), i + 1
        i += 1
    raise SystemExit(f'REPAIR PREFLIGHT FAILED: llaves sin cerrar en {name}')


def extract_class(source, name):
    a, b = class_span(source, name)
    return source[a:b]


def replace_class(source, name, replacement):
    a, b = class_span(source, name)
    return source[:a] + replacement + source[b:]


def replace_dashboard_method(source, name, replacement):
    a, b = class_span(source, '_DashboardPageState')
    body = source[a:b]
    match = re.search(rf'(?m)^\s*Future<void>\s+{re.escape(name)}\s*\([^)]*\)\s+async\s*\{{', body)
    if not match:
        raise SystemExit(f'REPAIR PREFLIGHT FAILED: método {name} ausente')
    start = body.find('{', match.start(), match.end())
    depth = 0
    quote = None
    i = start
    while i < len(body):
        if quote:
            if body[i] == '\\':
                i += 2
                continue
            if body[i] == quote:
                quote = None
            i += 1
            continue
        if body.startswith("'''", i) or body.startswith('"""', i):
            quote = body[i]
            i += 3
            continue
        if body[i] in "'\"":
            quote = body[i]
        elif body[i] == '{':
            depth += 1
        elif body[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                new_body = body[:match.start()] + replacement + body[end:]
                return source[:a] + new_body + source[b:]
        i += 1
    raise SystemExit(f'REPAIR PREFLIGHT FAILED: llaves sin cerrar en {name}')


current = TARGET.read_text()
baseline = subprocess.check_output(['git', 'show', f'{STABLE}:lib/main.dart'], text=True)
current = replace_class(current, '_LoginPageState', extract_class(baseline, '_LoginPageState'))
current = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.5+125';", current, count=1)
current = re.sub(r"const String updateManifestUrl = '[^']+';", "const String updateManifestUrl = 'https://github.com/anparamo25-sketch/Billares-Don-Miguel-/raw/refs/heads/main/update.json';", current, count=1)
seen = set()
lines = []
for line in current.splitlines():
    if line.startswith('import '):
        if line in seen:
            continue
        seen.add(line)
    lines.append(line)
TARGET.write_text('\n'.join(lines) + '\n')

login = extract_class(TARGET.read_text(), '_LoginPageState')
for forbidden in ('checkingUpdate', 'showSettings', 'logout', 'dashboard()', 'historyPage()'):
    if forbidden in login:
        raise SystemExit(f'REPAIR PREFLIGHT FAILED: {forbidden} dentro de _LoginPageState')
if not re.search(r'\bMap\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap\s*\(\s*\)', TARGET.read_text()):
    raise SystemExit('REPAIR PREFLIGHT FAILED: stateMap ausente')

subprocess.check_call(['python3', 'scripts/rebuild_tv_1_2_5.py'])
subprocess.check_call(['python3', 'scripts/repair_tv_hostname_1_2_5.py'])
subprocess.check_call(['python3', 'scripts/ensure_mdns_1_2_5.py'])
subprocess.check_call(['python3', 'scripts/repair_tv_final_safety.py'])

# La versión TV/LAN actual ya no utiliza url_launcher. La eliminación se hace
# después de la reconstrucción canónica, para que el productor no dependa de
# imports heredados de versiones anteriores.
source = TARGET.read_text()
source = source.replace("import 'package:url_launcher/url_launcher.dart';\n", '')

# Reconstrucción estructural del flujo de actualización: apk_install exige que
# REQUEST_INSTALL_PACKAGES esté habilitado en Android >= 8. Primero se verifica
# esa autorización (el plugin abre Ajustes si hace falta), luego se descarga y
# finalmente se inicia el instalador. Así no se confunde un fallo de instalación
# con un fallo de descarga.
update_method = '''  Future<void> downloadAndInstall(String url) async {
    HttpClient? client;
    try {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Preparando actualización...')));
      final bool installPermission = await ApkInstall().onCheckInstallApkPermission();
      if (!installPermission) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Activa "Permitir instalar aplicaciones desconocidas" para Billares Don Miguel y vuelve a pulsar Actualizar.')));
        }
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Descargando actualización...')));
      final Directory directory = await getApplicationDocumentsDirectory();
      final String path = '${directory.path}/billares-don-miguel-update.apk';
      client = HttpClient()..connectionTimeout = const Duration(seconds: 20);
      final HttpClientResponse response = await (await client.getUrl(Uri.parse(url))).close();
      if (response.statusCode != 200) throw const HttpException('Descarga fallida');
      final File file = File(path);
      final IOSink sink = file.openWrite();
      await response.pipe(sink);
      await sink.flush();
      await sink.close();
      final bool installStarted = await ApkInstall().onInstallApk(path);
      if (!installStarted && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Android no inició el instalador. Verifica el permiso de instalación y vuelve a intentarlo.')));
      }
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo descargar o iniciar la instalación de la actualización.')));
    } finally {
      client?.close(force: true);
    }
  }'''
source = replace_dashboard_method(source, 'downloadAndInstall', update_method)
TARGET.write_text(source)

source = TARGET.read_text()
normalized = re.sub(r'\s+', ' ', source)
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
    (source.count('onCheckInstallApkPermission') == 1, 'permiso de instalación'),
    (source.count('onInstallApk(path)') == 1, 'instalación APK'),
)
for ok, name in checks:
    if not ok:
        raise SystemExit(f'REPAIR FINAL FAILED: estructura {name} incompleta')
if "appVersion = '1.2.5+125'" not in source:
    raise SystemExit('REPAIR FINAL FAILED: versión 1.2.5+125 ausente')
print('OK: generación 1.2.5 completada mediante reconstrucción canónica única')
