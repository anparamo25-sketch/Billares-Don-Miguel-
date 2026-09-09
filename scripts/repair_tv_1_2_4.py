from pathlib import Path
import json
import re

TARGET = Path('lib/main.dart')


def skip_string_or_comment(source, i):
    if source.startswith("'''", i) or source.startswith('"""', i):
        q = source[i]
        end = source.find(q * 3, i + 3)
        if end < 0:
            raise SystemExit('TV REBUILD FAILED: bloque de texto sin cerrar')
        return end + 3
    if source[i] in "'\"":
        q = source[i]
        i += 1
        while i < len(source):
            if source[i] == '\\':
                i += 2
            elif source[i] == q:
                return i + 1
            else:
                i += 1
        raise SystemExit('TV REBUILD FAILED: cadena sin cerrar')
    if source.startswith('//', i):
        end = source.find('\n', i + 2)
        return len(source) if end < 0 else end + 1
    if source.startswith('/*', i):
        end = source.find('*/', i + 2)
        if end < 0:
            raise SystemExit('TV REBUILD FAILED: comentario sin cerrar')
        return end + 2
    return i + 1


def matching_brace(source, open_pos):
    depth = 0
    i = open_pos
    while i < len(source):
        if source[i] in "'\"" or source.startswith('//', i) or source.startswith('/*', i):
            i = skip_string_or_comment(source, i)
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
    pattern = re.compile(rf'(?m)^\s*(?:Future\s*<\s*void\s*>|void)\s+{re.escape(name)}\s*\([^;]*?\)\s*(?:async\s*)?\{{')
    while True:
        m = pattern.search(source)
        if not m:
            return source
        brace = source.find('{', m.start(), m.end())
        source = source[:m.start()] + source[matching_brace(source, brace):]


def remove_getter(source, name):
    block = re.compile(rf'(?m)^\s*String\s+get\s+{re.escape(name)}\s*\{{')
    expr = re.compile(rf'(?m)^\s*String\s+get\s+{re.escape(name)}\s*=>[^;]*;\s*\n?')
    while True:
        m = block.search(source)
        if not m:
            break
        brace = source.find('{', m.start(), m.end())
        source = source[:m.start()] + source[matching_brace(source, brace):]
    return expr.sub('', source)


def remove_field(source, declaration):
    return re.sub(rf'(?m)^\s*{re.escape(declaration)}\s*;\s*\n?', '', source)


def class_span_containing(source, marker_pos):
    classes = list(re.finditer(r'\bclass\s+[A-Za-z_][A-Za-z0-9_]*[^\{]*\{', source[:marker_pos]))
    for m in reversed(classes):
        brace = source.find('{', m.start(), m.end())
        end = matching_brace(source, brace)
        if end > marker_pos:
            return m.start(), end
    raise SystemExit('TV REBUILD FAILED: clase contenedora de stateMap ausente')


source = TARGET.read_text()

# Dependencias requeridas por el receptor LAN/mDNS y por el botón de copiar.
for statement in ("import 'dart:io';", "import 'dart:convert';", "import 'package:flutter/services.dart';"):
    if statement not in source:
        imports = list(re.finditer(r'(?m)^import\s+[^\n]+\n', source))
        at = imports[-1].end() if imports else 0
        source = source[:at] + statement + '\n' + source[at:]

# Reconstrucción determinista: elimina únicamente la estructura TV/LAN anterior.
for name in ('showTvConnection', 'showTvConnectionLegacy1', 'showTvConnectionLegacy2', 'showTvConnectionLegacy3', 'startLanServer'):
    source = remove_method(source, name)
for name in ('tvHtml', 'tvHtmlLegacy1', 'tvHtmlLegacy2', 'tvHtmlLegacy3'):
    source = remove_getter(source, name)
for field in ('HttpServer? server', 'String? lanIp'):
    source = remove_field(source, field)

# mDNS queda definido una sola vez, a nivel superior, sin depender del nombre de una clase.
mdns = '''
RawDatagramSocket? _billaresMdnsSocket;

Future<String?> _billaresLocalIp() async {
  try {
    final interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);
    for (final networkInterface in interfaces) {
      for (final address in networkInterface.addresses) {
        final p = address.address.split('.').map(int.tryParse).whereType<int>().toList();
        final privateIpv4 = p.length == 4 && (p[0] == 10 || (p[0] == 172 && p[1] >= 16 && p[1] <= 31) || (p[0] == 192 && p[1] == 168));
        if (!address.isLoopback && !address.isLinkLocal && !address.isMulticast && privateIpv4) return address.address;
      }
    }
  } catch (_) {}
  return null;
}

Future<void> _answerBillaresMdns(RawDatagramSocket socket, Datagram datagram) async {
  try {
    final query = datagram.data;
    if (query.length < 12) return;
    final questions = (query[4] << 8) | query[5];
    var offset = 12;
    var match = false;
    for (var q = 0; q < questions; q++) {
      final labels = <String>[];
      while (offset < query.length) {
        final length = query[offset++];
        if (length == 0) break;
        if (length > 63 || offset + length > query.length) return;
        labels.add(String.fromCharCodes(query.sublist(offset, offset + length)));
        offset += length;
      }
      if (offset + 4 > query.length) return;
      final type = (query[offset] << 8) | query[offset + 1];
      offset += 4;
      if (labels.join('.').toLowerCase() == 'billaresdonmiguel.local' && (type == 1 || type == 255)) match = true;
    }
    if (!match) return;
    final ip = await _billaresLocalIp();
    if (ip == null) return;
    final octets = ip.split('.').map(int.parse).toList();
    if (octets.length != 4) return;
    final response = <int>[];
    response.addAll(query.sublist(0, 2));
    response.addAll(<int>[0x84, 0, 0, 0, 0, 1, 0, 0, 0, 120, 0, 4]);
    response.addAll(query.sublist(12, offset));
    response.addAll(<int>[0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, 120, 0, 4]);
    response.addAll(octets);
    socket.send(response, datagram.address, datagram.port);
  } catch (_) {}
}

Future<void> _startBillaresMdns() async {
  try {
    _billaresMdnsSocket?.close();
    final socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 5353, reuseAddress: true, reusePort: true);
    _billaresMdnsSocket = socket;
    socket.joinMulticast(InternetAddress('224.0.0.251'));
    socket.listen((event) {
      if (event != RawSocketEvent.read) return;
      final datagram = socket.receive();
      if (datagram != null) _answerBillaresMdns(socket, datagram);
    });
  } catch (_) {}
}
'''

first_class = re.search(r'\bclass\s+[A-Za-z_][A-Za-z0-9_]*', source)
if not first_class:
    raise SystemExit('TV REBUILD FAILED: ninguna clase Dart encontrada')
source = source[:first_class.start()] + mdns + '\n' + source[first_class.start():]

marker = re.search(r'\bMap\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap\s*\(\s*\)', source)
if not marker:
    raise SystemExit('TV REBUILD FAILED: stateMap ausente')
class_start, class_end = class_span_containing(source, marker.start())
class_source = source[class_start:class_end]
state = re.search(r'\bMap\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap\s*\(\s*\)', class_source)

server_members = '''
  HttpServer? server;
  String? lanIp;

  Future<void> startLanServer() async {
    try {
      server = await HttpServer.bind(InternetAddress.anyIPv4, 80, shared: true);
      lanIp = await _billaresLocalIp();
      server!.listen(handleRequest, onError: (_) {});
      await _startBillaresMdns();
      if (mounted) setState(() {});
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo iniciar el servidor LAN en el puerto 80')));
    }
  }

  Future<void> showTvConnection() async {
    const url = 'http://billaresdonmiguel.local/tv';
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Pantalla exclusiva para TV'),
        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
          const Text('La TV mostrará solamente las mesas. El celular seguirá funcionando como administrador.'),
          const SizedBox(height: 12),
          const SelectableText(url, style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          FilledButton.icon(onPressed: () async {
            await Clipboard.setData(const ClipboardData(text: url));
            if (dialogContext.mounted) ScaffoldMessenger.of(dialogContext).showSnackBar(const SnackBar(content: Text('Dirección copiada')));
          }, icon: const Icon(Icons.copy), label: const Text('Copiar dirección')),
          const SizedBox(height: 8),
          const Text('En la TV abre el navegador y escribe la dirección. No uses Duplicar pantalla/Miracast.', style: TextStyle(fontSize: 12)),
        ])),
        actions: <Widget>[TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cerrar'))],
      ),
    );
  }
'''

html = ''.join([
    '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Billares Don Miguel - TV</title>',
    '<style>*{box-sizing:border-box}body{margin:0;background:#05070b;color:#fff;font-family:Arial,sans-serif}header{padding:18px;text-align:center;background:#fff;border-bottom:3px solid #1557c0}h1{margin:0;font-size:clamp(28px,4vw,46px);color:#1557c0;text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff}.clock{margin-top:6px;font-size:clamp(18px,2vw,26px);font-weight:700;color:#123f91}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px;padding:22px;max-width:1800px;margin:auto}.card{border-radius:18px;padding:22px;background:#111827;border:3px solid #64748b;min-height:205px}.green{background:#103b22;border-color:#22c55e}.red{background:#511b1b;border-color:#ef4444}.yellow{background:#56490a;border-color:#eab308}.name{font-size:clamp(25px,3vw,38px);font-weight:900}.status{margin:10px 0;font-size:clamp(18px,2vw,25px);font-weight:800}.line{margin:8px 0;font-size:clamp(15px,1.6vw,20px)}.money{margin-top:14px;font-size:clamp(25px,2.7vw,36px);font-weight:900}.offline{position:fixed;right:12px;bottom:10px;background:#7f1d1d;padding:7px 12px;border-radius:10px;display:none}</style></head>',
    '<body><header><h1>Billares Don Miguel</h1><div id="clock" class="clock">Conectando...</div></header><main id="grid" class="grid"></main><div id="offline" class="offline">Sin conexión con CENTRAL</div>',
    '<script>function money(n){return \'C&#36; \'+Number(n||0).toFixed(2)}function render(d){document.getElementById(\'clock\').textContent=d.time||\'--:--:--\';document.getElementById(\'grid\').innerHTML=(d.tables||[]).map(function(t){var c=t.status===\'Disponible\'?\'green\':t.status===\'En juego\'?\'red\':\'yellow\';return \'<section class="card \'+c+\'"><div class="name">Mesa \'+t.number+\'</div><div class="status">\'+t.status+\'</div><div class="line">Inicio: \'+(t.start||\'—\')+\'</div><div class="line">Finalización: \'+(t.end||\'—\')+\'</div><div class="line">Tiempo jugado: \'+(t.elapsed||\'00:00:00\')+\'</div><div class="money">\'+money(t.amount)+\'</div></section>\'}).join(\'\')}async function tick(){try{var r=await fetch(\'/api/state?ts=\'+Date.now(),{cache:\'no-store\'});if(!r.ok)throw new Error();render(await r.json());document.getElementById(\'offline\').style.display=\'none\'}catch(e){document.getElementById(\'offline\').style.display=\'block\'}}tick();setInterval(tick,1000);</script>',
    '</body></html>'
])
getter = '  String get tvHtml => ' + json.dumps(html, ensure_ascii=False, separators=(',', ':')) + ';\n\n'

class_source = class_source[:state.start()] + server_members + getter + class_source[state.start():]
source = source[:class_start] + class_source + source[class_end:]
TARGET.write_text(source)
print('OK: reconstrucción única TV/LAN/mDNS completada')
