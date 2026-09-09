from pathlib import Path
import json
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
    raise SystemExit('TV 1.2.6 FAILED: cadena Dart sin cerrar')


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
    raise SystemExit('TV 1.2.6 FAILED: llaves Dart sin cerrar')


def statement_end(source, start):
    index = start
    while index < len(source):
        if source[index] in "'\"":
            index = skip_string(source, index)
            continue
        if source.startswith('//', index):
            end = source.find('\n', index + 2)
            index = len(source) if end < 0 else end + 1
            continue
        if source[index] == ';':
            return index + 1
        index += 1
    raise SystemExit('TV 1.2.6 FAILED: declaración Dart sin terminar')


def remove_method(source, name):
    pattern = re.compile(rf'(?m)^\s*(?:Future\s*<\s*void\s*>|void)\s+{re.escape(name)}\s*\([^)]*\)\s*(?:async\s*)?\{{')
    while True:
        match = pattern.search(source)
        if not match:
            return source
        start = source.find('{', match.start(), match.end())
        source = source[:match.start()] + source[brace_end(source, start):]


def remove_getter(source, name):
    pattern = re.compile(rf'(?m)^\s*String\s+get\s+{re.escape(name)}\s*(?:=>|\{{)')
    while True:
        match = pattern.search(source)
        if not match:
            return source
        if '{' in match.group(0):
            end = brace_end(source, source.find('{', match.start(), match.end()))
        else:
            end = statement_end(source, match.end())
        source = source[:match.start()] + source[end:]


def remove_top_level_function(source, name):
    pattern = re.compile(rf'(?m)^\s*(?:Future\s*<[^\n{{]+>|void|String\??)\s+{re.escape(name)}\s*\([^)]*\)\s*(?:async\s*)?\{{')
    while True:
        match = pattern.search(source)
        if not match:
            return source
        start = source.find('{', match.start(), match.end())
        source = source[:match.start()] + source[brace_end(source, start):]


def class_span(source, position):
    candidates = list(re.finditer(r'\bclass\s+[A-Za-z_][A-Za-z0-9_]*[^\{]*\{', source[:position]))
    for match in reversed(candidates):
        end = brace_end(source, source.find('{', match.start(), match.end()))
        if end > position:
            return match.start(), end
    raise SystemExit('TV 1.2.6 FAILED: no se encontró la clase que contiene stateMap')


def escape_plain_dollars(source):
    output = []
    index = 0
    while index < len(source):
        if source[index] in "'\"":
            start = index
            triple = source.startswith(source[index] * 3, index)
            end = skip_string(source, index)
            body = source[start:end]
            if not triple:
                chars = []
                j = 0
                while j < len(body):
                    if body[j] == '\\' and j + 1 < len(body):
                        chars.append(body[j:j + 2])
                        j += 2
                    elif body[j] == '$' and (j + 1 == len(body) or (body[j + 1] != '{' and not (body[j + 1].isalpha() or body[j + 1] == '_'))):
                        chars.append('\\$')
                        j += 1
                    else:
                        chars.append(body[j])
                        j += 1
                body = ''.join(chars)
            output.append(body)
            index = end
        else:
            output.append(source[index])
            index += 1
    return ''.join(output)


source = TARGET.read_text()
for import_line in ("import 'dart:io';", "import 'package:flutter/services.dart';"):
    if import_line not in source:
        imports = list(re.finditer(r'(?m)^import\s+[^\n]+\n', source))
        position = imports[-1].end() if imports else 0
        source = source[:position] + import_line + '\n' + source[position:]

state_marker = re.search(r'\bMap\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap\s*\(\s*\)', source)
if not state_marker:
    raise SystemExit('TV 1.2.6 FAILED: stateMap ausente')

class_start, class_end = class_span(source, state_marker.start())
class_source = source[class_start:class_end]
for method_name in ('startLanServer', 'showTvConnection'):
    class_source = remove_method(class_source, method_name)
for getter_name in ('tvHtml', 'tvHtmlLegacy1', 'tvHtmlLegacy2', 'tvHtmlLegacy3'):
    class_source = remove_getter(class_source, getter_name)
class_source = re.sub(r'(?m)^\s*HttpServer\?\s+server\s*;\s*\n?', '', class_source)
class_source = re.sub(r'(?m)^\s*String\?\s+lanIp\s*;\s*\n?', '', class_source)
class_source = re.sub(r'(?m)^\s*int\??\s+lanPort\s*;\s*\n?', '', class_source)
source = source[:class_start] + class_source + source[class_end:]

for function_name in ('_billaresLocalIp', '_answerBillaresMdns', '_startBillaresMdns'):
    source = remove_top_level_function(source, function_name)
source = re.sub(r'(?m)^\s*RawDatagramSocket\?\s+_billaresMdnsSocket\s*;\s*\n?', '', source)

mdns = '''
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
    final query = datagram.data;
    if (query.length < 12) return;
    final questions = (query[4] << 8) | query[5];
    var offset = 12;
    var match = false;
    for (var i = 0; i < questions; i++) {
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
    raise SystemExit('TV 1.2.6 FAILED: no hay clases Dart')
source = source[:first_class.start()] + mdns + source[first_class.start():]

state_marker = re.search(r'\bMap\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap\s*\(\s*\)', source)
class_start, class_end = class_span(source, state_marker.start())
class_source = source[class_start:class_end]
state = re.search(r'\bMap\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap\s*\(\s*\)', class_source)

members = '''
  HttpServer? server;
  String? lanIp;
  int? lanPort;
  Future<void> startLanServer() async {
    if (server != null) return;
    try {
      try {
        server = await HttpServer.bind(InternetAddress.anyIPv4, 80, shared: true);
        lanPort = 80;
      } catch (_) {
        server = await HttpServer.bind(InternetAddress.anyIPv4, 8080, shared: true);
        lanPort = 8080;
      }
      lanIp = await _billaresLocalIp();
      server!.listen(handleRequest, onError: (_) {});
      await _startBillaresMdns();
      if (mounted) setState(() {});
    } catch (_) {
      server = null;
      lanPort = null;
      if (mounted) setState(() {});
    }
  }
  Future<void> showTvConnection() async {
    final int port = lanPort ?? 80;
    final String url = port == 80 ? 'http://billaresdonmiguel.local/tv' : 'http://billaresdonmiguel.local:$port/tv';
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Pantalla exclusiva para TV'),
        content: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
            const Text('La TV mostrará solamente las mesas. La administración continúa funcionando de forma independiente.'),
            const SizedBox(height: 12),
            SelectableText(url, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            FilledButton.icon(onPressed: () async { await Clipboard.setData(ClipboardData(text: url)); if (dialogContext.mounted) ScaffoldMessenger.of(dialogContext).showSnackBar(const SnackBar(content: Text('Dirección de TV copiada'))); }, icon: const Icon(Icons.copy), label: const Text('Copiar dirección')),
            const SizedBox(height: 8),
            const Text('Para la pantalla exclusiva utiliza esta dirección en el navegador de la TV. No uses Duplicar pantalla/Miracast.', style: TextStyle(fontSize: 12)),
          ]),
        ),
        actions: <Widget>[TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cerrar'))],
      ),
    );
  }
'''

html = '''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Billares Don Miguel - TV</title><style>*{box-sizing:border-box}body{margin:0;background:#05070b;color:#fff;font-family:Arial,sans-serif}header{padding:18px;text-align:center;background:#fff;border-bottom:3px solid #1557c0}h1{margin:0;font-size:clamp(28px,4vw,46px);color:#1557c0;text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px;padding:22px}.card{border-radius:18px;padding:22px;border:3px solid #64748b;min-height:205px}.green{background:#103b22;border-color:#22c55e}.red{background:#511b1b;border-color:#ef4444}.yellow{background:#56490a;border-color:#eab308}.name{font-size:clamp(25px,3vw,38px);font-weight:900}.status{font-size:clamp(18px,2vw,25px);font-weight:800}.line{margin:8px 0;font-size:clamp(15px,1.6vw,20px)}.money{margin-top:14px;font-size:clamp(25px,2.7vw,36px);font-weight:900}</style></head><body><header><h1>Billares Don Miguel</h1></header><main id="grid" class="grid"></main><script>function money(n){return 'C&#36; '+Number(n||0).toFixed(2)}async function tick(){try{var r=await fetch('/api/state?ts='+Date.now(),{cache:'no-store'});var d=await r.json();document.getElementById('grid').innerHTML=(d.tables||[]).map(function(t){var c=t.status==='Disponible'?'green':t.status==='En juego'?'red':'yellow';return '<section class="card '+c+'"><div class="name">Mesa '+t.number+'</div><div class="status">'+t.status+'</div><div class="line">Inicio: '+(t.start||'—')+'</div><div class="line">Finalización: '+(t.end||'—')+'</div><div class="line">Tiempo jugado: '+(t.elapsed||'00:00:00')+'</div><div class="money">'+money(t.amount)+'</div></section>'}).join('')}catch(e){}}tick();setInterval(tick,1000);</script></body></html>'''

tv_literal = json.dumps(html, ensure_ascii=False)
getter = '  String get tvHtml => ' + tv_literal + ';\n\n'
class_source = class_source[:state.start()] + members + getter + class_source[state.start():]
source = source[:class_start] + class_source + source[class_end:]
source = escape_plain_dollars(source)
TARGET.write_text(source)
print('OK: productor TV/LAN/mDNS 1.2.6 reconstruido de forma determinista e idempotente')
