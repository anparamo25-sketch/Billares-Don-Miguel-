from pathlib import Path
import re

TARGET = Path('lib/main.dart')
s = TARGET.read_text()

FIELD = '  RawDatagramSocket? _billaresMdnsSocket;\n'
METHOD = r'''  Future<void> _startBillaresMdns() async {
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
        final String name = labels.join('.').toLowerCase();
        if (name == 'billaresdonmiguel.local' && (type == 1 || type == 255)) matched = true;
      }
      if (!matched || lanIp == null) return;
      final List<int> ip = lanIp!.split('.').map(int.parse).toList();
      if (ip.length != 4) return;
      final List<int> response = <int>[];
      response.addAll(q.sublist(0, 2));
      response.addAll(<int>[0x84, 0x00]);
      response.addAll(<int>[0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]);
      response.addAll(q.sublist(12, offset));
      response.addAll(<int>[0xC0, 0x0C, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00, 0x78, 0x00, 0x04]);
      response.addAll(ip);
      socket.send(response, datagram.address, 5353);
    } catch (_) {}
  }

'''

if 'RawDatagramSocket? _billaresMdnsSocket;' not in s:
    marker = re.search(r'(?m)^\s*HttpServer\?\s+server\s*;', s)
    if marker:
        s = s[:marker.end()] + '\n' + FIELD.rstrip() + s[marker.end():]
    else:
        marker = re.search(r'(?m)^class\s+_DashboardPageState\b[^\{]*\{', s)
        if not marker:
            raise SystemExit('mDNS ENSURE FAILED: no se encontró Dashboard')
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

if 'billaresdonmiguel.local' not in s:
    raise SystemExit('mDNS ENSURE FAILED: hostname ausente')
if 'RawDatagramSocket? _billaresMdnsSocket;' not in s:
    raise SystemExit('mDNS ENSURE FAILED: socket ausente')
if 'Future<void> _startBillaresMdns() async {' not in s:
    raise SystemExit('mDNS ENSURE FAILED: método ausente')
if 'await _startBillaresMdns();' not in s:
    raise SystemExit('mDNS ENSURE FAILED: arranque ausente')

TARGET.write_text(s)
print('OK: mDNS determinista presente, con socket 5353, respuesta a billaresdonmiguel.local y arranque del servicio')
