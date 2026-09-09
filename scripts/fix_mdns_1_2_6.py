from pathlib import Path
import re

TARGET = Path('lib/main.dart')


def skip_string(source, index):
    quote = source[index]
    token = quote * 3 if source.startswith(quote * 3, index) else quote
    index += len(token)
    while index < len(source):
        if source[index] == '\\':
            index += 2
            continue
        if source.startswith(token, index):
            return index + len(token)
        index += 1
    raise SystemExit('MDNS 1.2.6 FAILED: cadena Dart sin cerrar')


def top_level_function_span(source, name):
    match = re.search(rf'(?m)^Future<void>\s+{re.escape(name)}\s*\([^)]*\)\s*\{{', source)
    if not match:
        raise SystemExit(f'MDNS 1.2.6 FAILED: función {name} ausente')
    brace = source.find('{', match.start(), match.end())
    depth = 0
    i = brace
    while i < len(source):
        if source[i] in "'\"":
            i = skip_string(source, i); continue
        if source.startswith('//', i):
            e = source.find('\n', i + 2); i = len(source) if e < 0 else e + 1; continue
        if source[i] == '{': depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0: return match.start(), i + 1
        i += 1
    raise SystemExit(f'MDNS 1.2.6 FAILED: llaves de {name} sin cerrar')


def replace_function(source, name, replacement):
    start, end = top_level_function_span(source, name)
    return source[:start] + replacement + source[end:]


answer = r'''Future<void> _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram) async {
  try {
    final List<int> query = datagram.data;
    if (query.length < 12) return;
    final int questions = (query[4] << 8) | query[5];
    var offset = 12;
    String? matchedName;
    int? matchedType;
    for (var i = 0; i < questions; i++) {
      final labels = <String>[];
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
      if (labels.join('.').toLowerCase() == 'billaresdonmiguel.local' && (type == 1 || type == 255)) {
        matchedName = 'billaresdonmiguel.local';
        matchedType = type;
      }
    }
    if (matchedName == null || matchedType == null) return;
    final String? ip = await _billaresLocalIp();
    if (ip == null) return;
    final List<int> octets = ip.split('.').map(int.parse).toList();
    if (octets.length != 4) return;

    // DNS header: transaction ID, response flags 0x8400, QDCOUNT=0,
    // ANCOUNT=1, NSCOUNT=0, ARCOUNT=0. The previous implementation
    // incorrectly wrote TTL/RDLENGTH into the header, producing an invalid packet.
    final response = <int>[];
    response.addAll(query.sublist(0, 2));
    response.addAll(<int>[0x84, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]);
    response.addAll(<int>[0xC0, 0x0C]);
    response.addAll(<int>[0x00, 0x01, 0x00, 0x01]);
    response.addAll(<int>[0x00, 0x00, 0x00, 0x78]);
    response.addAll(<int>[0x00, 0x04]);
    response.addAll(octets);
    socket.send(response, datagram.address, datagram.port);
  } catch (_) {}
}
'''

start_mdns = r'''Future<void> _startBillaresMdns() async {
  try {
    _billaresMdnsSocket?.close();
    final RawDatagramSocket socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 5353, reuseAddress: true, reusePort: true);
    _billaresMdnsSocket = socket;
    socket.broadcastEnabled = true;
    socket.joinMulticast(InternetAddress('224.0.0.251'));
    socket.listen((RawSocketEvent event) {
      if (event != RawSocketEvent.read) return;
      final Datagram? datagram = socket.receive();
      if (datagram != null) _answerBillaresMdns(socket, datagram);
    });
    try {
      await const MethodChannel('billaresdonmiguel/network').invokeMethod<void>('acquireMulticastLock');
    } catch (_) {}
  } catch (_) {}
}
'''

source = TARGET.read_text()
source = replace_function(source, '_answerBillaresMdns', answer)
source = replace_function(source, '_startBillaresMdns', start_mdns)
TARGET.write_text(source)
print('OK: mDNS 1.2.6 corregido con paquete DNS válido y multicast lock')
