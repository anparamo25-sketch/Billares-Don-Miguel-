from pathlib import Path
import re

TARGET = Path('lib/main.dart')
FIELD = 'RawDatagramSocket? _billaresMdnsSocket;'
MDNS = '''
Future<void> _startBillaresMdns() async {
  try {
    _billaresMdnsSocket?.close();
    final RawDatagramSocket socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 5353, reuseAddress: true, reusePort: true);
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
    final List<NetworkInterface> interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);
    for (final NetworkInterface networkInterface in interfaces) {
      for (final InternetAddress address in networkInterface.addresses) {
        if (!address.isLoopback && !address.isLinkLocal && !address.isMulticast) return address.address;
      }
    }
  } catch (_) {}
  return null;
}

Future<void> _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram) async {
  try {
    final List<int> query = datagram.data;
    if (query.length < 12) return;
    final int questions = (query[4] << 8) | query[5];
    int offset = 12;
    bool matches = false;
    for (int i = 0; i < questions; i++) {
      final List<String> labels = <String>[];
      while (offset < query.length) {
        final int length = query[offset++];
        if (length == 0) break;
        if (length > 63 || offset + length > query.length) return;
        labels.add(String.fromCharCodes(query.sublist(offset, offset + length)));
        offset += length;
      }
      if (offset + 4 > query.length) return;
      final int type = (query[offset] << 8) | query[offset + 1];
      offset += 4;
      if (labels.join('.').toLowerCase() == 'billaresdonmiguel.local' && (type == 1 || type == 255)) matches = true;
    }
    if (!matches) return;
    final String? ip = await _billaresLocalIp();
    if (ip == null) return;
    final List<int> parts = ip.split('.').map(int.parse).toList();
    if (parts.length != 4) return;
    final List<int> response = <int>[];
    response.addAll(query.sublist(0, 2));
    response.addAll(<int>[0x84, 0, 0, 0, 0, 1, 0, 0, 0, 0]);
    response.addAll(query.sublist(12, offset));
    response.addAll(<int>[0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, 120, 0, 4]);
    response.addAll(parts);
    socket.send(response, datagram.address, datagram.port);
  } catch (_) {}
}
'''
SERVER = '''  Future<void> startLanServer() async {
    try {
      server = await HttpServer.bind(InternetAddress.anyIPv4, 80, shared: true);
      final List<NetworkInterface> interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);
      for (final NetworkInterface networkInterface in interfaces) {
        for (final InternetAddress address in networkInterface.addresses) {
          final List<int> p = address.address.split('.').map(int.parse).toList();
          if (p.length == 4 && !address.isLoopback && !address.isLinkLocal && !address.isMulticast && (p[0] == 10 || (p[0] == 172 && p[1] >= 16 && p[1] <= 31) || (p[0] == 192 && p[1] == 168))) { lanIp = address.address; }
        }
      }
      server!.listen(handleRequest, onError: (_) {});
      await _startBillaresMdns();
      if (mounted) setState(() {});
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo iniciar el servidor LAN en el puerto 80')));
    }
  }
'''

def brace_end(s, open_pos):
    depth = 0; i = open_pos; quote = None; triple = False
    while i < len(s):
        if quote:
            token = quote * 3 if triple else quote
            if s.startswith(token, i): quote = None; triple = False; i += len(token); continue
            if s[i] == '\\' and not triple: i += 2
            else: i += 1
            continue
        if s.startswith("'''", i): quote = "'"; triple = True; i += 3; continue
        if s.startswith('"""', i): quote = '"'; triple = True; i += 3; continue
        if s[i] in "'\"": quote = s[i]; i += 1; continue
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

def remove_async(s, names):
    pat = re.compile(r'\b(?:Future\s*<\s*void\s*>|Future\s*<\s*String\s*\?>)\s+(' + '|'.join(map(re.escape, names)) + r')\s*\([^)]*\)\s+async\s*\{')
    while True:
        m = pat.search(s)
        if not m: return s
        e = brace_end(s, s.find('{', m.start(), m.end()))
        s = s[:m.start()] + s[e:]

s = TARGET.read_text()
if "import 'dart:io';" not in s:
    imports = list(re.finditer(r'(?m)^import\s+[^\n]+\n', s)); pos = imports[-1].end() if imports else 0
    s = s[:pos] + "import 'dart:io';\n" + s[pos:]
s = remove_async(s, ('startLanServer', '_startBillaresMdns', '_answerBillaresMdns', '_billaresLocalIp'))
s = re.sub(r'(?m)^\s*RawDatagramSocket\?\s+_billaresMdnsSocket;\s*\n?', '', s)
# Reconstruir el servidor dentro de su clase real usando el campo HttpServer como ancla; no se exige nombre de clase ni stateMap.
server_field = re.search(r'\bHttpServer\s*\?\s*server\s*;', s)
if not server_field:
    raise SystemExit('mDNS ENSURE FAILED: la fuente generada no contiene el campo HttpServer del servidor LAN')
server_insert = server_field.end()
s = s[:server_insert] + '\n' + SERVER + s[server_insert:]
imports = list(re.finditer(r'(?m)^import\s+[^\n]+\n', s)); pos = imports[-1].end() if imports else 0
s = s[:pos] + '\n' + FIELD + MDNS + s[pos:]
normalized = re.sub(r'\s+', ' ', s)
checks = (
    (s.count(FIELD) == 1, 'socket mDNS duplicado'),
    (s.count('Future<void> _startBillaresMdns() async') == 1, 'método mDNS duplicado'),
    (s.count('Future<String?> _billaresLocalIp() async') == 1, 'detector IP duplicado'),
    (s.count('Future<void> _answerBillaresMdns(') == 1, 'respuesta mDNS duplicada'),
    (s.count('await _startBillaresMdns();') == 1, 'arranque mDNS duplicado'),
    (s.count('Future<void> startLanServer() async') == 1, 'servidor LAN duplicado'),
    (bool(re.search(r'HttpServer\.bind\s*\(\s*InternetAddress\.anyIPv4\s*,\s*80\b', normalized)), 'servidor LAN no quedó en puerto 80'),
    ('224.0.0.251' in s, 'multicast mDNS ausente'),
    ('billaresdonmiguel.local' in s, 'hostname mDNS ausente'),
    ('\\nFuture<void> _startBillaresMdns()' not in s, 'saltos de línea literales detectados'),
)
for ok, message in checks:
    if not ok: raise SystemExit('mDNS ENSURE FAILED: ' + message)
TARGET.write_text(s)
print('OK: servidor LAN y mDNS reconstruidos desde el campo HttpServer real; interfaz TV intacta')
