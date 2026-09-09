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
      try { socket.joinMulticast(multicast); } catch (_) {}
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
        if (labels.join('.').toLowerCase() == 'billaresdonmiguel.local' && (type == 1 || type == 255)) matched = true;
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


def matching_brace(source: str, open_pos: int) -> int:
    depth = 0
    quote = None
    triple = False
    i = open_pos
    while i < len(source):
        if quote:
            token = quote * 3 if triple else quote
            if source.startswith(token, i):
                i += len(token); quote = None; triple = False; continue
            if source[i] == '\\' and not triple:
                i += 2; continue
            i += 1; continue
        if source.startswith("'''", i): quote, triple = "'", True; i += 3; continue
        if source.startswith('"""', i): quote, triple = '"', True; i += 3; continue
        if source[i] in ("'", '"'): quote, triple = source[i], False; i += 1; continue
        if source.startswith('//', i):
            end = source.find('\n', i + 2); i = len(source) if end < 0 else end + 1; continue
        if source.startswith('/*', i):
            end = source.find('*/', i + 2); i = len(source) if end < 0 else end + 2; continue
        if source[i] == '{': depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0: return i + 1
        i += 1
    raise SystemExit('mDNS ENSURE FAILED: llaves Dart sin cerrar')


def all_class_spans(source: str):
    spans = []
    for match in re.finditer(r'\bclass\s+[A-Za-z_][A-Za-z0-9_]*\b[^\{]*\{', source):
        brace = source.find('{', match.start())
        try:
            end = matching_brace(source, brace)
        except SystemExit:
            continue
        spans.append((match.start(), end, source[match.start():end]))
    return spans


def remove_method(source: str, pattern: re.Pattern) -> str:
    while True:
        match = pattern.search(source)
        if not match: return source
        brace = source.find('{', match.start(), match.end())
        if brace < 0: return source
        end = matching_brace(source, brace)
        source = source[:match.start()] + source[end:]


s = TARGET.read_text()
classes = all_class_spans(s)
# Find the actual class that owns the HTTP listener. No dependency on any
# historical class name such as _DashboardPageState or method name startLanServer.
owner = None
for a, b, text in classes:
    if re.search(r'server!\.listen\(\s*handleRequest\b', text):
        owner = (a, b, text)
        break
if owner is None:
    raise SystemExit('mDNS ENSURE FAILED: no se encontró el servidor HTTP del receptor TV')

class_start, class_end, owner_text = owner

if FIELD.strip() not in owner_text:
    insert_at = s.find('{', class_start) + 1
    s = s[:insert_at] + '\n' + FIELD + s[insert_at:]

# Recalculate the owning class after the field insertion.
for a, b, text in all_class_spans(s):
    if re.search(r'server!\.listen\(\s*handleRequest\b', text):
        class_start, class_end, owner_text = a, b, text
        break
else:
    raise SystemExit('mDNS ENSURE FAILED: se perdió el servidor HTTP tras insertar socket')

# Remove only our generated mDNS methods, wherever they are in the source,
# then insert one clean copy inside the owning server class.
s = remove_method(s, re.compile(r'(?m)^\s*Future<void>\s+_startBillaresMdns\s*\(\)\s+async\s*\{'))
s = remove_method(s, re.compile(r'(?m)^\s*void\s+_answerBillaresMdns\s*\(RawDatagramSocket\s+socket,\s*Datagram\s+datagram\)\s*\{'))

for a, b, text in all_class_spans(s):
    if re.search(r'server!\.listen\(\s*handleRequest\b', text):
        class_start, class_end, owner_text = a, b, text
        break
else:
    raise SystemExit('mDNS ENSURE FAILED: servidor HTTP ausente después de limpiar mDNS')

marker = re.search(r'(?m)^\s*Map<String,\s*dynamic>\s+stateMap\s*\(\)', owner_text)
absolute = class_start + marker.start() if marker else class_end - 1
s = s[:absolute] + METHODS + '\n' + s[absolute:]

# Recalculate and attach startup to the real HTTP listener exactly once.
for a, b, text in all_class_spans(s):
    if re.search(r'server!\.listen\(\s*handleRequest\b', text):
        class_start, class_end, owner_text = a, b, text
        break
else:
    raise SystemExit('mDNS ENSURE FAILED: listener HTTP ausente al finalizar')

owner_text = re.sub(r'\n\s*await\s+_startBillaresMdns\(\);', '', owner_text)
listener = re.search(r'server!\.listen\(\s*handleRequest\b[^;]*\);', owner_text)
if not listener:
    raise SystemExit('mDNS ENSURE FAILED: listener HTTP no reconocido')
pos = listener.end()
owner_text = owner_text[:pos] + '\n      await _startBillaresMdns();' + owner_text[pos:]
s = s[:class_start] + owner_text + s[class_end:]

# Semantic validation over the actual owning class.
for a, b, text in all_class_spans(s):
    if re.search(r'server!\.listen\(\s*handleRequest\b', text):
        owner_text = text
        break
else:
    raise SystemExit('mDNS ENSURE FAILED: clase del servidor no encontrada al validar')

checks = (
    FIELD.strip(),
    'Future<void> _startBillaresMdns() async',
    'void _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram)',
    'await _startBillaresMdns();',
    'RawDatagramSocket.bind',
    '5353',
    '224.0.0.251',
    'server!.listen(handleRequest',
)
for marker in checks:
    if marker not in owner_text:
        raise SystemExit('mDNS ENSURE FAILED: componente ausente: ' + marker)
if 'billaresdonmiguel.local' not in s:
    raise SystemExit('mDNS ENSURE FAILED: hostname ausente')
if owner_text.count(FIELD.strip()) != 1:
    raise SystemExit('mDNS ENSURE FAILED: socket mDNS duplicado')
if owner_text.count('Future<void> _startBillaresMdns() async') != 1:
    raise SystemExit('mDNS ENSURE FAILED: método mDNS duplicado')
if owner_text.count('void _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram)') != 1:
    raise SystemExit('mDNS ENSURE FAILED: respuesta mDNS duplicada')
if owner_text.count('await _startBillaresMdns();') != 1:
    raise SystemExit('mDNS ENSURE FAILED: arranque mDNS duplicado')

TARGET.write_text(s)
print('OK: mDNS instalado por estructura del servidor, independiente de nombres históricos de clases y métodos')
