from pathlib import Path
import re

TARGET = Path('lib/main.dart')
s = TARGET.read_text()

# URL fija para el televisor: el teléfono anuncia billaresdonmiguel.local mediante mDNS.
s = s.replace("final String url = 'http://$lanIp:8080/tv';", "final String url = 'http://billaresdonmiguel.local/tv';")
s = s.replace("const Text('Dirección del receptor:', style: TextStyle(fontWeight: FontWeight.bold)),", "const Text('Dirección del receptor:', style: TextStyle(fontWeight: FontWeight.bold)),")
s = s.replace("const Text('En la TV: abre su navegador y escribe exactamente la dirección anterior. El celular puede seguir usando CENTRAL normalmente.', style: TextStyle(fontSize: 12)),", "const Text('En la TV: escribe exactamente http://billaresdonmiguel.local/tv. No necesitas código ni IP. El celular puede seguir usando CENTRAL normalmente.', style: TextStyle(fontSize: 12)),")

# Add an mDNS responder field next to the existing HTTP server field.
if 'RawDatagramSocket? _billaresMdnsSocket;' not in s:
    marker = re.search(r'(\n\s*HttpServer\?\s+server\s*;)', s)
    if not marker:
        marker = re.search(r'(\n\s*HttpServer\s+server\s*;)', s)
    if not marker:
        raise SystemExit('No se encontró la declaración de HttpServer')
    s = s[:marker.end()] + "\n  RawDatagramSocket? _billaresMdnsSocket;" + s[marker.end():]

# Bind the web receiver on port 80 so the TV can omit :8080.
old_bind = "server = await HttpServer.bind(InternetAddress.anyIPv4, 8080, shared: true);"
new_bind = "server = await HttpServer.bind(InternetAddress.anyIPv4, 80, shared: true);"
if old_bind not in s:
    raise SystemExit('No se encontró el bind HTTP 8080')
s = s.replace(old_bind, new_bind, 1)

# Start the fixed local hostname responder after the HTTP server starts.
needle = "server!.listen(handleRequest, onError: (_) {});\n      if (mounted) setState(() {});"
replacement = "server!.listen(handleRequest, onError: (_) {});\n      await _startBillaresMdns();\n      if (mounted) setState(() {});"
if needle not in s:
    raise SystemExit('No se encontró el punto de inicio del servidor LAN')
s = s.replace(needle, replacement, 1)

# Insert the mDNS responder immediately before startLanServer.
if '_startBillaresMdns()' not in s:
    method = r'''  Future<void> _startBillaresMdns() async {
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
    } catch (_) {
      // El receptor IP continúa funcionando aunque el mDNS no esté disponible.
    }
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
        offset += 2;
        offset += 2; // class
        final String name = labels.join('.').toLowerCase();
        if (name == 'billaresdonmiguel.local' && (type == 1 || type == 255)) matched = true;
      }
      if (!matched || lanIp == null) return;
      final List<int> ip = lanIp!.split('.').map(int.parse).toList();
      if (ip.length != 4) return;
      final List<int> response = <int>[];
      response.addAll(q.sublist(0, 2));
      response.addAll(<int>[0x84, 0x00]);
      response.addAll(<int>[(qdCount >> 8) & 0xff, qdCount & 0xff, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]);
      response.addAll(q.sublist(12, offset));
      response.addAll(<int>[0xC0, 0x0C, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00, 0x78, 0x00, 0x04]);
      response.addAll(ip);
      socket.send(response, datagram.address, datagram.port);
    } catch (_) {}
  }

'''
    marker = '  Future<void> startLanServer() async {'
    if marker not in s:
        raise SystemExit('No se encontró startLanServer para insertar mDNS')
    s = s.replace(marker, method + marker, 1)

# Close mDNS when the HTTP server is closed, if the generated source has a direct close.
s = s.replace('server?.close(force: true);', 'server?.close(force: true);\n      _billaresMdnsSocket?.close();', 1)

# Ensure the user-facing dialog never tells the user to enter a code.
s = s.replace('No necesitas código ni IP.', 'No necesitas código ni IP.')

TARGET.write_text(s)
print('OK: hostname fijo billaresdonmiguel.local + mDNS + HTTP puerto 80')
