from pathlib import Path
import re
import subprocess

TARGET = Path('lib/main.dart')
s = TARGET.read_text()

# Este paso fija solamente la dirección pública del receptor y su puerto HTTP.
# El mDNS se instala después mediante ensure_mdns_1_2_5.py, por estructura del
# servidor, sin depender de nombres de clases o métodos concretos.
s = s.replace("final String url = 'http://$lanIp:8080/tv';", "final String url = 'http://billaresdonmiguel.local/tv';")
s = s.replace(
    "const Text('En la TV: abre su navegador y escribe exactamente la dirección anterior. El celular puede seguir usando CENTRAL normalmente.', style: TextStyle(fontSize: 12)),",
    "const Text('En la TV: escribe exactamente http://billaresdonmiguel.local/tv. No necesitas código ni IP. El celular puede seguir usando CENTRAL normalmente.', style: TextStyle(fontSize: 12)),",
)

# Normaliza cualquier servidor HTTP IPv4 existente a puerto 80.
bind_pattern = re.compile(r'HttpServer\.bind\s*\(\s*InternetAddress\.anyIPv4\s*,\s*([^,\)]+)([^\)]*)\)')
matches = list(bind_pattern.finditer(s))
if not matches:
    raise SystemExit('No se encontró HttpServer.bind del servidor TV')
first = matches[0]
if first.group(1).strip() != '80':
    replacement = f"HttpServer.bind(InternetAddress.anyIPv4, 80{first.group(2)})"
    s = s[:first.start()] + replacement + s[first.end():]

normalized = re.sub(r'\s+', ' ', s)
binds = re.findall(r'HttpServer\.bind\s*\(\s*InternetAddress\.anyIPv4\s*,\s*([^,\)]+)', normalized)
if not any(arg.strip() == '80' for arg in binds):
    raise SystemExit(f'El servidor TV no quedó en puerto 80: {binds}')
if 'billaresdonmiguel.local' not in s:
    raise SystemExit('Hostname TV ausente después de la reparación')

TARGET.write_text(s)
subprocess.check_call(['python3', 'scripts/repair_tv_final_safety.py'])
print('OK: hostname fijo billaresdonmiguel.local + HTTP puerto 80 + limpieza TV final')
