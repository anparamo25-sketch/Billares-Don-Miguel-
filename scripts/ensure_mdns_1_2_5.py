from pathlib import Path
import re

TARGET = Path('lib/main.dart')
FIELD = 'RawDatagramSocket? _billaresMdnsSocket;'

METHODS = '''
Future<void> _startBillaresMdns() async {
  try {
    _billaresMdnsSocket?.close();
    final RawDatagramSocket socket = await RawDatagramSocket.bind(
      InternetAddress.anyIPv4,
      5353,
      reuseAddress: true,
      reusePort: true,
    );
    _billaresMdnsSocket = socket;
    socket.joinMulticast(InternetAddress('224.0.0.251'));
    socket.listen((RawSocketEvent event) {
      if (event != RawSocketEvent.read) return;
      final Datagram? datagram = socket.receive();
      if (datagram != null) _answerBillaresMdns(socket, datagram);
    });
  } catch (_) {}
}

Future<String?> _billaresLocalIp() async {
  try {
    final interfaces = await NetworkInterface.list(
      type: InternetAddressType.IPv4,
      includeLoopback: false,
    );
    for (final NetworkInterface networkInterface in interfaces) {
      for (final InternetAddress address in networkInterface.addresses) {
        final String value = address.address;
        if (value.startsWith('127.')) continue;
        return value;
      }
    }
  } catch (_) {}
  return null;
}

Future<void> _answerBillaresMdns(
  RawDatagramSocket socket,
  Datagram datagram,
) async {
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
      if (labels.join('.').toLowerCase() == 'billaresdonmiguel.local' &&
          (type == 1 || type == 255)) {
        matched = true;
      }
    }
    if (!matched) return;
    final String? localIp = await _billaresLocalIp();
    if (localIp == null) return;
    final List<int> ip = localIp.split('.').map(int.parse).toList();
    if (ip.length != 4) return;
    final List<int> response = <int>[];
    response.addAll(q.sublist(0, 2));
    response.addAll(<int>[0x84, 0x00, 0, 0, 0, 1, 0, 0, 0, 0]);
    response.addAll(q.sublist(12, offset));
    response.addAll(<int>[0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, 120, 0, 4]);
    response.addAll(ip);
    socket.send(response, datagram.address, datagram.port);
  } catch (_) {}
}
'''


def matching_brace(s: str, open_pos: int) -> int:
    depth = 0
    i = open_pos
    quote = None
    triple = False
    while i < len(s):
        if quote:
            token = quote * 3 if triple else quote
            if s.startswith(token, i):
                i += len(token)
                quote = None
                triple = False
                continue
            if s[i] == '\\' and not triple:
                i += 2
            else:
                i += 1
            continue
        if s.startswith("'''", i):
            quote, triple = "'", True
            i += 3
            continue
        if s.startswith('"""', i):
            quote, triple = '"', True
            i += 3
            continue
        if s[i] in "'\"":
            quote, triple = s[i], False
            i += 1
            continue
        if s.startswith('//', i):
            end = s.find('\n', i + 2)
            i = len(s) if end < 0 else end + 1
            continue
        if s.startswith('/*', i):
            end = s.find('*/', i + 2)
            i = len(s) if end < 0 else end + 2
            continue
        if s[i] == '{':
            depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise SystemExit('mDNS ENSURE FAILED: llaves Dart sin cerrar')


def function_spans(s: str):
    pattern = re.compile(
        r'\b(?:Future\s*<[^>]+>|void|[A-Za-z_][A-Za-z0-9_<>, ?]*)\s+'
        r'[A-Za-z_][A-Za-z0-9_]*\s*\([^;{}]*\)\s*(?:async\s*)?\{'
    )
    for m in pattern.finditer(s):
        open_pos = s.find('{', m.start(), m.end())
        try:
            yield m.start(), matching_brace(s, open_pos)
        except SystemExit:
            continue


def remove_method(s: str, name: str) -> str:
    pat = re.compile(
        r'(?m)^\s*Future\s*<\s*void\s*>\s+' + re.escape(name) +
        r'\s*\([^)]*\)\s+async\s*\{'
    )
    while True:
        m = pat.search(s)
        if not m:
            return s
        end = matching_brace(s, s.find('{', m.start(), m.end()))
        s = s[:m.start()] + s[end:]


def remove_field_and_calls(s: str) -> str:
    s = re.sub(r'(?m)^\s*RawDatagramSocket\?\s+_billaresMdnsSocket;\s*\n?', '', s)
    s = re.sub(r'(?m)^\s*await\s+_startBillaresMdns\(\);\s*\n?', '', s)
    return s


def normalize_http_bind(s: str) -> str:
    m = re.search(r'\bHttpServer\s*\.\s*bind\s*\(', s)
    if not m:
        raise SystemExit('mDNS ENSURE FAILED: no se encontró HttpServer.bind del servidor TV')
    op = s.find('(', m.start(), m.end())
    cp = s.find(')', op)
    if cp < 0:
        raise SystemExit('mDNS ENSURE FAILED: HttpServer.bind sin cerrar')
    args = s[op + 1:cp]
    if re.search(r'InternetAddress\.anyIPv4\s*,\s*\d+', args):
        args = re.sub(
            r'(InternetAddress\.anyIPv4\s*,\s*)\d+',
            r'\g<1>80',
            args,
            count=1,
        )
    elif 'InternetAddress.anyIPv4' in args:
        args = re.sub(
            r'InternetAddress\.anyIPv4\s*(?:,\s*)?',
            'InternetAddress.anyIPv4, 80',
            args,
            count=1,
        )
    s = s[:op + 1] + args + s[cp:]
    return s


s = TARGET.read_text()

if "import 'dart:io';" not in s:
    imports = list(re.finditer(r'(?m)^import\s+[^\n]+\n', s))
    at = imports[-1].end() if imports else 0
    s = s[:at] + "import 'dart:io';\n" + s[at:]

for name in ('_startBillaresMdns', '_answerBillaresMdns', '_billaresLocalIp'):
    s = remove_method(s, name)
s = remove_field_and_calls(s)
s = normalize_http_bind(s)

# The HTTP server was already validated by the preceding hostname step.
# This script NEVER fabricates a new server and NEVER searches for stateMap.
# It only attaches mDNS to the real function that owns the existing bind.
bind = re.search(r'\bHttpServer\s*\.\s*bind\s*\(', s)
if not bind:
    raise SystemExit('mDNS ENSURE FAILED: HttpServer.bind ausente después de normalizar')
bind_pos = bind.start()
owner = None
for start, end in function_spans(s):
    if start < bind_pos < end:
        owner = (start, end)
        break
if owner is None:
    raise SystemExit('mDNS ENSURE FAILED: HttpServer.bind no pertenece a una función Dart')

op = s.find('(', bind.start(), bind.end())
cp = s.find(')', op)
if cp < 0:
    raise SystemExit('mDNS ENSURE FAILED: HttpServer.bind sin cerrar')
if not re.search(r'InternetAddress\.anyIPv4\s*,\s*80\b', s[op + 1:cp]):
    raise SystemExit('mDNS ENSURE FAILED: servidor HTTP no está en puerto 80')

# Insert helpers at file scope, immediately after the imports.
imports = list(re.finditer(r'(?m)^import\s+[^\n]+\n', s))
at = imports[-1].end() if imports else 0
s = s[:at] + '\n' + FIELD + '\n' + METHODS + s[at:]

# Re-find the bind after insertion and attach exactly one startup call to the
# statement that owns it. This does not depend on class names or indentation.
bind = re.search(r'\bHttpServer\s*\.\s*bind\s*\(', s)
if not bind:
    raise SystemExit('mDNS ENSURE FAILED: HttpServer.bind no encontrado después de insertar mDNS')
op = s.find('(', bind.start(), bind.end())
cp = s.find(')', op)
semi = s.find(';', cp)
if cp < 0 or semi < 0:
    raise SystemExit('mDNS ENSURE FAILED: sentencia HttpServer.bind inválida')
s = s[:semi + 1] + '\n    await _startBillaresMdns();' + s[semi + 1:]

if s.count(FIELD) != 1:
    raise SystemExit('mDNS ENSURE FAILED: socket mDNS duplicado')
if s.count('Future<void> _startBillaresMdns() async') != 1:
    raise SystemExit('mDNS ENSURE FAILED: método mDNS duplicado')
if s.count('Future<void> _answerBillaresMdns(') != 1:
    raise SystemExit('mDNS ENSURE FAILED: respuesta mDNS duplicada')
if s.count('Future<String?> _billaresLocalIp() async') != 1:
    raise SystemExit('mDNS ENSURE FAILED: detector IP duplicado')
if s.count('await _startBillaresMdns();') != 1:
    raise SystemExit('mDNS ENSURE FAILED: arranque mDNS duplicado')
if 'RawDatagramSocket.bind(' not in s or '224.0.0.251' not in s:
    raise SystemExit('mDNS ENSURE FAILED: multicast ausente')
if 'billaresdonmiguel.local' not in s:
    raise SystemExit('mDNS ENSURE FAILED: hostname ausente')
if '\\nFuture<void> _startBillaresMdns()' in s or '\\nFuture<String?> _billaresLocalIp()' in s or '\\nFuture<void> _answerBillaresMdns(' in s:
    raise SystemExit('mDNS ENSURE FAILED: se detectaron saltos de línea literales')

TARGET.write_text(s)
print('OK: servidor HTTP existente preservado; mDNS añadido estructuralmente sin stateMap ni nombres de clase')
