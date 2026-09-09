from pathlib import Path
import re
import py_compile

TARGET = Path('lib/main.dart')
source = TARGET.read_text()

# Este script es únicamente un validador. No modifica ni fabrica código.
# La reconstrucción completa de TV/LAN/mDNS pertenece al productor canónico
# repair_tv_1_2_4.py. Las dependencias de Dart se validan por compilación/análisis,
# no mediante requisitos textuales que puedan producir falsos negativos.
py_compile.compile('scripts/repair_tv_1_2_4.py', doraise=True)

normalized = re.sub(r'\s+', ' ', source)
checks = (
    (len(re.findall(r'\bHttpServer\s*\?\s*server\s*;', source)) == 1, 'campo HttpServer inválido'),
    (len(re.findall(r'\bString\s*\?\s*lanIp\s*;', source)) == 1, 'campo lanIp inválido'),
    (len(re.findall(r'\bFuture\s*<\s*void\s*>\s+startLanServer\s*\(\s*\)\s+async\s*\{', source)) == 1, 'startLanServer inválido'),
    (len(re.findall(r'\bFuture\s*<\s*void\s*>\s+_startBillaresMdns\s*\(\s*\)\s+async\s*\{', source)) == 1, 'método mDNS inválido'),
    (len(re.findall(r'\bFuture\s*<\s*String\s*\?>\s+_billaresLocalIp\s*\(\s*\)\s+async\s*\{', source)) == 1, 'detector IP inválido'),
    (len(re.findall(r'\bFuture\s*<\s*void\s*>\s+_answerBillaresMdns\s*\(\s*RawDatagramSocket\s+socket\s*,\s*Datagram\s+datagram\s*\)\s+async\s*\{', source)) == 1, 'respuesta mDNS inválida'),
    (source.count('await _startBillaresMdns();') == 1, 'arranque mDNS duplicado o ausente'),
    (bool(re.search(r'HttpServer\.bind\s*\(\s*InternetAddress\.anyIPv4\s*,\s*80\b', normalized)), 'servidor LAN no está en puerto 80'),
    ('224.0.0.251' in source, 'multicast mDNS ausente'),
    ('billaresdonmiguel.local' in source, 'hostname mDNS ausente'),
    ('http://billaresdonmiguel.local/tv' in source, 'URL del receptor TV ausente'),
    ('Billares Don Miguel' in source, 'título TV ausente'),
    ('/api/state?ts=' in source, 'actualización TV ausente'),
    ('===\'green\'' not in source, 'JavaScript salió del receptor TV'),
    ('\\nFuture<void> _startBillaresMdns()' not in source, 'saltos de línea literales detectados'),
)

for ok, message in checks:
    if not ok:
        raise SystemExit('mDNS ENSURE FAILED: ' + message)

print('OK: estructura TV/LAN/mDNS completa y coherente; este validador no modifica la fuente')
