from pathlib import Path
import re

TARGET = Path('lib/main.dart')
source = TARGET.read_text()
normalized = re.sub(r'\s+', ' ', source)

# Validación final pura. No reescribe HTML ni aplica parches. Si algo está mal,
# el productor canónico debe corregirse; este paso no intenta ocultarlo.
if len(re.findall(r'(?m)^\s*String\s+get\s+tvHtml\s*=>', source)) != 1:
    raise SystemExit('TV FINAL FAILED: receptor TV no es único')
if source.count('RawDatagramSocket? _billaresMdnsSocket;') != 1:
    raise SystemExit('TV FINAL FAILED: estructura mDNS no es única')
if source.count('await _startBillaresMdns();') != 1:
    raise SystemExit('TV FINAL FAILED: arranque mDNS no es único')
if len(re.findall(r'\bFuture\s*<\s*void\s*>\s+startLanServer\s*\(\s*\)\s+async\s*\{', source)) != 1:
    raise SystemExit('TV FINAL FAILED: servidor LAN no es único')
if 'HttpServer.bind(InternetAddress.anyIPv4, 80' not in normalized:
    raise SystemExit('TV FINAL FAILED: servidor LAN no usa puerto 80')
if 'http://billaresdonmiguel.local/tv' not in source:
    raise SystemExit('TV FINAL FAILED: hostname TV ausente')
if '/api/state?ts=' not in source:
    raise SystemExit('TV FINAL FAILED: actualización TV ausente')
if 'Billares Don Miguel' not in source:
    raise SystemExit('TV FINAL FAILED: título TV ausente')
if 'return r"""' in source or "return r'''" in source or 'String get tvHtml {' in source:
    raise SystemExit('TV FINAL FAILED: TV con triple comillas o bloque heredado')
if '\\nFuture<void> _startBillaresMdns()' in source:
    raise SystemExit('TV FINAL FAILED: salto de línea literal en mDNS')

print('OK: seguridad final TV/LAN/mDNS validada sin modificar la fuente')
