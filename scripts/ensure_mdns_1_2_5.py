from pathlib import Path
import re

TARGET = Path('lib/main.dart')
FIELD = '  RawDatagramSocket? _billaresMdnsSocket;\n'
METHOD = '''  Future<void> _startBillaresMdns() async {
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
      response.addAll(<int>[0x84, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]);
      response.addAll(q.sublist(12, offset));
      response.addAll(<int>[0xC0, 0x0C, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00, 0x78, 0x00, 0x04]);
      response.addAll(ip);
      socket.send(response, datagram.address, 5353);
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


def class_containing(source: str, position: int):
    matches = list(re.finditer(r'(?m)^class\s+[^\n\{]+\{', source))
    owner = None
    for match in matches:
        end = find_matching_brace(source, source.find('{', match.start()))
        if match.start() <= position < end:
            owner = (match.start(), end, match)
            break
    if owner is None:
        raise SystemExit('mDNS ENSURE FAILED: startLanServer no pertenece a una clase Dart')
    return owner


s = TARGET.read_text()
start_match = re.search(r'(?m)^\s*Future<void>\s+startLanServer\s*\(\)\s+async\s*\{', s)
if not start_match:
    raise SystemExit('mDNS ENSURE FAILED: no se encontró startLanServer')
class_start, class_end, _ = class_containing(s, start_match.start())

# Rebuild mDNS only inside the same Dart class that owns startLanServer.
# This prevents fields/methods from landing in unrelated classes.
if FIELD.strip() not in s[class_start:class_end]:
    insert_at = s.find('{', class_start) + 1
    s = s[:insert_at] + '\n' + FIELD + s[insert_at:]
    start_match = re.search(r'(?m)^\s*Future<void>\s+startLanServer\s*\(\)\s+async\s*\{', s)
    class_start, class_end, _ = class_containing(s, start_match.start())

# Remove only previous mDNS definitions if present, then insert exactly one copy.
method_matches = list(re.finditer(r'(?m)^\s*Future<void>\s+_startBillaresMdns\s*\(\)\s+async\s*\{', s))
for match in reversed(method_matches):
    end = find_matching_brace(s, s.find('{', match.start()))
    s = s[:match.start()] + s[end:]

answer_matches = list(re.finditer(r'(?m)^\s*void\s+_answerBillaresMdns\s*\(RawDatagramSocket\s+socket,\s*Datagram\s+datagram\)\s*\{', s))
for match in reversed(answer_matches):
    end = find_matching_brace(s, s.find('{', match.start()))
    s = s[:match.start()] + s[end:]

start_match = re.search(r'(?m)^\s*Future<void>\s+startLanServer\s*\(\)\s+async\s*\{', s)
class_start, class_end, _ = class_containing(s, start_match.start())
s = s[:start_match.start()] + METHOD + s[start_match.start():]

# Insert startup inside startLanServer, immediately after the actual HTTP listener.
start_match = re.search(r'(?m)^\s*Future<void>\s+startLanServer\s*\(\)\s+async\s*\{', s)
method_end = find_matching_brace(s, s.find('{', start_match.start()))
body = s[start_match.start():method_end]
if 'server!.listen(handleRequest);' not in body:
    raise SystemExit('mDNS ENSURE FAILED: startLanServer no contiene server!.listen(handleRequest)')
if body.count('await _startBillaresMdns();') > 0:
    body = re.sub(r'\n\s*await _startBillaresMdns\(\);', '', body)
listener = 'server!.listen(handleRequest);'
pos = body.find(listener) + len(listener)
body = body[:pos] + '\n      await _startBillaresMdns();' + body[pos:]
s = s[:start_match.start()] + body + s[method_end:]

# Validate semantic invariants, not fragile source formatting.
start_match = re.search(r'(?m)^\s*Future<void>\s+startLanServer\s*\(\)\s+async\s*\{', s)
class_start, class_end, _ = class_containing(s, start_match.start())
owner = s[class_start:class_end]
checks = (
    FIELD.strip(),
    'Future<void> _startBillaresMdns() async',
    'void _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram)',
    'await _startBillaresMdns();',
    "billaresdonmiguel.local",
    'RawDatagramSocket.bind',
    '5353',
    '224.0.0.251',
    'server!.listen(handleRequest);',
)
for marker in checks:
    if marker not in owner:
        raise SystemExit('mDNS ENSURE FAILED: componente ausente: ' + marker)
if owner.count('Future<void> _startBillaresMdns() async') != 1:
    raise SystemExit('mDNS ENSURE FAILED: método mDNS duplicado')
if owner.count('void _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram)') != 1:
    raise SystemExit('mDNS ENSURE FAILED: respuesta mDNS duplicada')
if owner.count('RawDatagramSocket? _billaresMdnsSocket;') != 1:
    raise SystemExit('mDNS ENSURE FAILED: socket mDNS duplicado')
if owner.count('await _startBillaresMdns();') != 1:
    raise SystemExit('mDNS ENSURE FAILED: arranque mDNS duplicado')

TARGET.write_text(s)
print('OK: mDNS reconstruido de forma determinista dentro de la clase que contiene startLanServer')
