from pathlib import Path
import json
import re

TARGET = Path('lib/main.dart')

# PRODUCTOR CANÓNICO ÚNICO.
# Reconstruye estructuralmente el bloque LAN/TV/mDNS una sola vez.


def matching_brace(source: str, open_pos: int) -> int:
    depth = 0
    quote = None
    triple = False
    i = open_pos
    while i < len(source):
        if quote:
            token = quote * 3 if triple else quote
            if source.startswith(token, i):
                i += len(token); quote = None; triple = False; continue
            if source[i] == '\\' and not triple: i += 2
            else: i += 1
            continue
        if source.startswith("'''", i) or source.startswith('"""', i):
            quote = source[i]; triple = True; i += 3; continue
        if source[i] in "'\"": quote = source[i]; triple = False; i += 1; continue
        if source.startswith('//', i):
            e = source.find('\n', i + 2); i = len(source) if e < 0 else e + 1; continue
        if source.startswith('/*', i):
            e = source.find('*/', i + 2); i = len(source) if e < 0 else e + 2; continue
        if source[i] == '{': depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0: return i + 1
        i += 1
    raise SystemExit('TV REBUILD FAILED: llaves sin cerrar')


def remove_function(source: str, name: str) -> str:
    pattern = re.compile(rf'\bFuture\s*<\s*void\s*>\s+{re.escape(name)}\s*\(\s*\)\s+async\s*\{{')
    while True:
        m = pattern.search(source)
        if not m: return source
        end = matching_brace(source, source.find('{', m.start(), m.end()))
        source = source[:m.start()] + source[end:]


def remove_tv_getters(source: str) -> str:
    source = re.sub(r'(?m)^\s*String\s+get\s+tvHtml(?:Legacy\d+)?\s*=>.*?;\s*\n?', '', source)
    pattern = re.compile(r'\bString\s+get\s+tvHtml(?:Legacy\d+)?\s*\{')
    while True:
        m = pattern.search(source)
        if not m: return source
        end = matching_brace(source, source.find('{', m.start(), m.end()))
        source = source[:m.start()] + source[end:]


def remove_field(source: str, type_name: str, field_name: str) -> str:
    return re.sub(rf'(?m)^\s*{re.escape(type_name)}\s+{re.escape(field_name)}\s*;\s*\n?', '', source)


def class_containing(source: str, marker: str):
    pos = source.find(marker)
    if pos < 0: raise SystemExit(f'TV REBUILD FAILED: no se encontró {marker}')
    matches = list(re.finditer(r'\bclass\s+[A-Za-z_][A-Za-z0-9_]*[^\{]*\{', source[:pos + 1]))
    if not matches: raise SystemExit('TV REBUILD FAILED: no se encontró una clase Dart')
    m = matches[-1]
    return m.start(), matching_brace(source, source.find('{', m.start(), m.end()))


source = TARGET.read_text()
if "import 'dart:io';" not in source:
    imports = list(re.finditer(r'(?m)^import\s+[^\n]+\n', source))
    insert = imports[-1].end() if imports else 0
    source = source[:insert] + "import 'dart:io';\n" + source[insert:]

for fn in ('showTvConnection', 'showTvConnectionLegacy1', 'showTvConnectionLegacy2', 'showTvConnectionLegacy3', 'startLanServer'):
    source = remove_function(source, fn)
source = remove_tv_getters(source)
source = remove_field(source, 'HttpServer?', 'server')
source = remove_field(source, 'String?', 'lanIp')

mdns = '''\nRawDatagramSocket? _billaresMdnsSocket;\n\nFuture<void> _startBillaresMdns() async {\n  try {\n    _billaresMdnsSocket?.close();\n    final RawDatagramSocket socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 5353, reuseAddress: true, reusePort: true);\n    _billaresMdnsSocket = socket;\n    socket.joinMulticast(InternetAddress('224.0.0.251'));\n    socket.listen((RawSocketEvent event) {\n      if (event != RawSocketEvent.read) return;\n      final Datagram? datagram = socket.receive();\n      if (datagram != null) _answerBillaresMdns(socket, datagram);\n    });\n  } catch (_) {}\n}\n\nFuture<String?> _billaresLocalIp() async {\n  try {\n    final List<NetworkInterface> interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);\n    for (final NetworkInterface networkInterface in interfaces) {\n      for (final InternetAddress address in networkInterface.addresses) {\n        if (!address.isLoopback && !address.isLinkLocal && !address.isMulticast) return address.address;\n      }\n    }\n  } catch (_) {}\n  return null;\n}\n\nFuture<void> _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram) async {\n  try {\n    final List<int> query = datagram.data;\n    if (query.length < 12) return;\n    final int questions = (query[4] << 8) | query[5];\n    int offset = 12;\n    bool matches = false;\n    for (int i = 0; i < questions; i++) {\n      final List<String> labels = <String>[];\n      while (offset < query.length) {\n        final int length = query[offset++];\n        if (length == 0) break;\n        if (length > 63 || offset + length > query.length) return;\n        labels.add(String.fromCharCodes(query.sublist(offset, offset + length)));\n        offset += length;\n      }\n      if (offset + 4 > query.length) return;\n      final int type = (query[offset] << 8) | query[offset + 1];\n      offset += 4;\n      if (labels.join('.').toLowerCase() == 'billaresdonmiguel.local' && (type == 1 || type == 255)) matches = true;\n    }\n    if (!matches) return;\n    final String? ip = await _billaresLocalIp();\n    if (ip == null) return;\n    final List<int> parts = ip.split('.').map(int.parse).toList();\n    if (parts.length != 4) return;\n    final List<int> response = <int>[];\n    response.addAll(query.sublist(0, 2));\n    response.addAll(<int>[0x84, 0, 0, 0, 0, 1, 0, 0, 0, 120, 0, 4]);\n    response.addAll(query.sublist(12, offset));\n    response.addAll(<int>[0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, 120, 0, 4]);\n    response.addAll(parts);\n    socket.send(response, datagram.address, datagram.port);\n  } catch (_) {}\n}\n'''
first_class = re.search(r'\bclass\s+[A-Za-z_][A-Za-z0-9_]*', source)
if not first_class: raise SystemExit('TV REBUILD FAILED: no se encontró ninguna clase Dart')
source = source[:first_class.start()] + mdns + '\n' + source[first_class.start():]

server_block = '''  HttpServer? server;\n  String? lanIp;\n\n  Future<void> startLanServer() async {\n    try {\n      server = await HttpServer.bind(InternetAddress.anyIPv4, 80, shared: true);\n      final List<NetworkInterface> interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);\n      final List<String> candidates = <String>[];\n      for (final NetworkInterface networkInterface in interfaces) {\n        final String name = networkInterface.name.toLowerCase();\n        for (final InternetAddress address in networkInterface.addresses) {\n          final List<int> parts = address.address.split('.').map(int.tryParse).whereType<int>().toList();\n          final bool privateIpv4 = parts.length == 4 && (parts[0] == 10 || (parts[0] == 172 && parts[1] >= 16 && parts[1] <= 31) || (parts[0] == 192 && parts[1] == 168));\n          if (!address.isLoopback && !address.isMulticast && !address.isLinkLocal && privateIpv4) {\n            final int priority = name.contains('wlan') || name.contains('wifi') ? 0 : name.contains('eth') ? 1 : 2;\n            candidates.add('$priority|${address.address}');\n          }\n        }\n      }\n      candidates.sort();\n      if (candidates.isNotEmpty) lanIp = candidates.first.split('|').last;\n      server!.listen(handleRequest, onError: (_) {});\n      await _startBillaresMdns();\n      if (mounted) setState(() {});\n    } catch (_) {\n      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo iniciar el servidor LAN en el puerto 80')));\n    }\n  }\n\n  Future<void> handleRequest(HttpRequest request) async {\n    final HttpResponse response = request.response;\n    response.headers.set('Access-Control-Allow-Origin', '*');\n    response.headers.set('Access-Control-Allow-Methods', 'GET, OPTIONS');\n    response.headers.set('Access-Control-Allow-Headers', 'Content-Type, Cache-Control');\n    response.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');\n    response.headers.set('Pragma', 'no-cache');\n    if (request.method == 'OPTIONS') {\n      response.statusCode = HttpStatus.noContent;\n      await response.close();\n      return;\n    }\n    if (request.uri.path == '/health') {\n      response.headers.contentType = ContentType.json;\n      response.write(jsonEncode(<String, dynamic>{'ok': true, 'app': 'Billares Don Miguel', 'version': appVersion}));\n    } else if (request.uri.path == '/api/state') {\n      response.headers.contentType = ContentType.json;\n      response.write(jsonEncode(stateMap()));\n    } else if (request.uri.path == '/tv' || request.uri.path == '/') {\n      response.headers.contentType = ContentType.html;\n      response.write(tvHtml);\n    } else {\n      response.statusCode = HttpStatus.notFound;\n      response.write('Not found');\n    }\n    await response.close();\n  }\n\n'''
show_block = '''  Future<void> showTvConnection() async {\n    const String url = 'http://billaresdonmiguel.local/tv';\n    if (!mounted) return;\n    await showDialog<void>(\n      context: context,\n      builder: (BuildContext dialogContext) => AlertDialog(\n        title: const Text('Pantalla exclusiva para TV'),\n        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[\n          const Text('La TV mostrará solamente las mesas. El celular seguirá funcionando como administrador.'),\n          const SizedBox(height: 14),\n          const Text('Dirección:', style: TextStyle(fontWeight: FontWeight.bold)),\n          const SizedBox(height: 6),\n          const SelectableText(url, style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),\n          const SizedBox(height: 10),\n          FilledButton.icon(onPressed: () async {\n            await Clipboard.setData(const ClipboardData(text: url));\n            if (dialogContext.mounted) ScaffoldMessenger.of(dialogContext).showSnackBar(const SnackBar(content: Text('Dirección copiada')));\n          }, icon: const Icon(Icons.copy), label: const Text('Copiar dirección')),\n          const SizedBox(height: 8),\n          const Text('En la TV abre el navegador, escribe la dirección y presiona Enter. No uses Duplicar pantalla/Miracast.', style: TextStyle(fontSize: 12)),\n        ])),\n        actions: <Widget>[TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cerrar'))],\n      ),\n    );\n  }\n\n'''
html = '''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Billares Don Miguel - TV</title><style>*{box-sizing:border-box}body{margin:0;background:#05070b;color:#fff;font-family:Arial,sans-serif}header{padding:18px;text-align:center;background:#fff;border-bottom:3px solid #1557c0}h1{margin:0;font-size:clamp(28px,4vw,46px);color:#1557c0;text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff}.clock{margin-top:6px;font-size:clamp(18px,2vw,26px);font-weight:700;color:#123f91}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px;padding:22px;max-width:1800px;margin:auto}.card{border-radius:18px;padding:22px;background:#111827;border:3px solid #64748b;min-height:205px}.green{background:#103b22;border-color:#22c55e}.red{background:#511b1b;border-color:#ef4444}.yellow{background:#56490a;border-color:#eab308}.name{font-size:clamp(25px,3vw,38px);font-weight:900}.status{margin:10px 0;font-size:clamp(18px,2vw,25px);font-weight:800}.line{margin:8px 0;font-size:clamp(15px,1.6vw,20px)}.money{margin-top:14px;font-size:clamp(25px,2.7vw,36px);font-weight:900}.offline{position:fixed;right:12px;bottom:10px;background:#7f1d1d;padding:7px 12px;border-radius:10px;display:none}</style></head><body><header><h1>Billares Don Miguel</h1><div id="clock" class="clock">Conectando...</div></header><main id="grid" class="grid"></main><div id="offline" class="offline">Sin conexión con CENTRAL</div><script>function money(n){return 'C&#36; '+Number(n||0).toFixed(2)}function render(d){document.getElementById('clock').textContent=d.time||'--:--:--';document.getElementById('grid').innerHTML=(d.tables||[]).map(function(t){var c=t.status==='Disponible'?'green':t.status==='En juego'?'red':'yellow';return '<section class="card '+c+'"><div class="name">Mesa '+t.number+'</div><div class="status">'+t.status+'</div><div class="line">Inicio: '+(t.start||'—')+'</div><div class="line">Finalización: '+(t.end||'—')+'</div><div class="line">Tiempo jugado: '+(t.elapsed||'00:00:00')+'</div><div class="money">'+money(t.amount)+'</div></section>'}).join('')}async function tick(){try{var r=await fetch('/api/state?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error();render(await r.json());document.getElementById('offline').style.display='none'}catch(e){document.getElementById('offline').style.display='block'}}tick();setInterval(tick,1000);</script></body></html>'''

a, b = class_containing(source, 'Map<String, dynamic> stateMap()')
class_body = source[a:b]
class_body = server_block + show_block + '  String get tvHtml => ' + json.dumps(html, ensure_ascii=False) + ';\n\n' + class_body
source = source[:a] + class_body + source[b:]

normalized = re.sub(r'\s+', ' ', source)
checks = (
    (len(re.findall(r'\bFuture\s*<\s*void\s*>\s+startLanServer\s*\(\s*\)\s+async\s*\{', source)) == 1, 'startLanServer'),
    (len(re.findall(r'\bFuture\s*<\s*void\s*>\s+showTvConnection\s*\(\s*\)\s+async\s*\{', source)) == 1, 'showTvConnection'),
    (len(re.findall(r'(?m)^\s*String\s+get\s+tvHtml\s*=>', source)) == 1, 'tvHtml'),
    (source.count('RawDatagramSocket? _billaresMdnsSocket;') == 1, 'mDNS'),
    (source.count('await _startBillaresMdns();') == 1, 'arranque mDNS'),
    ('HttpServer.bind(InternetAddress.anyIPv4, 80' in normalized, 'puerto 80'),
    ('http://billaresdonmiguel.local/tv' in source, 'hostname'),
    ('/api/state?ts=' in source, 'polling TV'),
)
for ok, name in checks:
    if not ok: raise SystemExit(f'TV REBUILD FAILED: {name}')

TARGET.write_text(source)
print('OK: TV/LAN/mDNS reconstruidos por un único productor estructural')
