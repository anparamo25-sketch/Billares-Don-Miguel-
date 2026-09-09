from pathlib import Path
import re

TARGET = Path('lib/main.dart')

FIELD = '  RawDatagramSocket? _billaresMdnsSocket;\n'
METHODS = '''  Future<void> _startBillaresMdns() async {
    try {
      _billaresMdnsSocket?.close();
      final RawDatagramSocket socket = await RawDatagramSocket.bind(
        InternetAddress.anyIPv4,
        5353,
        reuseAddress: true,
        reusePort: true,
      );
      _billaresMdnsSocket = socket;
      final InternetAddress multicast = InternetAddress('224.0.0.251');
      try {
        socket.joinMulticast(multicast);
      } catch (_) {}
      socket.listen((RawSocketEvent event) {
        if (event != RawSocketEvent.read) return;
        final Datagram? datagram = socket.receive();
        if (datagram == null) return;
        _answerBillaresMdns(socket, datagram);
      });
    } catch (_) {}
  }

  void _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram) {
    try {
      final List<int> q = datagram.data;
      if (q.length < 12) return;
      final int qdCount = (q[4] << 8) | q[5];
      int offset = 12;
      bool matched = false;
      for (int i = 0; i < qdCount; i++) {
        final List<String> labels = <String>[];
        while (offset < q.length) {
          final int len = q[offset++];
          if (len == 0) break;
          if (len > 63 || offset + len > q.length) return;
          labels.add(String.fromCharCodes(q.sublist(offset, offset + len)));
          offset += len;
        }
        if (offset + 4 > q.length) return;
        final int type = (q[offset] << 8) | q[offset + 1];
        offset += 4;
        if (labels.join('.').toLowerCase() == 'billaresdonmiguel.local' && (type == 1 || type == 255)) {
          matched = true;
        }
      }
      if (!matched || lanIp == null) return;
      final List<int> ip = lanIp!.split('.').map(int.parse).toList();
      if (ip.length != 4) return;
      final List<int> response = <int>[];
      response.addAll(q.sublist(0, 2));
      response.addAll(<int>[0x84, 0x00, (qdCount >> 8) & 0xff, qdCount & 0xff, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]);
      response.addAll(q.sublist(12, offset));
      response.addAll(<int>[0xC0, 0x0C, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00, 0x78, 0x00, 0x04]);
      response.addAll(ip);
      socket.send(response, datagram.address, datagram.port);
    } catch (_) {}
  }
'''


def find_matching_brace(source: str, open_pos: int) -> int:
    depth = 0
    i = open_pos
    quote = None
    triple = False
    while i < len(source):
        if quote:
            token = quote * 3 if triple else quote
            if source.startswith(token, i):
                i += len(token)
                quote = None
                triple = False
                continue
            if source[i] == '\\' and not triple:
                i += 2
                continue
            i += 1
            continue
        if source.startswith("'''", i):
            quote, triple = "'", True
            i += 3
            continue
        if source.startswith('"""', i):
            quote, triple = '"', True
            i += 3
            continue
        if source[i] in ("'", '"'):
            quote, triple = source[i], False
            i += 1
            continue
        if source.startswith('//', i):
            end = source.find('\n', i + 2)
            i = len(source) if end < 0 else end + 1
            continue
        if source.startswith('/*', i):
            end = source.find('*/', i + 2)
            i = len(source) if end < 0 else end + 2
            continue
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise SystemExit('mDNS ENSURE FAILED: llaves Dart sin cerrar')


def dashboard_span(source: str):
    match = re.search(r'(?m)^class\s+_DashboardPageState\b[^\{]*\{', source)
    if not match:
        raise SystemExit('mDNS ENSURE FAILED: no se encontró _DashboardPageState')
    brace = source.find('{', match.start())
    return match.start(), find_matching_brace(source, brace)


def remove_method(source: str, pattern: re.Pattern) -> str:
    while True:
        match = pattern.search(source)
        if not match:
            return source
        brace = source.find('{', match.start(), match.end())
        end = find_matching_brace(source, brace)
        source = source[:match.start()] + source[end:]


s = TARGET.read_text()
class_start, class_end = dashboard_span(s)
owner = s[class_start:class_end]

# Work only inside the Dashboard class. This makes the operation independent of
# method names that may change during source preparation.
if FIELD.strip() not in owner:
    insert_at = s.find('{', class_start) + 1
    s = s[:insert_at] + '\n' + FIELD + s[insert_at:]
    class_start, class_end = dashboard_span(s)
    owner = s[class_start:class_end]

s = remove_method(s, re.compile(r'(?m)^\s*Future<void>\s+_startBillaresMdns\s*\(\)\s+async\s*\{'))
s = remove_method(s, re.compile(r'(?m)^\s*void\s+_answerBillaresMdns\s*\(RawDatagramSocket\s+socket,\s*Datagram\s+datagram\)\s*\{'))

class_start, class_end = dashboard_span(s)
owner = s[class_start:class_end]

# Insert the two mDNS methods immediately before stateMap when available; otherwise
# use the end of the Dashboard class. No dependency on startLanServer is required.
marker = re.search(r'(?m)^\s*Map<String,\s*dynamic>\s+stateMap\s*\(\)', owner)
if marker:
    absolute = class_start + marker.start()
else:
    absolute = class_end - 1
s = s[:absolute] + METHODS + '\n' + s[absolute:]

# Find the actual HTTP listener in Dashboard and make mDNS startup exactly once.
class_start, class_end = dashboard_span(s)
owner = s[class_start:class_end]
listener_matches = list(re.finditer(r'server!\.listen\(\s*handleRequest\b[^;]*\);', owner))
if not listener_matches:
    raise SystemExit('mDNS ENSURE FAILED: no se encontró el listener HTTP del Dashboard')

owner = re.sub(r'\n\s*await\s+_startBillaresMdns\(\);', '', owner)
listener_matches = list(re.finditer(r'server!\.listen\(\s*handleRequest\b[^;]*\);', owner))
listener = listener_matches[0]
pos = listener.end()
owner = owner[:pos] + '\n      await _startBillaresMdns();' + owner[pos:]
s = s[:class_start] + owner + s[class_end:]

class_start, class_end = dashboard_span(s)
owner = s[class_start:class_end]
checks = (
    FIELD.strip(),
    'Future<void> _startBillaresMdns() async',
    'void _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram)',
    'await _startBillaresMdns();',
    'billaresdonmiguel.local',
    'RawDatagramSocket.bind',
    '5353',
    '224.0.0.251',
    'server!.listen(handleRequest',
)
for marker in checks:
    if marker not in owner:
        raise SystemExit('mDNS ENSURE FAILED: componente ausente: ' + marker)
if owner.count(FIELD.strip()) != 1:
    raise SystemExit('mDNS ENSURE FAILED: socket mDNS duplicado')
if owner.count('Future<void> _startBillaresMdns() async') != 1:
    raise SystemExit('mDNS ENSURE FAILED: método mDNS duplicado')
if owner.count('void _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram)') != 1:
    raise SystemExit('mDNS ENSURE FAILED: respuesta mDNS duplicada')
if owner.count('await _startBillaresMdns();') != 1:
    raise SystemExit('mDNS ENSURE FAILED: arranque mDNS duplicado')

TARGET.write_text(s)
print('OK: mDNS reconstruido dentro de _DashboardPageState, independiente del nombre de startLanServer')
