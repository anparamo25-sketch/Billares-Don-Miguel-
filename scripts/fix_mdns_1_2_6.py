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


def brace_end(source, start):
    depth = 0
    index = start
    while index < len(source):
        if source[index] in "'\"":
            index = skip_string(source, index)
            continue
        if source.startswith('//', index):
            end = source.find('\n', index + 2)
            index = len(source) if end < 0 else end + 1
            continue
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise SystemExit('MDNS 1.2.6 FAILED: llaves Dart sin cerrar')


def remove_top_level_function(source, name):
    pattern = re.compile(
        rf'(?m)^\s*(?:Future\s*<\s*[^>]+\s*>|void|String\??)\s+{re.escape(name)}\s*\([^)]*\)\s*(?:async\s*)?\{{'
    )
    while True:
        match = pattern.search(source)
        if not match:
            return source
        end = brace_end(source, source.find('{', match.start(), match.end()))
        source = source[:match.start()] + source[end:]


def remove_socket(source):
    return re.sub(
        r'(?m)^RawDatagramSocket\?\s+_billaresMdnsSocket\s*;\s*\n?',
        '',
        source,
    )


MDNS_SOURCE = r'''
RawDatagramSocket? _billaresMdnsSocket;
Future<String?> _billaresLocalIp() async {
  try {
    final interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);
    for (final network in interfaces) {
      for (final address in network.addresses) {
        final parts = address.address.split('.').map(int.tryParse).whereType<int>().toList();
        final privateIpv4 = parts.length == 4 && (parts[0] == 10 || (parts[0] == 172 && parts[1] >= 16 && parts[1] <= 31) || (parts[0] == 192 && parts[1] == 168));
        if (privateIpv4 && !address.isLoopback && !address.isLinkLocal && !address.isMulticast) return address.address;
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
    var offset = 12;
    var matched = false;
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
      if (labels.join('.').toLowerCase() == 'billaresdonmiguel.local' && (type == 1 || type == 255)) matched = true;
    }
    if (!matched) return;
    final String? ip = await _billaresLocalIp();
    if (ip == null) return;
    final List<int> octets = ip.split('.').map(int.parse).toList();
    if (octets.length != 4) return;

    final response = <int>[];
    response.addAll(query.sublist(0, 2));
    response.addAll(<int>[0x84, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]);
    response.addAll(<int>[0xC0, 0x0C]);
    response.addAll(<int>[0x00, 0x01, 0x00, 0x01]);
    response.addAll(<int>[0x00, 0x00, 0x00, 0x78]);
    response.addAll(<int>[0x00, 0x04]);
    response.addAll(octets);
    socket.send(response, InternetAddress('224.0.0.251'), 5353);
    if (datagram.address.address != '224.0.0.251' || datagram.port != 5353) {
      socket.send(response, datagram.address, datagram.port);
    }
  } catch (_) {}
}
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
    socket.broadcastEnabled = true;
    socket.joinMulticast(InternetAddress('224.0.0.251'));
    socket.listen((RawSocketEvent event) {
      if (event != RawSocketEvent.read) return;
      final Datagram? datagram = socket.receive();
      if (datagram != null) {
        _answerBillaresMdns(socket, datagram);
      }
    });
    try {
      await const MethodChannel('billaresdonmiguel/network').invokeMethod<void>('acquireMulticastLock');
    } catch (_) {}
  } catch (_) {}
}
'''

source = TARGET.read_text()
# Remove every generated copy, including Future<String?> _billaresLocalIp.
for function_name in ('_answerBillaresMdns', '_startBillaresMdns', '_billaresLocalIp'):
    source = remove_top_level_function(source, function_name)
source = remove_socket(source)

first_class = re.search(r'(?m)^class\s+[A-Za-z_][A-Za-z0-9_]*', source)
if not first_class:
    raise SystemExit('MDNS 1.2.6 FAILED: no se encontró una clase Dart donde insertar mDNS')

source = source[:first_class.start()] + MDNS_SOURCE.lstrip() + '\n' + source[first_class.start():]
TARGET.write_text(source)
print('OK: mDNS 1.2.6 corregido estructuralmente; local IP y funciones canónicas insertadas una sola vez')
