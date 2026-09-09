from pathlib import Path
import re

TARGET = Path('lib/main.dart')
source = TARGET.read_text()

# The historical preparation keeps the proven dashboard/jornada implementation.
# This final pass only enforces the agreed 1.2.6 constants and never introduces
# a second table-device architecture.
source = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.6+126';", source, count=1)
source = re.sub(r"const Map<int, double> tableRates = .*?;", "const Map<int, double> tableRates = <int, double>{1: 120, 2: 120, 3: 100, 4: 100, 5: 70};", source, count=1, flags=re.S)
if 'const Map<int, double> tableRates' not in source:
    anchor = "const String updateManifestUrl"
    position = source.index(anchor)
    line_end = source.index('\n', position)
    source = source[:line_end + 1] + "const Map<int, double> tableRates = <int, double>{1: 120, 2: 120, 3: 100, 4: 100, 5: 70};\n" + source[line_end + 1:]

# Keep the current single-TV architecture: there must not be code identifying
# separate table tablets/devices as part of the 1.2.6 application.
for forbidden in ('tableDevice', 'tableDeviceId', 'tableTablet', 'modo mesas', 'dispositivo de mesa'):
    if forbidden.lower() in source.lower():
        raise SystemExit(f'1.2.6 SOURCE FAILED: arquitectura antigua detectada: {forbidden}')

# Finalization time is mandatory in the TV state and cards.
if "'end': t.end == null ? null : clock(t.end!)" not in source and "'end': t.end == null ? null : clock(t.end!)" not in source:
    raise SystemExit('1.2.6 SOURCE FAILED: falta la hora de finalización en el estado TV')
if 'Finalización:' not in source:
    raise SystemExit('1.2.6 SOURCE FAILED: falta la hora de finalización en las tarjetas')

TARGET.write_text(source)
print('OK: fuente final 1.2.6 aplicada y validada')
