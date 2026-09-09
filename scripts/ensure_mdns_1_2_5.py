from pathlib import Path
import py_compile
PRODUCER=Path('scripts/rebuild_tv_1_2_5.py'); TARGET=Path('lib/main.dart')
py_compile.compile(str(PRODUCER),doraise=True)
producer=PRODUCER.read_text(); source=TARGET.read_text()
for marker in ('RawDatagramSocket? _billaresMdnsSocket;','Future<void> _startBillaresMdns() async','Future<String?> _billaresLocalIp() async','Future<void> _answerBillaresMdns(','Future<void> startLanServer() async','HttpServer.bind(InternetAddress.anyIPv4, 80','await _startBillaresMdns();','http://billaresdonmiguel.local/tv','/api/state?ts='):
    if marker not in producer.replace('\r',''): raise SystemExit(f'mDNS PREFLIGHT FAILED: productor incompleto: {marker}')
if source.count('RawDatagramSocket? _billaresMdnsSocket;')!=1: raise SystemExit('mDNS PREFLIGHT FAILED: socket mDNS duplicado o ausente')
if source.count('await _startBillaresMdns();')!=1: raise SystemExit('mDNS PREFLIGHT FAILED: arranque mDNS duplicado o ausente')
if 'http://billaresdonmiguel.local/tv' not in source: raise SystemExit('mDNS PREFLIGHT FAILED: receptor TV ausente')
print('OK: preflight mDNS completado; este script no modifica la fuente')
