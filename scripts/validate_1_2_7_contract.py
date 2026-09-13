from pathlib import Path
import re

APP_SOURCE = Path('lib/main.dart').read_text()
TV_SOURCE = Path('cloud-tv/public/index.html').read_text()
APP_NORMALIZED = re.sub(r'\s+', ' ', APP_SOURCE)
TV_NORMALIZED = re.sub(r'\s+', ' ', TV_SOURCE)

PUBLIC_TV_URL = 'https://billaresdonmiguel.pages.dev'
if PUBLIC_TV_URL != 'https://billaresdonmiguel.pages.dev':
    raise SystemExit('1.3.0 CONTRACT FAILED: dominio publico de TV incorrecto')

REQUIRED_APP = {
    'updater': 'Billares-Don-Miguel-/raw/refs/heads/main/update.json',
    'tv_getter': 'String get tvHtml =>',
    'lan_port_field': 'lanPort',
    'mdns_socket': 'RawDatagramSocket',
    'mdns_group': '224.0.0.251',
    'mdns_port': '5353',
    'workday': 'workdayActive',
    'cash_close': 'workdayCashClose',
    'workday_games': 'workdayGames',
    'ota_permission': 'onCheckInstallApkPermission',
    'ota_install': 'onInstallApk(file.path)',
    'cloud_tv_import': "import 'cloud_tv_sync.dart';",
    'cloud_tv_publish': 'publishCloudTvState(',
}
for name, marker in REQUIRED_APP.items():
    if marker not in APP_SOURCE and marker not in APP_NORMALIZED:
        raise SystemExit(f'1.3.0 CONTRACT FAILED: falta {name}: {marker}')

rate_decl = re.search(
    r'\btableRates\s*=\s*(?:<\s*int\s*,\s*double\s*>\s*)?\{([^{}]*)\}',
    APP_SOURCE,
    flags=re.S,
)
if not rate_decl:
    raise SystemExit('1.3.0 CONTRACT FAILED: tarifas fijas incorrectas o ausentes')
entries = re.findall(r'(\d+)\s*:\s*(\d+(?:\.\d+)?)', rate_decl.group(1))
actual_rates = {int(table): float(rate) for table, rate in entries}
expected_rates = {1: 120.0, 2: 120.0, 3: 100.0, 4: 100.0, 5: 70.0}
if actual_rates != expected_rates or len(entries) != len(expected_rates):
    raise SystemExit('1.3.0 CONTRACT FAILED: tarifas fijas incorrectas o ausentes')

for port in (80, 8080):
    pattern = rf'HttpServer\.bind\(\s*InternetAddress\.anyIPv4\s*,\s*{port}\b'
    if not re.search(pattern, APP_NORMALIZED):
        raise SystemExit(f'1.3.0 CONTRACT FAILED: servidor LAN sin soporte para puerto {port}')

for pattern, name in (
    (r'(?m)^\s*Future<void>\s+startLanServer\s*\(', 'startLanServer'),
    (r'(?m)^\s*Future<void>\s+showTvConnection\s*\(', 'showTvConnection'),
    (r'(?m)^\s*String\s+get\s+tvHtml\s*=>', 'tvHtml'),
):
    if len(re.findall(pattern, APP_SOURCE)) != 1:
        raise SystemExit(f'1.3.0 CONTRACT FAILED: {name} debe existir exactamente una vez')

REQUIRED_TV = {
    'tv_title': 'Billares Don Miguel',
    'tv_api': '/api/state?ts=',
    'tv_stream': '/api/stream',
    'tv_routing': 'location.host',
    'tv_elapsed': 'Tiempo jugado',
    'tv_end': 'Finalización:',
    'tv_amount': 'TOTAL A PAGAR',
    'tv_logo': 'src="/tv-logo.png"',
    'tv_timer': 'setInterval(function(){if(lastState)render(lastState)},1000);',
}
for name, marker in REQUIRED_TV.items():
    if marker not in TV_SOURCE and marker not in TV_NORMALIZED:
        raise SystemExit(f'1.3.0 CONTRACT FAILED: falta {name} en la fuente TV: {marker}')

for marker in ('color:#1557c0', 'font-size:clamp('):
    if marker not in TV_SOURCE:
        raise SystemExit(f'1.3.0 CONTRACT FAILED: estilo TV ausente: {marker}')
for marker in (
    '.green{',
    '.red{',
    '.yellow{',
    'En juego',
    'Pendiente de cobro',
    'Disponible',
):
    if marker not in TV_SOURCE:
        raise SystemExit(f'1.3.0 CONTRACT FAILED: estado visual ausente: {marker}')

if 'Finalización:' not in TV_SOURCE:
    raise SystemExit('1.3.0 CONTRACT FAILED: falta hora de finalización en TV')
if 'panel externo' in APP_SOURCE.lower() or 'panel externo' in TV_SOURCE.lower():
    raise SystemExit('1.3.0 CONTRACT FAILED: panel externo no permitido')
for forbidden in ('faltante', 'sobrante', 'diferencia de caja', 'caja cuadrada'):
    if forbidden in APP_SOURCE.lower() or forbidden in TV_SOURCE.lower():
        raise SystemExit(f'1.3.0 CONTRACT FAILED: lógica prohibida: {forbidden}')

version_match = re.search(r"const String appVersion = '([^']+)';", APP_SOURCE)
if not version_match or version_match.group(1) != '1.3.0+130':
    raise SystemExit('1.3.0 CONTRACT FAILED: la fuente no corresponde a la versión 1.3.0+130')

print(f'OK: contrato funcional 1.3.0/130 validado; TV publica: {PUBLIC_TV_URL}')
