from pathlib import Path
import py_compile
import re

PRODUCER = Path('scripts/rebuild_tv_1_2_5.py')

# Este preflight ocurre ANTES de generar lib/main.dart.
# Solo valida el productor canónico. La salida generada se valida
# posteriormente por repair_1_2_4_generated.py.
py_compile.compile(str(PRODUCER), doraise=True)
producer = re.sub(r'\s+', ' ', PRODUCER.read_text())
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

print('OK: preflight del productor canónico completado')
