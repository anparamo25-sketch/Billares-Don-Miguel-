from pathlib import Path
import re
import subprocess

TARGET = Path('lib/main.dart')
source = TARGET.read_text()

# Este paso ya no modifica el servidor ni aplica reemplazos de texto.
# La dirección del receptor forma parte de la reconstrucción canónica de TV y
# el servidor LAN/mDNS se reconstruye de forma estructural en ensure_mdns_1_2_5.py.
if 'http://billaresdonmiguel.local/tv' not in source:
    raise SystemExit('TV HOSTNAME FAILED: la reconstrucción TV no contiene el receptor billaresdonmiguel.local/tv')

if not re.search(r'\bFuture\s*<\s*void\s*>\s+startLanServer\s*\(\s*\)\s+async\s*\{', source):
    raise SystemExit('TV HOSTNAME FAILED: la fuente no contiene la función estructural startLanServer')

subprocess.check_call(['python3', 'scripts/repair_tv_final_safety.py'])
print('OK: hostname TV validado; este paso no aplica parches al servidor')
