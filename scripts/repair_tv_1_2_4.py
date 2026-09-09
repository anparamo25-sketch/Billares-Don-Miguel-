from pathlib import Path
import json
import re

TARGET = Path('lib/main.dart')


def find_matching_brace(source: str, open_pos: int) -> int:
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
                continue
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
        if source[i] in ("'", '"'):
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
    raise SystemExit('TV REPAIR FAILED: llaves sin cerrar')


def remove_async_functions(source: str, names: tuple[str, ...]) -> str:
    pattern = re.compile(r'\bFuture\s*<\s*void\s*>\s+(' + '|'.join(map(re.escape, names)) + r')\s*\(\s*\)\s+async\s*\{')
    while True:
        m = pattern.search(source)
        if not m:
            return source
        open_pos = source.find('{', m.start(), m.end())
        end_pos = find_matching_brace(source, open_pos)
        source = source[:m.start()] + source[end_pos:]


def remove_tv_getters(source: str) -> str:
    arrow = re.compile(r'(?m)^\s*String\s+get\s+tvHtml(?:Legacy\d+)?\s*=>[^;]*;\s*')
    source = arrow.sub('', source)
    block = re.compile(r'\bString\s+get\s+tvHtml(?:Legacy\d+)?\s*\{')
    while True:
        m = block.search(source)
        if not m:
            return source
        open_pos = source.find('{', m.start(), m.end())
        end_pos = find_matching_brace(source, open_pos)
        source = source[:m.start()] + source[end_pos:]


def remove_fields(source: str) -> str:
    source = re.sub(r'(?m)^\s*HttpServer\?\s+server;\s*\n?', '', source)
    source = re.sub(r'(?m)^\s*String\?\s+lanIp;\s*\n?', '', source)
    return source


def insert_before(source: str, marker: str, text: str) -> str:
    pos = source.find(marker)
    if pos < 0:
        raise SystemExit(f'TV REPAIR FAILED: no se encontró marcador {marker}')
    return source[:pos] + text + source[pos:]


s = TARGET.read_text()
if "import 'dart:io';" not in s:
    imports = list(re.finditer(r'(?m)^import\s+[^\n]+\n', s))
    pos = imports[-1].end() if imports else 0
    s = s[:pos] + "import 'dart:io';\n" + s[pos:]

s = remove_async_functions(s, ('showTvConnection', 'showTvConnectionLegacy1', 'showTvConnectionLegacy2', 'showTvConnectionLegacy3', 'startLanServer'))
s = remove_tv_getters(s)
s = remove_fields(s)

MDNS = '''
RawDatagramSocket? _billaresMdnsSocket;

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
    response.addAll(<int>[0x84, 0, 0, 0, 0, 1, 0, 0, 0, 120, 0, 4]);
    response.addAll(query.sublist(12, offset));
    response.addAll(<int>[0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, 120, 0, 4]);
    response.addAll(parts);
    socket.send(response, datagram.address, datagram.port);
  } catch (_) {}
}
'''

s = insert_before(s, r"" if False else 'class ', '') if False else s
# Top-level mDNS is inserted before the first class declaration. This avoids any
# dependency on generated class names while keeping all LAN structure in this
# single canonical TV producer.
class_pos = re.search(r'\bclass\s+[A-Za-z_][A-Za-z0-9_]*', s)
if not class_pos:
    raise SystemExit('TV REPAIR FAILED: no se encontró ninguna clase Dart')
s = s[:class_pos.start()] + MDNS + '\n' + s[class_pos.start():]

SERVER = '''  HttpServer? server;
  String? lanIp;

  Future<void> startLanServer() async {
    try {
      server = await HttpServer.bind(InternetAddress.anyIPv4, 80, shared: true);
      final List<NetworkInterface> interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);
      for (final NetworkInterface networkInterface in interfaces) {
        for (final InternetAddress address in networkInterface.addresses) {
          final List<String> octets = address.address.split('.');
          if (octets.length == 4 && !address.isLoopback && !address.isLinkLocal && !address.isMulticast) {
            final int first = int.tryParse(octets[0]) ?? 0;
            final int second = int.tryParse(octets[1]) ?? 0;
            if (first == 10 || (first == 172 && second >= 16 && second <= 31) || (first == 192 && second == 168)) lanIp = address.address;
          }
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

SHOW = '''  Future<void> showTvConnection() async {
    const String url = 'http://billaresdonmiguel.local/tv';
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: const Text('Receptor exclusivo para TV'),
        content: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
            const Text('La TV mostrará solamente las mesas. El celular seguirá funcionando como administrador.'),
            const SizedBox(height: 14),
            const Text('Dirección:', style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            const SelectableText(url, style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            FilledButton.icon(onPressed: () async {
              await Clipboard.setData(const ClipboardData(text: url));
              if (dialogContext.mounted) ScaffoldMessenger.of(dialogContext).showSnackBar(const SnackBar(content: Text('Dirección copiada')));
            }, icon: const Icon(Icons.copy), label: const Text('Copiar dirección')),
            const SizedBox(height: 8),
            const Text('En la TV abre el navegador, escribe la dirección y presiona Enter. No uses Duplicar pantalla/Miracast.', style: TextStyle(fontSize: 12)),
          ]),
        ),
        actions: <Widget>[TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cerrar'))],
      ),
    );
  }
'''

html = '''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Billares Don Miguel - TV</title><style>*{box-sizing:border-box}body{margin:0;background:#05070b;color:#fff;font-family:Arial,sans-serif}header{padding:18px;text-align:center;background:#fff;border-bottom:3px solid #1557c0}h1{margin:0;font-size:clamp(28px,4vw,46px);color:#1557c0;text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff}.clock{margin-top:6px;font-size:clamp(18px,2vw,26px);font-weight:700;color:#123f91}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px;padding:22px;max-width:1800px;margin:auto}.card{border-radius:18px;padding:22px;background:#111827;border:3px solid #64748b;min-height:205px}.green{background:#103b22;border-color:#22c55e}.red{background:#511b1b;border-color:#ef4444}.yellow{background:#56490a;border-color:#eab308}.name{font-size:clamp(25px,3vw,38px);font-weight:900}.status{margin:10px 0;font-size:clamp(18px,2vw,25px);font-weight:800}.line{margin:8px 0;font-size:clamp(15px,1.6vw,20px)}.money{margin-top:14px;font-size:clamp(25px,2.7vw,36px);font-weight:900}.offline{position:fixed;right:12px;bottom:10px;background:#7f1d1d;padding:7px 12px;border-radius:10px;display:none}</style></head><body><header><h1>Billares Don Miguel</h1><div id="clock" class="clock">Conectando...</div></header><main id="grid" class="grid"></main><div id="offline" class="offline">Sin conexión con CENTRAL</div><script>function money(n){return 'C&#36; '+Number(n||0).toFixed(2)}function render(d){document.getElementById('clock').textContent=d.time||'--:--:--';document.getElementById('grid').innerHTML=(d.tables||[]).map(function(t){var c=t.status==='Disponible'?'green':t.status==='En juego'?'red':'yellow';return '<section class="card '+c+'"><div class="name">Mesa '+t.number+'</div><div class="status">'+t.status+'</div><div class="line">Inicio: '+(t.start||'—')+'</div><div class="line">Finalización: '+(t.end||'—')+'</div><div class="line">Tiempo jugado: '+(t.elapsed||'00:00:00')+'</div><div class="money">'+money(t.amount)+'</div></section>'}).join('')}async function tick(){try{var r=await fetch('/api/state?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error();render(await r.json());document.getElementById('offline').style.display='none'}catch(e){document.getElementById('offline').style.display='block'}}tick();setInterval(tick,1000);</script></body></html>'''

# All class members are inserted immediately before stateMap(), which is a
# structural member marker, not a generated class-name dependency.
canonical = SERVER + SHOW + '\n  String get tvHtml => ' + json.dumps(html, ensure_ascii=False) + ';\n\n'
s = insert_before(s, '  Map<String, dynamic> stateMap()', canonical)

if len(re.findall(r'\bFuture\s*<\s*void\s*>\s+showTvConnection\s*\(\s*\)\s+async\b', s)) != 1:
    raise SystemExit('TV REPAIR FAILED: showTvConnection no quedó exactamente una vez')
if len(re.findall(r'(?m)^\s*String\s+get\s+tvHtml\s*=>', s)) != 1:
    raise SystemExit('TV REPAIR FAILED: tvHtml no quedó exactamente una vez')
if len(re.findall(r'\bFuture\s*<\s*void\s*>\s+startLanServer\s*\(\s*\)\s+async\b', s)) != 1:
    raise SystemExit('TV REPAIR FAILED: startLanServer no quedó exactamente una vez')
if s.count('RawDatagramSocket? _billaresMdnsSocket;') != 1:
    raise SystemExit('TV REPAIR FAILED: estructura mDNS inválida')
if s.count('await _startBillaresMdns();') != 1:
    raise SystemExit('TV REPAIR FAILED: arranque mDNS inválido')
if 'HttpServer.bind(InternetAddress.anyIPv4, 80' not in re.sub(r'\s+', ' ', s):
    raise SystemExit('TV REPAIR FAILED: servidor LAN no quedó en puerto 80')
if 'http://billaresdonmiguel.local/tv' not in s:
    raise SystemExit('TV REPAIR FAILED: hostname TV ausente')
if '\\nFuture<void> _startBillaresMdns()' in s:
    raise SystemExit('TV REPAIR FAILED: saltos de línea literales detectados')

TARGET.write_text(s)
print('OK: TV, servidor LAN y mDNS reconstruidos como una única estructura canónica; sin parches de texto sobre HTML')
