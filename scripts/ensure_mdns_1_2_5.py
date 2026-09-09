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


def matching_paren(source: str, open_pos: int) -> int:
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
        if source[i] == '(':
            depth += 1
        elif source[i] == ')':
            depth -= 1
            if depth == 0: return i
        i += 1
    raise SystemExit('mDNS ENSURE FAILED: paréntesis Dart sin cerrar')


def class_spans(source: str):
    spans = []
    for m in re.finditer(r'\bclass\s+[A-Za-z_][A-Za-z0-9_]*\b[^\{]*\{', source):
        brace = source.find('{', m.start(), m.end())
        try:
            end = matching_brace(source, brace)
        except SystemExit:
            continue
        spans.append((m.start(), end, source[m.start():end]))
    return spans


def remove_method(source: str, pattern: re.Pattern) -> str:
    while True:
        m = pattern.search(source)
        if not m:
            return source
        brace = source.find('{', m.start(), m.end())
        if brace < 0:
            return source
        end = matching_brace(source, brace)
        source = source[:m.start()] + source[end:]


s = TARGET.read_text()

# Find the real HTTP server by its actual bind call. We intentionally do not
# depend on any generated dashboard class or on a particular server variable
# or listener formatting.
bind_match = re.search(r'HttpServer\.bind\s*\(', s)
if not bind_match:
    raise SystemExit('mDNS ENSURE FAILED: no se encontró HttpServer.bind del receptor TV')

# Locate the class containing that real bind call.
owner = None
for a, b, text in class_spans(s):
    if a <= bind_match.start() < b:
        owner = (a, b, text)
        break
if owner is None:
    raise SystemExit('mDNS ENSURE FAILED: no se encontró la clase que contiene el servidor HTTP')

class_start, class_end, owner_text = owner

# Clean every generated copy before inserting one canonical implementation.
s = remove_method(s, re.compile(r'(?m)^\s*Future<void>\s+_startBillaresMdns\s*\(\)\s+async\s*\{'))
s = remove_method(s, re.compile(r'(?m)^\s*void\s+_answerBillaresMdns\s*\(RawDatagramSocket\s+socket,\s*Datagram\s+datagram\)\s*\{'))
s = re.sub(r'(?m)^\s*RawDatagramSocket\?\s+_billaresMdnsSocket;\s*\n?', '', s)

# Recompute the HTTP bind and owning class after cleanup.
bind_match = re.search(r'HttpServer\.bind\s*\(', s)
if not bind_match:
    raise SystemExit('mDNS ENSURE FAILED: servidor HTTP desapareció al limpiar')
for a, b, text in class_spans(s):
    if a <= bind_match.start() < b:
        class_start, class_end, owner_text = a, b, text
        break
else:
    raise SystemExit('mDNS ENSURE FAILED: clase del servidor HTTP no encontrada')

# Insert the field immediately inside the real server class.
insert_at = s.find('{', class_start, class_end) + 1
s = s[:insert_at] + '\n' + FIELD + s[insert_at:]

# Recompute class span and insert canonical mDNS methods before its closing brace.
for a, b, text in class_spans(s):
    if a <= bind_match.start() < b:
        class_start, class_end, owner_text = a, b, text
        break
absolute = class_end - 1
s = s[:absolute] + '\n' + METHODS + s[absolute:]

# Recompute the bind and its class one final time. Start mDNS immediately after
# the complete HttpServer.bind(...) expression; this does not depend on whether
# the HTTP listener is written as server.listen, await server.listen, or split
# across multiple lines.
bind_match = re.search(r'HttpServer\.bind\s*\(', s)
if not bind_match:
    raise SystemExit('mDNS ENSURE FAILED: HttpServer.bind no reconocido al finalizar')
open_paren = s.find('(', bind_match.start())
close_paren = matching_paren(s, open_paren)
semicolon = s.find(';', close_paren)
if semicolon < 0:
    raise SystemExit('mDNS ENSURE FAILED: final de HttpServer.bind no encontrado')

# Remove any existing startup invocation, then add exactly one after the bind.
s = re.sub(r'(?m)^\s*await\s+_startBillaresMdns\(\);\s*\n?', '', s)
# The cleanup above may shift positions, so find bind again.
bind_match = re.search(r'HttpServer\.bind\s*\(', s)
open_paren = s.find('(', bind_match.start())
close_paren = matching_paren(s, open_paren)
semicolon = s.find(';', close_paren)
if semicolon < 0:
    raise SystemExit('mDNS ENSURE FAILED: final de HttpServer.bind no encontrado')
s = s[:semicolon + 1] + '\n      await _startBillaresMdns();' + s[semicolon + 1:]

# Semantic validation inside the actual server class.
bind_match = re.search(r'HttpServer\.bind\s*\(', s)
for a, b, text in class_spans(s):
    if a <= bind_match.start() < b:
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
print('OK: mDNS alineado al HttpServer.bind real, sin nombres históricos ni parches de texto frágiles')
