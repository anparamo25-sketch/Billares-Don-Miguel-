from pathlib import Path
import re

TARGET = Path('lib/main.dart')
FIELD = '  RawDatagramSocket? _billaresMdnsSocket;'
METHODS = '''  Future<void> _startBillaresMdns() async {
    try {
      _billaresMdnsSocket?.close();
      final RawDatagramSocket socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 5353, reuseAddress: true, reusePort: true);
      _billaresMdnsSocket = socket;
      final InternetAddress multicast = InternetAddress('224.0.0.251');
      try { socket.joinMulticast(multicast); } catch (_) {}
      socket.listen((RawSocketEvent event) {
        if (event != RawSocketEvent.read) return;
        final Datagram? datagram = socket.receive();
        if (datagram != null) _answerBillaresMdns(socket, datagram);
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
      response.addAll(<int>[0x84, 0x00, (qdCount >> 8) & 255, qdCount & 255, 0, 1, 0, 0, 0, 0]);
      response.addAll(q.sublist(12, offset));
      response.addAll(<int>[0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, 120, 0, 4]);
      response.addAll(ip);
      socket.send(response, datagram.address, datagram.port);
    } catch (_) {}
  }
'''

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

def owner_class(s, marker):
    # Locate the real enclosing Dart class from its declaration, without requiring
    # any historical class name or assuming that the opening brace occurs before
    # the searched marker. This matches the structure actually emitted by Flutter.
    classes = list(re.finditer(r'\bclass\s+[A-Za-z_][A-Za-z0-9_]*\b', s))
    candidates = []
    for m in classes:
        if m.start() > marker + 1: break
        brace = s.find('{', m.end())
        if brace < 0: continue
        try:
            end = match_brace(s, brace)
        except SystemExit:
            continue
        if brace <= marker < end:
            candidates.append((m.start(), end))
    if candidates:
        return candidates[-1]
    return None

def remove_method(s, name):
    pat = re.compile(r'(?m)^\s*(?:Future<void>|void)\s+' + re.escape(name) + r'\s*\([^\n]*\)\s*(?:async\s*)?\{')
    while True:
        m = pat.search(s)
        if not m: return s
        end = match_brace(s, s.find('{', m.start(), m.end()))
        s = s[:m.start()] + s[end:]

def ensure_http_server(s):
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
    own = owner_class(s, marker.start())
    if not own:
        raise SystemExit('mDNS ENSURE FAILED: no se encontró la clase real del receptor TV')
    a, b = own
    server = '''  Future<void> startLanServer() async {
    try {
      server = await HttpServer.bind(InternetAddress.anyIPv4, 80, shared: true);
      server!.listen(handleRequest, onError: (_) {});
      if (mounted) setState(() {});
    } catch (_) {}
  }
'''
    inside = s[a:b]
    state = re.search(r'\bMap<String,\s*dynamic>\s+stateMap\s*\(\)', inside)
    if state:
        pos = a + state.start()
    else:
        brace = s.find('{', a, b)
        if brace < 0: raise SystemExit('mDNS ENSURE FAILED: cuerpo de clase TV no encontrado')
        pos = brace + 1
    return s[:pos] + server + '\n' + s[pos:]

s = TARGET.read_text()
s = remove_method(s, '_startBillaresMdns')
s = remove_method(s, '_answerBillaresMdns')
s = re.sub(r'(?m)^\s*RawDatagramSocket\?\s+_billaresMdnsSocket;\s*\n?', '', s)
s = re.sub(r'(?m)^\s*await\s+_startBillaresMdns\(\);\s*\n?', '', s)
s = ensure_http_server(s)

bind = re.search(r'\bHttpServer\s*\.\s*bind\s*\(', s)
if not bind: raise SystemExit('mDNS ENSURE FAILED: no se pudo construir HttpServer.bind')
open_pos = s.find('(', bind.start()); close_pos = match_paren(s, open_pos)
args = s[open_pos + 1:close_pos]
if not re.search(r'InternetAddress\.anyIPv4\s*,\s*80\b', args):
    args = re.sub(r'(InternetAddress\.anyIPv4\s*,\s*)\d+', r'\g<1>80', args, count=1) if re.search(r'InternetAddress\.anyIPv4\s*,\s*\d+', args) else 'InternetAddress.anyIPv4, 80, shared: true'
    s = s[:open_pos + 1] + args + s[close_pos:]

bind = re.search(r'\bHttpServer\s*\.\s*bind\s*\(', s)
own = owner_class(s, bind.start())
if not own: raise SystemExit('mDNS ENSURE FAILED: clase del servidor HTTP no encontrada')
a, b = own
brace = s.find('{', a, b)
s = s[:brace + 1] + '\n' + FIELD + s[brace + 1:]

bind = re.search(r'\bHttpServer\s*\.\s*bind\s*\(', s)
own = owner_class(s, bind.start())
a, b = own
s = s[:b - 1] + '\n' + METHODS + s[b - 1:]

bind = re.search(r'\bHttpServer\s*\.\s*bind\s*\(', s)
open_pos = s.find('(', bind.start()); close_pos = match_paren(s, open_pos)
semi = s.find(';', close_pos)
if semi < 0: raise SystemExit('mDNS ENSURE FAILED: final de HttpServer.bind no encontrado')
s = s[:semi + 1] + '\n      await _startBillaresMdns();' + s[semi + 1:]

if not re.search(r'\bHttpServer\s*\.\s*bind\s*\(\s*InternetAddress\.anyIPv4\s*,\s*80\b', s): raise SystemExit('mDNS ENSURE FAILED: servidor HTTP no está en puerto 80')
if s.count(FIELD) != 1: raise SystemExit('mDNS ENSURE FAILED: socket mDNS duplicado')
if s.count('Future<void> _startBillaresMdns() async') != 1: raise SystemExit('mDNS ENSURE FAILED: método mDNS duplicado')
if s.count('void _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram)') != 1: raise SystemExit('mDNS ENSURE FAILED: respuesta mDNS duplicada')
if 'await _startBillaresMdns();' not in s: raise SystemExit('mDNS ENSURE FAILED: arranque mDNS ausente')
if '5353' not in s or '224.0.0.251' not in s: raise SystemExit('mDNS ENSURE FAILED: configuración multicast ausente')
if 'billaresdonmiguel.local' not in s: raise SystemExit('mDNS ENSURE FAILED: hostname ausente')

TARGET.write_text(s)
print('OK: servidor HTTP y mDNS alineados con la estructura Dart real del receptor TV')
