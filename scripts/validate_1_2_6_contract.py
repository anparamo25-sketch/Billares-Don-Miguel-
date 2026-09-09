from pathlib import Path
import re

SOURCE = Path('lib/main.dart').read_text()
NORMALIZED = re.sub(r'\s+', ' ', SOURCE)

REQUIRED = {
    "version": "appVersion = '1.2.6+126'",
    "updater": 'Billares-Don-Miguel-/raw/refs/heads/main/update.json',
    "tv_getter": 'String get tvHtml =>',
    "tv_title": 'Billares Don Miguel',
    "tv_host": 'billaresdonmiguel.local',
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
}

for name, marker in REQUIRED.items():
    if marker not in SOURCE and marker not in NORMALIZED:
        raise SystemExit(f'1.2.6 CONTRACT FAILED: falta {name}: {marker}')

# Tarifas fijas: se acepta tanto const Map como Map, pero los cinco valores deben coincidir exactamente.
rate_pattern = r'(?:const\s+)?Map\s*<\s*int\s*,\s*double\s*>\s+tableRates\s*=\s*<\s*int\s*,\s*double\s*>\s*\{\s*1\s*:\s*120\s*,\s*2\s*:\s*120\s*,\s*3\s*:\s*100\s*,\s*4\s*:\s*100\s*,\s*5\s*:\s*70\s*\}'
if not re.search(rate_pattern, NORMALIZED):
    raise SystemExit('1.2.6 CONTRACT FAILED: tarifas fijas incorrectas o ausentes')

# Los puertos se validan semánticamente para no depender del formato que aplica dart format.
for port in (80, 8080):
    pattern = rf'HttpServer\.bind\(\s*InternetAddress\.anyIPv4\s*,\s*{port}\b'
    if not re.search(pattern, NORMALIZED):
        raise SystemExit(f'1.2.6 CONTRACT FAILED: servidor LAN sin soporte para puerto {port}')

# Debe existir una sola implementación de cada pieza crítica.
for pattern, name in (
    (r'(?m)^\s*Future<void>\s+startLanServer\s*\(', 'startLanServer'),
    (r'(?m)^\s*Future<void>\s+showTvConnection\s*\(', 'showTvConnection'),
    (r'(?m)^\s*String\s+get\s+tvHtml\s*=>', 'tvHtml'),
):
    count = len(re.findall(pattern, SOURCE))
    if count != 1:
        raise SystemExit(f'1.2.6 CONTRACT FAILED: {name} debe existir exactamente una vez (actual: {count})')

if SOURCE.count('RawDatagramSocket? _billaresMdnsSocket;') != 1:
    raise SystemExit('1.2.6 CONTRACT FAILED: socket mDNS duplicado o ausente')
if SOURCE.count('onCheckInstallApkPermission') != 1:
    raise SystemExit('1.2.6 CONTRACT FAILED: permiso OTA duplicado o ausente')
if SOURCE.count('onInstallApk(path)') != 1:
    raise SystemExit('1.2.6 CONTRACT FAILED: instalación OTA duplicada o ausente')

# Título de TV: azul rey con contorno blanco y tamaño responsive.
for marker in ('color:#1557c0', 'text-shadow:', 'font-size:clamp('):
    if marker not in SOURCE:
        raise SystemExit(f'1.2.6 CONTRACT FAILED: estilo TV ausente: {marker}')

# Estados visuales obligatorios.
for marker in ('.green{', '.red{', '.yellow{', "'Disponible'", "'En juego'", "'Pendiente de cobro'"):
    if marker not in SOURCE:
        raise SystemExit(f'1.2.6 CONTRACT FAILED: estado visual ausente: {marker}')

# La TV debe reflejar la hora de finalización en cada tarjeta.
if 'Finalización:' not in SOURCE:
    raise SystemExit('1.2.6 CONTRACT FAILED: falta hora de finalización en TV/tarjetas')

# El panel externo de vigilancia NO pertenece a 1.2.6.
if 'panel externo' in SOURCE.lower() or 'vigilancia externa' in SOURCE.lower():
    raise SystemExit('1.2.6 CONTRACT FAILED: el panel externo no pertenece a esta versión')

# No se permite introducir lógica de faltante/sobrante/diferencia de caja.
for forbidden in ('faltante', 'sobrante', 'diferencia de caja', 'caja cuadrada'):
    if forbidden in SOURCE.lower():
        raise SystemExit(f'1.2.6 CONTRACT FAILED: lógica prohibida encontrada: {forbidden}')

print('OK: contrato funcional y estructural 1.2.6 validado')
