from pathlib import Path
import subprocess

# Execute the complete, previously validated 1.2.4 preparation from repository history,
# then promote only the release markers to 1.2.5+125. This preserves all dashboard,
# workday, history, LAN and responsive changes already implemented there.
BASE_COMMIT = '21c20b4fdf72303398bb46c35dc109e1df373856'
source = subprocess.check_output(['git', 'show', f'{BASE_COMMIT}:scripts/prepare_1_2_4.py'], text=True)
source = source.replace('1.2.4+124', '1.2.5+125').replace('Billares-Don-Miguel/1.2.4', 'Billares-Don-Miguel/1.2.5')
exec(compile(source, 'prepare_1_2_5_from_history.py', 'exec'), {'__name__': '__main__'})
Path('lib/main.dart').write_text(Path('lib/main.dart').read_text().replace('1.2.4+124', '1.2.5+125').replace('Billares-Don-Miguel/1.2.4', 'Billares-Don-Miguel/1.2.5'))
print('OK: preparación completa promovida a 1.2.5+125')
