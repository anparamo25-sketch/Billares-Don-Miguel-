from pathlib import Path
import json
import re

TARGET = Path('lib/main.dart')


def matching_brace(source, open_pos):
    depth = 0
    quote = None
    triple = False
    i = open_pos
    while i < len(source):
        if quote:
            token = quote * 3 if triple else quote
            if source.startswith(token, i):
                i += len(token)
                quote = None
                triple = False
            elif source[i] == '\\' and not triple:
                i += 2
            else:
                i += 1
            continue
        if source.startswith("'''", i) or source.startswith('"""', i):
            quote = source[i]
            triple = True
            i += 3
            continue
        if source[i] in "'\"":
            quote = source[i]
            triple = False
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
    raise SystemExit('TV REBUILD FAILED: llaves sin cerrar')


def remove_method(source, name):
    pattern = re.compile(
        rf'(?m)^\s*(?:Future\s*<\s*void\s*>|void)\s+{re.escape(name)}\s*\([^)]*\)\s*(?:async\s*)?\{{'
    )
    while True:
        match = pattern.search(source)
        if not match:
            return source
        brace = source.find('{', match.start(), match.end())
        end = matching_brace(source, brace)
        source = source[:match.start()] + source[end:]


def remove_getter(source):
    pattern = re.compile(r'(?m)^\s*String\s+get\s+tvHtml(?:Legacy\d+)?\s*\{')
    while True:
        match = pattern.search(source)
        if not match:
            break
        end = matching_brace(source, source.find('{', match.start(), match.end()))
        source = source[:match.start()] + source[end:]
    return re.sub(r'(?m)^\s*String\s+get\s+tvHtml(?:Legacy\d+)?\s*=>.*?;\s*\n?', '', source)


def remove_field(source, declaration):
    return re.sub(rf'(?m)^\s*{re.escape(declaration)}\s*;\s*\n?', '', source)


def class_containing_state_map(source):
    marker = re.search(r'\bMap\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap\s*\(\s*\)', source)
    if not marker:
        raise SystemExit('TV REBUILD FAILED: stateMap ausente')
    declarations = list(re.finditer(r'\bclass\s+[A-Za-z_][A-Za-z0-9_]*[^\{]*\{', source[:marker.start()]))
    for declaration in reversed(declarations):
        brace = source.find('{', declaration.start(), declaration.end())
        end = matching_brace(source, brace)
        if end > marker.start():
            return declaration.start(), end
    raise SystemExit('TV REBUILD FAILED: clase que contiene stateMap ausente')


def add_import(source, statement):
    if re.search(rf'(?m)^import\s+[\'\"]{re.escape(statement.split("'")[1] if "'" in statement else statement.split("\"")[1])}[\'\"];\s*$', source):
        return source
    imports = list(re.finditer(r'(?m)^import\s+[^\n]+\n', source))
    pos = imports[-1].end() if imports else 0
    return source[:pos] + statement + '\n' + source[pos:]


source = TARGET.read_text()
source = add_import(source, "import 'dart:io';")
source = add_import(source, "import 'dart:convert';")
source = add_import(source, "import 'package:flutter/services.dart';")

# Reconstrucción estructural: se conserva handleRequest y todo el resto de la lógica.
for method in ('showTvConnection', 'showTvConnectionLegacy1', 'showTvConnectionLegacy2', 'showTvConnectionLegacy3', 'startLanServer'):
    source = remove_method(source, method)
source = remove_getter(source)
source = remove_field(source, 'HttpServer? server')
source = remove_field(source, 'String? lanIp')

mdns = """\nRawDatagramSocket? _billaresMdnsSocket;\n\nFuture<void> _startBillaresMdns() async {\n  try {\n    _billaresMdnsSocket?.close();\n    final RawDatagramSocket socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 5353, reuseAddress: true, reusePort: true);\n    _billaresMdnsSocket = socket;\n    socket.joinMulticast(InternetAddress('224.0.0.251'));\n    socket.listen((RawSocketEvent event) {\n      if (event != RawSocketEvent.read) return;\n      final Datagram? datagram = socket.receive();\n      if (datagram != null) _answerBillaresMdns(socket, datagram);\n    });\n  } catch (_) {}\n}\n\nFuture<String?> _billaresLocalIp() async {\n  try {\n    final List<NetworkInterface> interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);\n    for (final NetworkInterface networkInterface in interfaces) {\n      for (final InternetAddress address in networkInterface.addresses) {\n        final List<int> p = address.address.split('.').map(int.tryParse).whereType<int>().toList();\n        final bool privateIpv4 = p.length == 4 && (p[0] == 10 || (p[0] == 172 && p[1] >= 16 && p[1] <= 31) || (p[0] == 192 && p[1] == 168));\n        if (!address.isLoopback && !address.isLinkLocal && !address.isMulticast && privateIpv4) return address.address;\n      }\n    }\n  } catch (_) {}\n  return null;\n}\n\nFuture<void> _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram) async {\n  try {\n    final List<int> query = datagram.data;\n    if (query.length < 12) return;\n    final int questions = (query[4] << 8) | query[5];\n    int offset = 12;\n    bool match = false;\n    for (int q = 0; q < questions; q++) {\n      final List<String> labels = <String>[];\n      while (offset < query.length) {\n        final int length = query[offset++];\n        if (length == 0) break;\n        if (length > 63 || offset + length > query.length) return;\n        labels.add(String.fromCharCodes(query.sublist(offset, offset + length)));\n        offset += length;\n      }\n      if (offset + 4 > query.length) return;\n      final int type = (query[offset] << 8) | query[offset + 1];\n      offset += 4;\n      if (labels.join('.').toLowerCase() == 'billaresdonmiguel.local' && (type == 1 || type == 255)) match = true;\n    }\n    if (!match) return;\n    final String? ip = await _billaresLocalIp();\n    if (ip == null) return;\n    final List<int> octets = ip.split('.').map(int.parse).toList();\n    if (octets.length != 4) return;\n    final List<int> response = <int>[];\n    response.addAll(query.sublist(0, 2));\n    response.addAll(<int>[0x84, 0, 0, 0, 0, 1, 0, 0, 0, 120, 0, 4]);\n    response.addAll(query.sublist(12, offset));\n    response.addAll(<int>[0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, 120, 0, 4]);\n    response.addAll(octets);\n    socket.send(response, datagram.address, datagram.port);\n  } catch (_) {}\n}\n"""
first_class = re.search(r'\bclass\s+[A-Za-z_][A-Za-z0-9_]*', source)
if not first_class:
    raise SystemExit('TV REBUILD FAILED: ninguna clase Dart encontrada')
source = source[:first_class.start()] + mdns + '\n' + source[first_class.start():]

server_members = """  HttpServer? server;\n  String? lanIp;\n\n  Future<void> startLanServer() async {\n    try {\n      server = await HttpServer.bind(InternetAddress.anyIPv4, 80, shared: true);\n      lanIp = await _billaresLocalIp();\n      server!.listen(handleRequest, onError: (_) {});\n      await _startBillaresMdns();\n      if (mounted) setState(() {});\n    } catch (_) {\n      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo iniciar el servidor LAN en el puerto 80')));\n    }\n  }\n\n  Future<void> showTvConnection() async {\n    const String url = 'http://billaresdonmiguel.local/tv';\n    if (!mounted) return;\n    await showDialog<void>(\n      context: context,\n      builder: (BuildContext dialogContext) => AlertDialog(\n        title: const Text('Pantalla exclusiva para TV'),\n        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[\n          const Text('La TV mostrará solamente las mesas. El celular seguirá funcionando como administrador.'),\n          const SizedBox(height: 12),\n          const SelectableText(url, style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),\n          const SizedBox(height: 8),\n          FilledButton.icon(onPressed: () async {\n            await Clipboard.setData(const ClipboardData(text: url));\n            if (dialogContext.mounted) ScaffoldMessenger.of(dialogContext).showSnackBar(const SnackBar(content: Text('Dirección copiada')));\n          }, icon: const Icon(Icons.copy), label: const Text('Copiar dirección')),\n          const SizedBox(height: 8),\n          const Text('En la TV abre el navegador y escribe la dirección. No uses Duplicar pantalla/Miracast.', style: TextStyle(fontSize: 12)),\n        ])),\n        actions: <Widget>[TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cerrar'))],\n      ),\n    );\n  }\n\n"""
start, end = class_containing_state_map(source)
class_source = source[start:end]
state_pos = re.search(r'(?m)^\s*Map\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap\s*\(\s*\)', class_source)
if not state_pos:
    raise SystemExit('TV REBUILD FAILED: stateMap no quedó dentro de su clase')
insert_at = state_pos.start()
class_source = class_source[:insert_at] + server_members + class_source[insert_at:]

html_parts = [
    '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Billares Don Miguel - TV</title>',
    '<style>*{box-sizing:border-box}body{margin:0;background:#05070b;color:#fff;font-family:Arial,sans-serif}header{padding:18px;text-align:center;background:#fff;border-bottom:3px solid #1557c0}h1{margin:0;font-size:clamp(28px,4vw,46px);color:#1557c0;text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff}.clock{margin-top:6px;font-size:clamp(18px,2vw,26px);font-weight:700;color:#123f91}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px;padding:22px;max-width:1800px;margin:auto}.card{border-radius:18px;padding:22px;background:#111827;border:3px solid #64748b;min-height:205px}.green{background:#103b22;border-color:#22c55e}.red{background:#511b1b;border-color:#ef4444}.yellow{background:#56490a;border-color:#eab308}.name{font-size:clamp(25px,3vw,38px);font-weight:900}.status{margin:10px 0;font-size:clamp(18px,2vw,25px);font-weight:800}.line{margin:8px 0;font-size:clamp(15px,1.6vw,20px)}.money{margin-top:14px;font-size:clamp(25px,2.7vw,36px);font-weight:900}.offline{position:fixed;right:12px;bottom:10px;background:#7f1d1d;padding:7px 12px;border-radius:10px;display:none}</style></head>',
    '<body><header><h1>Billares Don Miguel</h1><div id="clock" class="clock">Conectando...</div></header><main id="grid" class="grid"></main><div id="offline" class="offline">Sin conexión con CENTRAL</div>',
    '<script>function money(n){return \'C&#36; \'+Number(n||0).toFixed(2)}function render(d){document.getElementById(\'clock\').textContent=d.time||\'--:--:--\';document.getElementById(\'grid\').innerHTML=(d.tables||[]).map(function(t){var c=t.status===\'Disponible\'?\'green\':t.status===\'En juego\'?\'red\':\'yellow\';return \'<section class="card \'+c+\'"><div class="name">Mesa \'+t.number+\'</div><div class="status">\'+t.status+\'</div><div class="line">Inicio: \'+(t.start||\'—\')+\'</div><div class="line">Finalización: \'+(t.end||\'—\')+\'</div><div class="line">Tiempo jugado: \'+(t.elapsed||\'00:00:00\')+\'</div><div class="money">\'+money(t.amount)+\'</div></section>\'}).join(\'\')}async function tick(){try{var r=await fetch(\'/api/state?ts=\'+Date.now(),{cache:\'no-store\'});if(!r.ok)throw new Error();render(await r.json());document.getElementById(\'offline\').style.display=\'none\'}catch(e){document.getElementById(\'offline\').style.display=\'block\'}}tick();setInterval(tick,1000);</script>',
    '</body></html>'
]
html = ''.join(html_parts)
getter = '  String get tvHtml => ' + json.dumps(html, ensure_ascii=False, separators=(',', ':')) + ';\n\n'
class_source = class_source[:insert_at] + getter + class_source[insert_at:]
source = source[:start] + class_source + source[end:]

# Validación del productor antes de entregar el archivo generado.
if len(re.findall(r'(?m)^\s*String\s+get\s+tvHtml\s*=>', source)) != 1:
    raise SystemExit('TV REBUILD FAILED: tvHtml')
if len(re.findall(r'\bFuture\s*<\s*void\s*>\s+startLanServer\s*\(\s*\)\s+async\s*\{', source)) != 1:
    raise SystemExit('TV REBUILD FAILED: startLanServer')
if len(re.findall(r'\bFuture\s*<\s*void\s*>\s+showTvConnection\s*\(\s*\)\s+async\s*\{', source)) != 1:
    raise SystemExit('TV REBUILD FAILED: showTvConnection')
if source.count('RawDatagramSocket? _billaresMdnsSocket;') != 1:
    raise SystemExit('TV REBUILD FAILED: mDNS')
if source.count('await _startBillaresMdns();') != 1:
    raise SystemExit('TV REBUILD FAILED: arranque mDNS')
if 'HttpServer.bind(InternetAddress.anyIPv4, 80' not in re.sub(r'\s+', ' ', source):
    raise SystemExit('TV REBUILD FAILED: puerto 80')
if 'http://billaresdonmiguel.local/tv' not in source:
    raise SystemExit('TV REBUILD FAILED: hostname TV')
if '/api/state?ts=' not in source:
    raise SystemExit('TV REBUILD FAILED: polling TV')
if 'Billares Don Miguel' not in source:
    raise SystemExit('TV REBUILD FAILED: título TV')
if 'handleRequest' not in source:
    raise SystemExit('TV REBUILD FAILED: handleRequest original ausente')

TARGET.write_text(source)
print('OK: productor canónico TV/LAN/mDNS reconstruido y validado estructuralmente')
