from pathlib import Path

TARGET = Path('lib/main.dart')
source = TARGET.read_text()
# The existing billing domain method is collect(); normalize the generated UI action to that real method.
source = source.replace('chargeGame(table)', 'collect(table)')
TARGET.write_text(source)

required = (
    '_summaryCard(',
    'GridView.builder(',
    'NavigationDestination(',
    'LAN conectado',
    'LAN no disponible',
    'Pantalla exclusiva para TV',
    'Mostrar en TV',
    'Iniciar juego',
    'Finalizar juego',
    'Cobrar',
)
for marker in required:
    if marker not in source:
        raise SystemExit(f'ADMIN UI FAILED: falta {marker}')
if 'chargeGame(table)' in source:
    raise SystemExit('ADMIN UI FAILED: acción de cobro inexistente chargeGame')
print('OK: interfaz administrativa generada con acciones existentes y layout responsive')
