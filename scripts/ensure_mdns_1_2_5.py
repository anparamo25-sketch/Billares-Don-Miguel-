from pathlib import Path
import re

TARGET = Path('lib/main.dart')
FIELD = 'RawDatagramSocket? _billaresMdnsSocket;'
METHODS = r'''\nFuture<void> _startBillaresMdns() async {\n  try {\n    _billaresMdnsSocket?.close();\n    final RawDatagramSocket socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 5353, reuseAddress: true, reusePort: true);\n    _billaresMdnsSocket = socket;\n    socket.joinMulticast(InternetAddress('224.0.0.251'));\n    socket.listen((RawSocketEvent event) {\n      if (event != RawSocketEvent.read) return;\n      final Datagram? datagram = socket.receive();\n      if (datagram != null) _answerBillaresMdns(socket, datagram);\n    });\n  } catch (_) {}\n}\n\nFuture<String?> _billaresLocalIp() async {\n  try {\n    final interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);\n    for (final NetworkInterface networkInterface in interfaces) {\n      for (final InternetAddress address in networkInterface.addresses) {\n        final String value = address.address;\n        if (value.startsWith('127.')) continue;\n        return value;\n      }\n    }\n  } catch (_) {}\n  return null;\n}\n\nFuture<void> _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram) async {\n  try {\n    final List<int> q = datagram.data;\n    if (q.length < 12) return;\n    final int qdCount = (q[4] << 8) | q[5];\n    int offset = 12;\n    bool matched = false;\n    for (int i = 0; i < qdCount; i++) {\n      final List<String> labels = <String>[];\n      while (offset < q.length) {\n        final int len = q[offset++];\n        if (len == 0) break;\n        if (len > 63 || offset + len > q.length) return;\n        labels.add(String.fromCharCodes(q.sublist(offset, offset + len)));\n        offset += len;\n      }\n      if (offset + 4 > q.length) return;\n      final int type = (q[offset] << 8) | q[offset + 1];\n      offset += 4;\n      if (labels.join('.').toLowerCase() == 'billaresdonmiguel.local' && (type == 1 || type == 255)) matched = true;\n    }\n    if (!matched) return;\n    final String? localIp = await _billaresLocalIp();\n    if (localIp == null) return;\n    final List<int> ip = localIp.split('.').map(int.parse).toList();\n    if (ip.length != 4) return;\n    final List<int> response = <int>[];\n    response.addAll(q.sublist(0, 2));\n    response.addAll(<int>[0x84, 0x00, (qdCount >> 8) & 255, qdCount & 255, 0, 1, 0, 0, 0, 0]);\n    response.addAll(q.sublist(12, offset));\n    response.addAll(<int>[0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, 120, 0, 4]);\n    response.addAll(ip);\n    socket.send(response, datagram.address, datagram.port);\n  } catch (_) {}\n}\n'''


def match_brace(s, pos):
    depth = 0; quote = None; triple = False; i = pos
    while i < len(s):
        if quote:
            token = quote * 3 if triple else quote
            if s.startswith(token, i): i += len(token); quote = None; triple = False; continue
            if s[i] == '\\' and not triple: i += 2; continue
            i += 1; continue
        if s.startswith("'''", i): quote, triple = "'", True; i += 3; continue
        if s.startswith('"""', i): quote, triple = '"', True; i += 3; continue
        if s[i] in "'\"": quote, triple = s[i], False; i += 1; continue
        if s.startswith('//', i):
            e = s.find('\n', i + 2); i = len(s) if e < 0 else e + 1; continue
        if s.startswith('/*', i):
            e = s.find('*/', i + 2); i = len(s) if e < 0 else e + 2; continue
        if s[i] == '{': depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0: return i + 1
        i += 1
    raise SystemExit('mDNS ENSURE FAILED: llaves Dart sin cerrar')


def match_paren(s, pos):
    depth = 0; quote = None; triple = False; i = pos
    while i < len(s):
        if quote:
            token = quote * 3 if triple else quote
            if s.startswith(token, i): i += len(token); quote = None; triple = False; continue
            if s[i] == '\\' and not triple: i += 2; continue
            i += 1; continue
        if s.startswith("'''", i): quote, triple = "'", True; i += 3; continue
        if s.startswith('"""', i): quote, triple = '"', True; i += 3; continue
        if s[i] in "'\"": quote, triple = s[i], False; i += 1; continue
        if s.startswith('//', i):
            e = s.find('\n', i + 2); i = len(s) if e < 0 else e + 1; continue
        if s.startswith('/*', i):
            e = s.find('*/', i + 2); i = len(s) if e < 0 else e + 2; continue
        if s[i] == '(': depth += 1
        elif s[i] == ')':
            depth -= 1
            if depth == 0: return i
        i += 1
    raise SystemExit('mDNS ENSURE FAILED: paréntesis Dart sin cerrar')


def remove_method(s, name):
    pat = re.compile(r'(?m)^\s*(?:Future<void>|void)\s+' + re.escape(name) + r'\s*\([^\n]*\)\s*(?:async\s*)?\{')
    while True:
        m = pat.search(s)
        if not m: return s
        end = match_brace(s, s.find('{', m.start(), m.end()))
        s = s[:m.start()] + s[end:]


def ensure_http_bind(s):
    bind = re.search(r'\bHttpServer\s*\.\s*bind\s*\(', s)
    if bind:
        op = s.find('(', bind.start()); cp = match_paren(s, op)
        args = s[op + 1:cp]
        if re.search(r'InternetAddress\.anyIPv4\s*,\s*80\b', args): return s
        if re.search(r'InternetAddress\.anyIPv4\s*,\s*\d+', args):
            args = re.sub(r'(InternetAddress\.anyIPv4\s*,\s*)\d+', r'\g<1>80', args, count=1)
        else:
            args = 'InternetAddress.anyIPv4, 80, shared: true'
        return s[:op + 1] + args + s[cp:]
    marker = re.search(r'\bMap<String,\s*dynamic>\s+stateMap\s*\(\)|\bFuture<void>\s+showTvConnection\s*\(\)|\bString\s+get\s+tvHtml\s*=>', s)
    if not marker:
        raise SystemExit('mDNS ENSURE FAILED: no se encontró receptor TV real')
    # Insert the canonical server method directly before the receiver state map.
    server = '''\n  Future<void> startLanServer() async {\n    try {\n      server = await HttpServer.bind(InternetAddress.anyIPv4, 80, shared: true);\n      server!.listen(handleRequest, onError: (_) {});\n      await _startBillaresMdns();\n      if (mounted) setState(() {});\n    } catch (_) {}\n  }\n'''
    return s[:marker.start()] + server + s[marker.start():]


s = TARGET.read_text()
s = remove_method(s, '_startBillaresMdns')
s = remove_method(s, '_answerBillaresMdns')
s = remove_method(s, '_billaresLocalIp')
s = re.sub(r'(?m)^\s*RawDatagramSocket\?\s+_billaresMdnsSocket;\s*\n?', '', s)
s = re.sub(r'(?m)^\s*await\s+_startBillaresMdns\(\);\s*\n?', '', s)
s = ensure_http_bind(s)

bind = re.search(r'\bHttpServer\s*\.\s*bind\s*\(', s)
if not bind: raise SystemExit('mDNS ENSURE FAILED: no se pudo construir HttpServer.bind')
open_pos = s.find('(', bind.start()); close_pos = match_paren(s, open_pos)
args = s[open_pos + 1:close_pos]
if not re.search(r'InternetAddress\.anyIPv4\s*,\s*80\b', args):
    raise SystemExit('mDNS ENSURE FAILED: servidor HTTP no está en puerto 80')

# The mDNS implementation is deliberately top-level: it does not depend on any
# generated Dashboard class name. Only the startup call is coupled to the actual
# HttpServer.bind statement, which is the stable structural anchor of the server.
insert_at = 0
imports = list(re.finditer(r'(?m)^import\s+[^\n]+\n', s))
if imports:
    insert_at = imports[-1].end()
s = s[:insert_at] + '\n' + FIELD + '\n' + METHODS + s[insert_at:]

bind = re.search(r'\bHttpServer\s*\.\s*bind\s*\(', s)
open_pos = s.find('(', bind.start()); close_pos = match_paren(s, open_pos)
semi = s.find(';', close_pos)
if semi < 0: raise SystemExit('mDNS ENSURE FAILED: final de HttpServer.bind no encontrado')
if 'await _startBillaresMdns();' not in s:
    s = s[:semi + 1] + '\n      await _startBillaresMdns();' + s[semi + 1:]

if not re.search(r'\bHttpServer\s*\.\s*bind\s*\(\s*InternetAddress\.anyIPv4\s*,\s*80\b', s): raise SystemExit('mDNS ENSURE FAILED: servidor HTTP no está en puerto 80')
if s.count(FIELD) != 1: raise SystemExit('mDNS ENSURE FAILED: socket mDNS duplicado')
if s.count('Future<void> _startBillaresMdns() async') != 1: raise SystemExit('mDNS ENSURE FAILED: método mDNS duplicado')
if s.count('Future<void> _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram) async') != 1: raise SystemExit('mDNS ENSURE FAILED: respuesta mDNS duplicada')
if s.count('Future<String?> _billaresLocalIp() async') != 1: raise SystemExit('mDNS ENSURE FAILED: detector IP duplicado')
if s.count('await _startBillaresMdns();') != 1: raise SystemExit('mDNS ENSURE FAILED: arranque mDNS duplicado')
if 'RawDatagramSocket.bind(InternetAddress.anyIPv4, 5353' not in s: raise SystemExit('mDNS ENSURE FAILED: socket multicast ausente')
if '224.0.0.251' not in s: raise SystemExit('mDNS ENSURE FAILED: multicast ausente')
if 'billaresdonmiguel.local' not in s: raise SystemExit('mDNS ENSURE FAILED: hostname ausente')

TARGET.write_text(s)
print('OK: servidor HTTP y mDNS reconstruidos estructuralmente sin depender de clases generadas')
