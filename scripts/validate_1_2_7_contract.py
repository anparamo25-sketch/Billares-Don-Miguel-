from pathlib import Path
import re

SOURCE = Path('lib/main.dart').read_text()
NORMALIZED = re.sub(r'\s+', ' ', SOURCE)

REQUIRED = {
    "version": "appVersion = '1.2.7+127'",
    "updater": 'Billares-Don-Miguel-/raw/refs/heads/main/update.json',
    "tv_getter": 'String get tvHtml =>',
    "tv_title": 'Billares Don Miguel',
    "tv_host": 'billaresdonmiguel.local',
    "tv_url": 'http://billaresdonmiguel.local/tv',
    "tv_api": '/api/state?ts=',
    "lan_port_field": 'lanPort',
    "mdns_socket": 'RawDatagramSocket',
    "mdns_group": '224.0.0.251',
    "mdns_port": '5353',
    "workday": 'workdayActive',
    "cash_close": 'workdayCashClose',
    "workday_games": 'workdayGames',
    "ota_permission": 'onCheckInstallApkPermission',
    "ota_install": 'onInstallApk(path)',
    "cloud_tv_import": "import 'cloud_tv_sync.dart';",
    "cloud_tv_publish": 'publishCloudTvState(',
}
for name, marker in REQUIRED.items():
    if marker not in SOURCE and marker not in NORMALIZED:
        raise SystemExit(f'1.2.7 CONTRACT FAILED: falta {name}: {marker}')

rate_decl = re.search(r'\btableRates\s*=\s*(?:<\s*int\s*,\s*double\s*>\s*)?\{([^{}]*)\}', SOURCE, flags=re.S)
if not rate_decl:
    raise SystemExit('1.2.7 CONTRACT FAILED: tarifas fijas incorrectas o ausentes')
entries = re.findall(r'(\d+)\s*:\s*(\d+(?:\.\d+)?)', rate_decl.group(1))
actual_rates = {int(table): float(rate) for table, rate in entries}
expected_rates = {1: 120.0, 2: 120.0, 3: 100.0, 4: 100.0, 5: 70.0}
if actual_rates != expected_rates or len(entries) != len(expected_rates):
    raise SystemExit('1.2.7 CONTRACT FAILED: tarifas fijas incorrectas o ausentes')

for port in (80, 8080):
    pattern = rf'HttpServer\.bind\(\s*InternetAddress\.anyIPv4\s*,\s*{port}\b'
    if not re.search(pattern, NORMALIZED):
        raise SystemExit(f'1.2.7 CONTRACT FAILED: servidor LAN sin soporte para puerto {port}')

for pattern, name in (
    (r'(?m)^\s*Future<void>\s+startLanServer\s*\(', 'startLanServer'),
    (r'(?m)^\s*Future<void>\s+showTvConnection\s*\(', 'showTvConnection'),
    (r'(?m)^\s*String\s+get\s+tvHtml\s*=>', 'tvHtml'),
):
    if len(re.findall(pattern, SOURCE)) != 1:
        raise SystemExit(f'1.2.7 CONTRACT FAILED: {name} debe existir exactamente una vez')

for marker in ('color:#1557c0', 'text-shadow:', 'font-size:clamp('):
    if marker not in SOURCE:
        raise SystemExit(f'1.2.7 CONTRACT FAILED: estilo TV ausente: {marker}')
for marker in ('.green{', '.red{', '.yellow{', "'Disponible'", "'En juego'", "'Pendiente de cobro'"):
    if marker not in SOURCE:
        raise SystemExit(f'1.2.7 CONTRACT FAILED: estado visual ausente: {marker}')
if 'Finalización:' not in SOURCE:
    raise SystemExit('1.2.7 CONTRACT FAILED: falta hora de finalización')
if 'panel externo' in SOURCE.lower() or 'vigilancia externa' in SOURCE.lower():
    raise SystemExit('1.2.7 CONTRACT FAILED: panel externo no permitido')
for forbidden in ('faltante', 'sobrante', 'diferencia de caja', 'caja cuadrada'):
    if forbidden in SOURCE.lower():
        raise SystemExit(f'1.2.7 CONTRACT FAILED: lógica prohibida: {forbidden}')

print('OK: contrato 1.2.7 con Cloud TV validado')
