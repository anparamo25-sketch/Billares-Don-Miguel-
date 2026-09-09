from pathlib import Path
import py_compile

# Este script es un preflight del PRODUCTOR canónico.
# No modifica lib/main.dart y no intenta reconstruir ni reconocer estructuras
# generadas con expresiones frágiles. La fuente de verdad es
# repair_tv_1_2_4.py; la sintaxis real de Dart queda a cargo de dart format,
# flutter analyze y flutter test en los pasos posteriores del workflow.
PRODUCER = Path('scripts/repair_tv_1_2_4.py')
TARGET = Path('lib/main.dart')

py_compile.compile(str(PRODUCER), doraise=True)
producer = PRODUCER.read_text()

required_producer_markers = (
    ("import 'dart:io';", 'dependencia dart:io'),
    ('RawDatagramSocket? _billaresMdnsSocket;', 'estructura mDNS'),
    ('Future<void> _startBillaresMdns() async', 'inicio mDNS'),
    ('Future<String?> _billaresLocalIp() async', 'detección de IP LAN'),
    ('Future<void> _answerBillaresMdns(', 'respuesta mDNS'),
    ('Future<void> startLanServer() async', 'servidor LAN'),
    ('HttpServer.bind(InternetAddress.anyIPv4, 80', 'servidor LAN en puerto 80'),
    ('await _startBillaresMdns();', 'arranque mDNS desde servidor LAN'),
    ('http://billaresdonmiguel.local/tv', 'receptor TV'),
    ('/api/state?ts=', 'actualización periódica del receptor TV'),
)

for marker, description in required_producer_markers:
    if marker not in producer:
        raise SystemExit(f'mDNS PREFLIGHT FAILED: productor canónico incompleto ({description})')

# El resultado generado no se modifica aquí. Solo se rechaza corrupción obvia
# que nunca debe salir del productor.
source = TARGET.read_text()
for bad in (
    '\\nFuture<void> _startBillaresMdns()',
    '\\nFuture<String?> _billaresLocalIp()',
    '\\nFuture<void> _answerBillaresMdns(',
):
    if bad in source:
        raise SystemExit('mDNS PREFLIGHT FAILED: se detectaron saltos de línea literales en Dart generado')

print('OK: productor canónico TV/LAN/mDNS verificado; este preflight no modifica la fuente')
