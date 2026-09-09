from pathlib import Path
import re

TARGET = Path('lib/main.dart')
source = TARGET.read_text()
normalized = re.sub(r'\s+', ' ', source)

# Validación final pura. Nunca modifica la fuente.
checks = (
    (len(re.findall(r'(?m)^\s*String\s+get\s+tvHtml\s*=>', source)) == 1, 'receptor TV no es único'),
    (source.count('RawDatagramSocket? _billaresMdnsSocket;') == 1, 'estructura mDNS no es única'),
    (source.count('await _startBillaresMdns();') == 1, 'arranque mDNS no es único'),
    (len(re.findall(r'\bFuture\s*<\s*void\s*>\s+startLanServer\s*\(\s*\)\s+async\s*\{', source)) == 1, 'servidor LAN no es único'),
    ('HttpServer.bind(InternetAddress.anyIPv4, 80' in normalized, 'servidor LAN no usa puerto 80'),
    ('http://billaresdonmiguel.local/tv' in source, 'hostname TV ausente'),
    ('/api/state?ts=' in source, 'actualización TV ausente'),
    ('Billares Don Miguel' in source, 'título TV ausente'),
    ('return r"""' not in source and "return r'''" not in source, 'TV con triple comillas heredadas'),
)
for ok, message in checks:
    if not ok:
        raise SystemExit(f'TV FINAL FAILED: {message}')
print('OK: seguridad final TV/LAN/mDNS validada sin modificar la fuente')
