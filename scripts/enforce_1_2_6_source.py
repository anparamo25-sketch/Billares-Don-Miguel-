from pathlib import Path
import re
import subprocess

TARGET = Path('lib/main.dart')

# Deterministic source transformations used by the release build.
subprocess.check_call(['python3', 'scripts/apply_admin_ui_1_2_6.py'])
subprocess.check_call(['python3', 'scripts/fix_mdns_1_2_6.py'])
subprocess.check_call(['python3', 'scripts/validate_generated_ui_1_2_6.py'])

source = TARGET.read_text()
source = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.6+126';", source, count=1)
source = re.sub(r"const Map<int, double> tableRates = .*?;", "const Map<int, double> tableRates = <int, double>{1: 120, 2: 120, 3: 100, 4: 100, 5: 70};", source, count=1, flags=re.S)
if 'const Map<int, double> tableRates' not in source:
    anchor = "const String updateManifestUrl"
    position = source.index(anchor)
    line_end = source.index('\n', position)
    source = source[:line_end + 1] + "const Map<int, double> tableRates = <int, double>{1: 120, 2: 120, 3: 100, 4: 100, 5: 70};\n" + source[line_end + 1:]

for forbidden in ('tableDevice', 'tableDeviceId', 'tableTablet', 'modo mesas', 'dispositivo de mesa'):
    if forbidden.lower() in source.lower():
        raise SystemExit(f'1.2.6 SOURCE FAILED: arquitectura antigua detectada: {forbidden}')

if "'end': t.end == null ? null : clock(t.end!)" not in source:
    raise SystemExit('1.2.6 SOURCE FAILED: falta la hora de finalización en el estado TV')
if 'Finalización:' not in source:
    raise SystemExit('1.2.6 SOURCE FAILED: falta la hora de finalización en las tarjetas')
for marker in ('_summaryCard(', 'NavigationDestination(', 'GridView.builder(', 'LAN conectado', 'Pantalla exclusiva para TV', 'Mostrar en TV', 'Iniciar juego', 'Finalizar juego', 'Cobrar'):
    if marker not in source:
        raise SystemExit(f'1.2.6 SOURCE FAILED: falta interfaz administrativa real: {marker}')
if 'chargeGame(table)' in source:
    raise SystemExit('1.2.6 SOURCE FAILED: acción de cobro inexistente chargeGame')

if '[0x84, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]' not in source:
    raise SystemExit('1.2.6 SOURCE FAILED: respuesta mDNS no usa encabezado DNS válido')
if source.count('RawDatagramSocket? _billaresMdnsSocket;') != 1:
    raise SystemExit('1.2.6 SOURCE FAILED: socket mDNS duplicado')
if source.count('Future<void> _answerBillaresMdns') != 1 or source.count('Future<void> _startBillaresMdns') != 1:
    raise SystemExit('1.2.6 SOURCE FAILED: funciones mDNS duplicadas o ausentes')

TARGET.write_text(source)
print('OK: fuente final 1.2.6 con interfaz administrativa nueva y mDNS corregido')
