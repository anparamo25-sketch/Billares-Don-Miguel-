from pathlib import Path
import re
import subprocess
import py_compile

TARGET = Path('lib/main.dart')
STABLE = '5e5ec88e7f6c12f5c1dae006ad95da4b903f950d'
PRODUCER = 'scripts/rebuild_tv_1_2_6.py'

py_compile.compile(PRODUCER, doraise=True)


def class_span(source, name):
    match = re.search(rf'\bclass\s+{re.escape(name)}\b[^{{]*\{{', source)
    if not match:
        raise SystemExit(f'1.2.6 PREFLIGHT FAILED: clase {name} ausente')
    depth = 0
    quote = None
    index = source.find('{', match.start(), match.end())
    while index < len(source):
        if quote:
            if source[index] == '\\':
                index += 2
                continue
            if source[index] == quote:
                quote = None
            index += 1
            continue
        if source.startswith("'''", index) or source.startswith('"""', index):
            quote = source[index]
            index += 3
            continue
        if source[index] in "'\"":
            quote = source[index]
        elif source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return match.start(), index + 1
        index += 1
    raise SystemExit(f'1.2.6 PREFLIGHT FAILED: llaves sin cerrar en {name}')


def replace_class(source, name, replacement):
    start, end = class_span(source, name)
    return source[:start] + replacement + source[end:]


def extract_class(source, name):
    start, end = class_span(source, name)
    return source[start:end]


def replace_dashboard_method(source, name, replacement):
    start, end = class_span(source, '_DashboardPageState')
    body = source[start:end]
    match = re.search(rf'(?m)^\s*Future<void>\s+{re.escape(name)}\s*\([^)]*\)\s+async\s*\{{', body)
    if not match:
        raise SystemExit(f'1.2.6 PREFLIGHT FAILED: método {name} ausente')
    brace = body.find('{', match.start(), match.end())
    depth = 0
    quote = None
    index = brace
    while index < len(body):
        if quote:
            if body[index] == '\\':
                index += 2
                continue
            if body[index] == quote:
                quote = None
            index += 1
            continue
        if body.startswith("'''", index) or body.startswith('"""', index):
            quote = body[index]
            index += 3
            continue
        if body[index] in "'\"":
            quote = body[index]
        elif body[index] == '{':
            depth += 1
        elif body[index] == '}':
            depth -= 1
            if depth == 0:
                new_body = body[:match.start()] + replacement + body[index + 1:]
                return source[:start] + new_body + source[end:]
        index += 1
    raise SystemExit(f'1.2.6 PREFLIGHT FAILED: llaves sin cerrar en {name}')


source = TARGET.read_text()
baseline = subprocess.check_output(['git', 'show', f'{STABLE}:lib/main.dart'], text=True)
source = replace_class(source, '_LoginPageState', extract_class(baseline, '_LoginPageState'))
source = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.6+126';", source, count=1)
source = re.sub(r"const String updateManifestUrl = '[^']+';", "const String updateManifestUrl = 'https://github.com/anparamo25-sketch/Billares-Don-Miguel-/raw/refs/heads/main/update.json';", source, count=1)

seen = set()
clean = []
for line in source.splitlines():
    if line.startswith('import '):
        if line in seen:
            continue
        seen.add(line)
    clean.append(line)
TARGET.write_text('\n'.join(clean) + '\n')

subprocess.check_call(['python3', PRODUCER])

# El updater queda con un flujo explícito: permiso -> descarga -> instalación.
update_method = '''  Future<void> downloadAndInstall(String url) async {
    HttpClient? client;
    try {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Preparando actualización...')));
      final bool installPermission = await ApkInstall().onCheckInstallApkPermission();
      if (!installPermission) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Activa el permiso para instalar aplicaciones desconocidas y vuelve a pulsar Actualizar.')));
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Descargando actualización...')));
      final Directory directory = await getApplicationDocumentsDirectory();
      final String path = '${directory.path}/billares-don-miguel-update.apk';
      client = HttpClient()..connectionTimeout = const Duration(seconds: 30);
      client.userAgent = 'Billares-Don-Miguel/1.2.6';
      final HttpClientRequest request = await client.getUrl(Uri.parse(url));
      final HttpClientResponse response = await request.close();
      if (response.statusCode != HttpStatus.ok) throw HttpException('HTTP ${response.statusCode}');
      final File file = File(path);
      final IOSink sink = file.openWrite();
      await response.pipe(sink);
      await sink.flush();
      await sink.close();
      if (!await file.exists() || await file.length() < 1024 * 1024) throw const HttpException('APK inválido o incompleto');
      final bool installStarted = await ApkInstall().onInstallApk(path);
      if (!installStarted && mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Android no inició el instalador. Verifica el permiso de instalación.')));
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo descargar o iniciar la instalación de la actualización.')));
    } finally {
      client?.close(force: true);
    }
  }'''
source = replace_dashboard_method(TARGET.read_text(), 'downloadAndInstall', update_method)
source = source.replace("import 'package:url_launcher/url_launcher.dart';\n", '')
TARGET.write_text(source)

source = TARGET.read_text()
normalized = re.sub(r'\s+', ' ', source)
required = (
    ("appVersion = '1.2.6+126'", 'versión 1.2.6+126'),
    ('tableRates = <int, double>{1: 120, 2: 120, 3: 100, 4: 100, 5: 70}', 'tarifas fijas'),
    ('Disponible', 'estado Disponible'),
    ('En juego', 'estado En juego'),
    ('Pendiente de cobro', 'estado Pendiente de cobro'),
    ('workdayActive', 'jornada activa'),
    ('openWorkday', 'apertura de jornada'),
    ('closeWorkday', 'cierre de jornada'),
    ('workdayCashClose', 'efectivo físico al cierre'),
    ('workdayGames', 'partidas de jornada'),
    ('String get tvHtml =>', 'receptor TV'),
    ('Billares Don Miguel', 'título TV'),
    ('billaresdonmiguel.local', 'mDNS TV'),
    ('/api/state?ts=', 'actualización TV'),
    ('RawDatagramSocket', 'mDNS socket'),
    ('224.0.0.251', 'multicast mDNS'),
    ('5353', 'puerto mDNS'),
    ('onCheckInstallApkPermission', 'permiso OTA'),
    ('onInstallApk(path)', 'instalación OTA'),
)
for marker, name in required:
    if marker not in source and marker not in normalized:
        raise SystemExit(f'1.2.6 FINAL FAILED: falta {name}')

if 'faltante' in source.lower() or 'sobrante' in source.lower() or 'diferencia de caja' in source.lower():
    raise SystemExit('1.2.6 FINAL FAILED: no debe existir cálculo de faltante/sobrante/diferencia')

if source.count('RawDatagramSocket? _billaresMdnsSocket;') != 1:
    raise SystemExit('1.2.6 FINAL FAILED: socket mDNS duplicado')
if source.count('String get tvHtml =>') != 1:
    raise SystemExit('1.2.6 FINAL FAILED: receptor TV duplicado')
if source.count('onCheckInstallApkPermission') != 1:
    raise SystemExit('1.2.6 FINAL FAILED: permiso OTA duplicado')
if source.count('onInstallApk(path)') != 1:
    raise SystemExit('1.2.6 FINAL FAILED: instalación OTA duplicada')

print('OK: fuente 1.2.6 reconstruida y validada estructuralmente')
