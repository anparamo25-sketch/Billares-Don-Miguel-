from pathlib import Path
import re

TARGET = Path('lib/main.dart')
s = TARGET.read_text()
FIELD = '  RawDatagramSocket? _billaresMdnsSocket;\n'
METHOD = r'''  Future<void> _startBillaresMdns() async {
    try {
      _billaresMdnsSocket?.close();
      final RawDatagramSocket socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 5353, reuseAddress: true, reusePort: true);
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
      response.addAll(<int>[0x84, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]);
      response.addAll(q.sublist(12, offset));
      response.addAll(<int>[0xC0, 0x0C, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00, 0x78, 0x00, 0x04]);
      response.addAll(ip);
      socket.send(response, datagram.address, 5353);
    } catch (_) {}
  }

'''

if FIELD not in s:
    marker = re.search(r'(?m)^\s*HttpServer\?\s+server\s*;', s)
    if marker:
        s = s[:marker.end()] + '\n' + FIELD.rstrip() + s[marker.end():]
    else:
        marker = re.search(r'(?m)^class\s+[^\n\{]+\{', s)
        if not marker:
            raise SystemExit('mDNS ENSURE FAILED: no se encontró una clase Dart donde insertar el socket')
        s = s[:marker.end()] + '\n' + FIELD + s[marker.end():]

if 'Future<void> _startBillaresMdns() async {' not in s:
    marker = '  Future<void> startLanServer() async {'
    if marker not in s:
        raise SystemExit('mDNS ENSURE FAILED: no se encontró startLanServer')
    s = s.replace(marker, METHOD + marker, 1)

if 'await _startBillaresMdns();' not in s:
    m = re.search(r'(?m)^\s*server!?\.listen\([^\n]*\);', s)
    if not m:
        raise SystemExit('mDNS ENSURE FAILED: no se encontró server.listen')
    s = s[:m.end()] + '\n      await _startBillaresMdns();' + s[m.end():]

for required in (FIELD.rstrip(), 'Future<void> _startBillaresMdns() async {', 'await _startBillaresMdns();', 'billaresdonmiguel.local'):
    if required not in s:
        raise SystemExit('mDNS ENSURE FAILED: componente ausente: ' + required)

TARGET.write_text(s)
print('OK: mDNS determinista presente sin depender del nombre de Dashboard')
