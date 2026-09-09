from pathlib import Path
import py_compile
import re

PRODUCER = Path('scripts/rebuild_tv_1_2_5.py')
TARGET = Path('lib/main.dart')
py_compile.compile(str(PRODUCER), doraise=True)
producer = re.sub(r'\s+', ' ', PRODUCER.read_text())
source = TARGET.read_text()
checks = (
    ('RawDatagramSocket? _billaresMdnsSocket;' in producer, 'socket mDNS'),
    ('Future<void> _startBillaresMdns() async' in producer, 'inicio mDNS'),
    ('Future<String?> _billaresLocalIp() async' in producer, 'IP local'),
    ('Future<void> _answerBillaresMdns(' in producer, 'respuesta mDNS'),
    ('Future<void> startLanServer() async' in producer, 'servidor LAN'),
    (re.search(r'HttpServer\.bind\(\s*InternetAddress\.anyIPv4\s*,\s*80\b', producer) is not None, 'puerto LAN 80'),
    ('await _startBillaresMdns();' in producer, 'arranque mDNS'),
    ('http://billaresdonmiguel.local/tv' in producer, 'hostname TV'),
    ('/api/state?ts=' in producer, 'actualización TV'),
)
for ok, name in checks:
    if not ok:
        raise SystemExit(f'mDNS PREFLIGHT FAILED: productor incompleto: {name}')
if source.count('RawDatagramSocket? _billaresMdnsSocket;') != 1:
    raise SystemExit('mDNS PREFLIGHT FAILED: socket mDNS duplicado o ausente')
if source.count('await _startBillaresMdns();') != 1:
    raise SystemExit('mDNS PREFLIGHT FAILED: arranque mDNS duplicado o ausente')
if 'http://billaresdonmiguel.local/tv' not in source:
    raise SystemExit('mDNS PREFLIGHT FAILED: receptor TV ausente')
print('OK: preflight mDNS completado; este script no modifica la fuente')
