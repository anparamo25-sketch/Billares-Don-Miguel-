from pathlib import Path
import re

TARGET = Path('lib/main.dart')
FIELD = '  RawDatagramSocket? _billaresMdnsSocket;\n'
HTTP_SERVER_METHOD = '''  Future<void> startLanServer() async {
    try {
      server = await HttpServer.bind(InternetAddress.anyIPv4, 80, shared: true);
      final List<NetworkInterface> interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);
      final List<String> candidates = <String>[];
      for (final NetworkInterface networkInterface in interfaces) {
        final String name = networkInterface.name.toLowerCase();
        for (final InternetAddress address in networkInterface.addresses) {
          final String ip = address.address;
          final List<int> parts = ip.split('.').map(int.parse).toList();
          final bool privateIpv4 = parts.length == 4 && ((parts[0] == 10) || (parts[0] == 172 && parts[1] >= 16 && parts[1] <= 31) || (parts[0] == 192 && parts[1] == 168));
          if (!address.isLoopback && !address.isMulticast && !address.isLinkLocal && privateIpv4) {
            final int priority = name.contains('wlan') || name.contains('wifi') ? 0 : name.contains('eth') ? 1 : 2;
            candidates.add('$priority|$ip');
          }
        }
      }
      candidates.sort();
      if (candidates.isNotEmpty) lanIp = candidates.first.split('|').last;
      server!.listen(handleRequest, onError: (_) {});
      if (mounted) setState(() {});
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo iniciar el servidor LAN')));
      }
    }
  }
'''
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
        if source[i] == '(': depth += 1
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


def owner_class(source: str, marker_pos: int):
    for a, b, text in class_spans(source):
        if a <= marker_pos < b:
            return a, b, text
    return None


def insert_in_class(source: str, class_start: int, class_end: int, text: str) -> str:
    brace = source.find('{', class_start, class_end)
    if brace < 0:
        raise SystemExit('mDNS ENSURE FAILED: llave de clase no encontrada')
    return source[:brace + 1] + '\n' + text + source[brace + 1:]


s = TARGET.read_text()

# Rebuild the generated HTTP server structure if the previous generator left
# no literal HttpServer.bind. This is structural reconstruction, not a textual
# patch: the receiver always owns one canonical startLanServer implementation.
bind_match = re.search(r'\bHttpServer\.bind\s*\(', s)
if not bind_match:
    candidate = None
    for pattern in (
        r'\bFuture<void>\s+startLanServer\s*\(\)\s+async\s*\{',
        r'\bFuture<void>\s+handleRequest\s*\(HttpRequest\s+request\)',
        r'\bMap<String,\s*dynamic>\s+stateMap\s*\(\)',
        r'\bString\s+get\s+tvHtml\s*=>',
    ):
        m = re.search(pattern, s)
        if m:
            candidate = m
            break
    if candidate is None:
        raise SystemExit('mDNS ENSURE FAILED: no se encontró la clase real del receptor TV')
    owner = owner_class(s, candidate.start())
    if owner is None:
        raise SystemExit('mDNS ENSURE FAILED: no se encontró la clase real del receptor TV')
    class_start, class_end, owner_text = owner
    start_match = re.search(r'\bFuture<void>\s+startLanServer\s*\(\)\s+async\s*\{', owner_text)
    if start_match:
        local_open = owner_text.find('{', start_match.start(), start_match.end())
        local_end = matching_brace(owner_text, local_open)
        abs_start = class_start + start_match.start()
        abs_end = class_start + local_end
        s = s[:abs_start] + HTTP_SERVER_METHOD.rstrip() + s[abs_end:]
    else:
        # The real class exists but the server lifecycle method was removed.
        # Insert the canonical method before stateMap, keeping the existing
        # handleRequest and state model intact.
        marker = re.search(r'\bMap<String,\s*dynamic>\s+stateMap\s*\(\)', owner_text)
        if marker:
            abs_marker = class_start + marker.start()
            s = s[:abs_marker] + HTTP_SERVER_METHOD + '\n' + s[abs_marker:]
        else:
            s = insert_in_class(s, class_start, class_end, HTTP_SERVER_METHOD)

# Remove previous mDNS definitions safely and rebuild exactly one copy in the
# class that now contains the real HttpServer.bind.
s = remove_method(s, re.compile(r'(?m)^\s*Future<void>\s+_startBillaresMdns\s*\(\)\s+async\s*\{'))
s = remove_method(s, re.compile(r'(?m)^\s*void\s+_answerBillaresMdns\s*\(RawDatagramSocket\s+socket,\s*Datagram\s+datagram\)\s*\{'))
s = re.sub(r'(?m)^\s*RawDatagramSocket\?\s+_billaresMdnsSocket;\s*\n?', '', s)
s = re.sub(r'(?m)^\s*await\s+_startBillaresMdns\(\);\s*\n?', '', s)

bind_match = re.search(r'\bHttpServer\.bind\s*\(', s)
if not bind_match:
    raise SystemExit('mDNS ENSURE FAILED: no se pudo reconstruir HttpServer.bind')

owner = owner_class(s, bind_match.start())
if owner is None:
    raise SystemExit('mDNS ENSURE FAILED: clase del servidor HTTP no encontrada')
class_start, class_end, owner_text = owner

# Ensure the real HTTP bind uses port 80 without depending on formatting.
open_paren = s.find('(', bind_match.start())
close_paren = matching_paren(s, open_paren)
bind_args = s[open_paren + 1:close_paren]
if not re.search(r'InternetAddress\.anyIPv4\s*,\s*80\b', bind_args):
    if re.search(r'InternetAddress\.anyIPv4\s*,\s*\d+', bind_args):
        new_args = re.sub(r'(InternetAddress\.anyIPv4\s*,\s*)\d+', r'\g<1>80', bind_args, count=1)
    else:
        new_args = 'InternetAddress.anyIPv4, 80, shared: true'
    s = s[:open_paren + 1] + new_args + s[close_paren:]
    bind_match = re.search(r'\bHttpServer\.bind\s*\(', s)
    owner = owner_class(s, bind_match.start())
    class_start, class_end, owner_text = owner

# Add the mDNS field and methods to the actual server class.
s = insert_in_class(s, class_start, class_end, FIELD.rstrip())
bind_match = re.search(r'\bHttpServer\.bind\s*\(', s)
owner = owner_class(s, bind_match.start())
class_start, class_end, owner_text = owner
absolute = class_end - 1
s = s[:absolute] + '\n' + METHODS + s[absolute:]

# Start mDNS immediately after the complete HttpServer.bind(...) statement.
bind_match = re.search(r'\bHttpServer\.bind\s*\(', s)
open_paren = s.find('(', bind_match.start())
close_paren = matching_paren(s, open_paren)
semicolon = s.find(';', close_paren)
if semicolon < 0:
    raise SystemExit('mDNS ENSURE FAILED: final de HttpServer.bind no encontrado')
s = s[:semicolon + 1] + '\n      await _startBillaresMdns();' + s[semicolon + 1:]

# Final semantic validation.
bind_match = re.search(r'\bHttpServer\.bind\s*\(', s)
if not bind_match:
    raise SystemExit('mDNS ENSURE FAILED: HttpServer.bind ausente al validar')
owner = owner_class(s, bind_match.start())
if owner is None:
    raise SystemExit('mDNS ENSURE FAILED: clase del servidor ausente al validar')
owner_text = owner[2]
for marker in (
    FIELD.strip(),
    'Future<void> _startBillaresMdns() async',
    'void _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram)',
    'await _startBillaresMdns();',
    'RawDatagramSocket.bind',
    '5353',
    '224.0.0.251',
):
    if marker not in owner_text:
        raise SystemExit('mDNS ENSURE FAILED: componente ausente: ' + marker)
if not re.search(r'HttpServer\.bind\s*\(\s*InternetAddress\.anyIPv4\s*,\s*80\b', s):
    raise SystemExit('mDNS ENSURE FAILED: servidor HTTP no está en puerto 80')
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
print('OK: servidor HTTP y mDNS reconstruidos estructuralmente sobre la clase real del receptor TV')
