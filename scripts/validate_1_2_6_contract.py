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
    "lan_80": 'HttpServer.bind(InternetAddress.anyIPv4, 80',
    "lan_8080": 'HttpServer.bind(InternetAddress.anyIPv4, 8080',
    "mdns_socket": 'RawDatagramSocket',
    "mdns_group": '224.0.0.251',
    "mdns_port": '5353',
    "workday": 'workdayActive',
    "cash_close": 'workdayCashClose',
    "workday_games": 'workdayGames',
    "fixed_rates": 'tableRates = <int, double>{1: 120, 2: 120, 3: 100, 4: 100, 5: 70}',
    "ota_permission": 'onCheckInstallApkPermission',
    "ota_install": 'onInstallApk(path)',
}

for name, marker in REQUIRED.items():
    if marker not in SOURCE and marker not in NORMALIZED:
        raise SystemExit(f'1.2.6 CONTRACT FAILED: falta {name}: {marker}')

if SOURCE.count('String get tvHtml =>') != 1:
    raise SystemExit('1.2.6 CONTRACT FAILED: tvHtml debe existir exactamente una vez')
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

# No se permite introducir lógica de faltante/sobrante/diferencia de caja.
for forbidden in ('faltante', 'sobrante', 'diferencia de caja', 'caja cuadrada'):
    if forbidden in SOURCE.lower():
        raise SystemExit(f'1.2.6 CONTRACT FAILED: lógica prohibida encontrada: {forbidden}')

print('OK: contrato funcional y estructural 1.2.6 validado')
