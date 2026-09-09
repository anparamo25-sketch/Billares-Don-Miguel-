from pathlib import Path
import subprocess

# Ejecuta la preparación completa y previamente validada de la base 1.2.4,
# conserva sus funciones de dashboard, jornadas, historial, LAN y responsive,
# y promueve únicamente los marcadores de versión a 1.2.6+126.
BASE_COMMIT = '21c20b4fdf72303398bb46c35dc109e1df373856'
source = subprocess.check_output(['git', 'show', f'{BASE_COMMIT}:scripts/prepare_1_2_4.py'], text=True)
source = source.replace('1.2.4+124', '1.2.6+126').replace('Billares-Don-Miguel/1.2.4', 'Billares-Don-Miguel/1.2.6')
exec(compile(source, 'prepare_1_2_6_from_history.py', 'exec'), {'__name__': '__main__'})
Path('lib/main.dart').write_text(Path('lib/main.dart').read_text().replace('1.2.4+124', '1.2.6+126').replace('Billares-Don-Miguel/1.2.4', 'Billares-Don-Miguel/1.2.6'))
print('OK: preparación completa promovida a 1.2.6+126')
