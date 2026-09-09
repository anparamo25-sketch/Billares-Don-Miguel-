from pathlib import Path
import py_compile

# PRE-FLIGHT PURO. No modifica lib/main.dart y no crea estructura.
# La única fuente que produce TV/LAN/mDNS es repair_tv_1_2_4.py.
PRODUCER = Path('scripts/repair_tv_1_2_4.py')
TARGET = Path('lib/main.dart')

py_compile.compile(str(PRODUCER), doraise=True)
producer = PRODUCER.read_text()
source = TARGET.read_text()

required = (
    "RawDatagramSocket? _billaresMdnsSocket;",
    'Future<void> _startBillaresMdns() async',
    'Future<String?> _billaresLocalIp() async',
    'Future<void> _answerBillaresMdns(',
    'Future<void> startLanServer() async',
    'HttpServer.bind(InternetAddress.anyIPv4, 80',
    'await _startBillaresMdns();',
    'http://billaresdonmiguel.local/tv',
    '/api/state?ts=',
)
for marker in required:
    if marker not in producer.replace('\r', ''):
        raise SystemExit(f'mDNS PREFLIGHT FAILED: productor incompleto: {marker}')

# El resultado debe tener la estructura una sola vez, pero se comprueba de
# forma semántica y sin contar literales presentes en mensajes de error.
if source.count('RawDatagramSocket? _billaresMdnsSocket;') != 1:
    raise SystemExit('mDNS PREFLIGHT FAILED: socket mDNS duplicado o ausente')
if source.count('await _startBillaresMdns();') != 1:
    raise SystemExit('mDNS PREFLIGHT FAILED: arranque mDNS duplicado o ausente')
if 'http://billaresdonmiguel.local/tv' not in source:
    raise SystemExit('mDNS PREFLIGHT FAILED: receptor TV ausente')

print('OK: preflight mDNS completado; este script no modifica la fuente')
