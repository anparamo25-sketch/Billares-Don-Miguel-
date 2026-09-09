from pathlib import Path
import re

TARGET = Path('lib/main.dart')
FIELD = 'RawDatagramSocket? _billaresMdnsSocket;'

MDNS_HELPERS = '''
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
    final List<NetworkInterface> interfaces = await NetworkInterface.list(
      type: InternetAddressType.IPv4,
      includeLoopback: false,
    );
    for (final NetworkInterface networkInterface in interfaces) {
      for (final InternetAddress address in networkInterface.addresses) {
        if (!address.isLoopback && !address.isLinkLocal && !address.isMulticast) {
          return address.address;
        }
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
    final List<int> query = datagram.data;
    if (query.length < 12) return;
    final int questions = (query[4] << 8) | query[5];
    int offset = 12;
    bool matches = false;
    for (int index = 0; index < questions; index++) {
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
      if (labels.join('.').toLowerCase() == 'billaresdonmiguel.local' &&
          (type == 1 || type == 255)) {
        matches = true;
      }
    }
    if (!matches) return;
    final String? localIp = await _billaresLocalIp();
    if (localIp == null) return;
    final List<int> parts = localIp.split('.').map(int.parse).toList();
    if (parts.length != 4) return;
    final List<int> response = <int>[];
    response.addAll(query.sublist(0, 2));
    response.addAll(<int>[0x84, 0x00, 0, 0, 0, 1, 0, 0, 0, 0]);
    response.addAll(query.sublist(12, offset));
    response.addAll(<int>[0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, 120, 0, 4]);
    response.addAll(parts);
    socket.send(response, datagram.address, datagram.port);
  } catch (_) {}
}
'''

CANONICAL_SERVER = '''  Future<void> startLanServer() async {
    try {
      server = await HttpServer.bind(InternetAddress.anyIPv4, 80, shared: true);
      final List<NetworkInterface> interfaces = await NetworkInterface.list(
        type: InternetAddressType.IPv4,
        includeLoopback: false,
      );
      final List<String> candidates = <String>[];
      for (final NetworkInterface networkInterface in interfaces) {
        final String name = networkInterface.name.toLowerCase();
        for (final InternetAddress address in networkInterface.addresses) {
          final List<int> parts = address.address.split('.').map(int.parse).toList();
          final bool privateIpv4 = parts.length == 4 &&
              (parts[0] == 10 ||
                  (parts[0] == 172 && parts[1] >= 16 && parts[1] <= 31) ||
                  (parts[0] == 192 && parts[1] == 168));
          if (!address.isLoopback && !address.isMulticast && !address.isLinkLocal && privateIpv4) {
            final int priority = name.contains('wlan') || name.contains('wifi')
                ? 0
                : name.contains('eth')
                    ? 1
                    : 2;
            candidates.add('$priority|${address.address}');
          }
        }
      }
      candidates.sort();
      if (candidates.isNotEmpty) lanIp = candidates.first.split('|').last;
      server!.listen(handleRequest, onError: (_) {});
      await _startBillaresMdns();
      if (mounted) setState(() {});
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No se pudo iniciar el servidor LAN en el puerto 80')),
        );
      }
    }
  }
'''


def matching_brace(source: str, open_pos: int) -> int:
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
            else:
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
        if source[i] in "'\"":
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


def class_spans(source: str):
    pattern = re.compile(r'\bclass\s+[A-Za-z_][A-Za-z0-9_]*(?:\s+extends\s+[^\{]+)?(?:\s+with\s+[^\{]+)?\s*\{')
    for match in pattern.finditer(source):
        open_pos = source.find('{', match.start(), match.end())
        try:
            yield match.start(), matching_brace(source, open_pos)
        except SystemExit:
            continue


def remove_function(source: str, name: str) -> str:
    pattern = re.compile(
        r'\bFuture\s*<\s*void\s*>\s+' + re.escape(name) +
        r'\s*\([^)]*\)\s+async\s*\{'
    )
    while True:
        match = pattern.search(source)
        if not match:
            return source
        open_pos = source.find('{', match.start(), match.end())
        end_pos = matching_brace(source, open_pos)
        source = source[:match.start()] + source[end_pos:]


def remove_mdns(source: str) -> str:
    for name in ('_startBillaresMdns', '_answerBillaresMdns', '_billaresLocalIp'):
        source = remove_function(source, name)
    source = re.sub(r'(?m)^\s*RawDatagramSocket\?\s+_billaresMdnsSocket;\s*\n?', '', source)
    source = re.sub(r'(?m)^\s*await\s+_startBillaresMdns\(\);\s*\n?', '', source)
    return source


def replace_start_server(source: str) -> str:
    pattern = re.compile(
        r'\bFuture\s*<\s*void\s*>\s+startLanServer\s*\(\s*\)\s+async\s*\{'
    )
    match = pattern.search(source)
    if match:
        open_pos = source.find('{', match.start(), match.end())
        end_pos = matching_brace(source, open_pos)
        return source[:match.start()] + CANONICAL_SERVER + source[end_pos:]

    state = re.search(r'\bMap<String,\s*dynamic>\s+stateMap\s*\(\s*\)', source)
    if not state:
        raise SystemExit('mDNS ENSURE FAILED: no se encontró el método stateMap para ubicar el servidor LAN')

    owner = None
    for start, end in class_spans(source):
        if start < state.start() < end:
            owner = (start, end)
            break
    if owner is None:
        raise SystemExit('mDNS ENSURE FAILED: stateMap no pertenece a una clase Dart')
    return source[:state.start()] + CANONICAL_SERVER + '\n' + source[state.start():]


source = TARGET.read_text()
if "import 'dart:io';" not in source:
    imports = list(re.finditer(r'(?m)^import\s+[^\n]+\n', source))
    insert_at = imports[-1].end() if imports else 0
    source = source[:insert_at] + "import 'dart:io';\n" + source[insert_at:]

source = remove_mdns(source)
source = replace_start_server(source)

imports = list(re.finditer(r'(?m)^import\s+[^\n]+\n', source))
insert_at = imports[-1].end() if imports else 0
source = source[:insert_at] + '\n' + FIELD + '\n' + MDNS_HELPERS + source[insert_at:]

normalized = re.sub(r'\s+', ' ', source)
if source.count(FIELD) != 1:
    raise SystemExit('mDNS ENSURE FAILED: socket mDNS duplicado')
if source.count('Future<void> _startBillaresMdns() async') != 1:
    raise SystemExit('mDNS ENSURE FAILED: método mDNS duplicado')
if source.count('Future<String?> _billaresLocalIp() async') != 1:
    raise SystemExit('mDNS ENSURE FAILED: detector IP duplicado')
if source.count('Future<void> _answerBillaresMdns(') != 1:
    raise SystemExit('mDNS ENSURE FAILED: respuesta mDNS duplicada')
if source.count('await _startBillaresMdns();') != 1:
    raise SystemExit('mDNS ENSURE FAILED: arranque mDNS duplicado')
if not re.search(r'HttpServer\.bind\s*\(\s*InternetAddress\.anyIPv4\s*,\s*80\b', normalized):
    raise SystemExit('mDNS ENSURE FAILED: servidor LAN no quedó configurado en puerto 80')
if 'RawDatagramSocket.bind(' not in source or '224.0.0.251' not in source:
    raise SystemExit('mDNS ENSURE FAILED: multicast mDNS ausente')
if 'billaresdonmiguel.local' not in source:
    raise SystemExit('mDNS ENSURE FAILED: hostname mDNS ausente')
if '\\nFuture<void> _startBillaresMdns()' in source or '\\nFuture<String?> _billaresLocalIp()' in source or '\\nFuture<void> _answerBillaresMdns(' in source:
    raise SystemExit('mDNS ENSURE FAILED: saltos de línea literales detectados')

TARGET.write_text(source)
print('OK: servidor LAN reconstruido estructuralmente en puerto 80 y mDNS integrado; sin stateMap como dependencia de búsqueda, sin nombres de clase y sin parches de texto')
