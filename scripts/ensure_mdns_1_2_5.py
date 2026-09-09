from pathlib import Path
import py_compile

PRODUCER = Path('scripts/rebuild_tv_1_2_5.py')

# Este script valida únicamente el contrato del productor ANTES de generar
# lib/main.dart. No inspecciona ni modifica main.dart y no exige una firma
# textual concreta de la implementación generada.
py_compile.compile(str(PRODUCER), doraise=True)
producer = PRODUCER.read_text()
required = (
    'RawDatagramSocket',
    '_billaresLocalIp',
    '_answerBillaresMdns',
    '_startBillaresMdns',
    'startLanServer',
    'billaresdonmiguel.local/tv',
    '/api/state?ts=',
    'InternetAddress.anyIPv4',
    '5353',
    '224.0.0.251',
)
missing = [item for item in required if item not in producer]
if missing:
    raise SystemExit('mDNS PREFLIGHT FAILED: contrato del productor incompleto: ' + ', '.join(missing))

print('OK: contrato del productor TV/LAN/mDNS validado')
