from pathlib import Path
import json
import re

TARGET = Path('lib/main.dart')


def skip_string(s, i):
    q = s[i]
    token = q * 3 if s.startswith(q * 3, i) else q
    i += len(token)
    while i < len(s):
        if s[i] == '\\':
            i += 2
        elif s.startswith(token, i):
            return i + len(token)
        else:
            i += 1
    raise SystemExit('TV REBUILD FAILED: cadena Dart sin cerrar')


def brace_end(s, start):
    depth = 0
    i = start
    while i < len(s):
        if s[i] in "'\"":
            i = skip_string(s, i)
            continue
        if s.startswith('//', i):
            e = s.find('\n', i + 2)
            i = len(s) if e < 0 else e + 1
            continue
        if s.startswith('/*', i):
            e = s.find('*/', i + 2)
            if e < 0:
                raise SystemExit('TV REBUILD FAILED: comentario sin cerrar')
            i = e + 2
            continue
        if s[i] == '{':
            depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise SystemExit('TV REBUILD FAILED: llaves sin cerrar')


def statement_end(s, start):
    i = start
    while i < len(s):
        if s[i] in "'\"":
            i = skip_string(s, i)
            continue
        if s.startswith('//', i):
            e = s.find('\n', i + 2)
            i = len(s) if e < 0 else e + 1
            continue
        if s[i] == ';':
            return i + 1
        i += 1
    raise SystemExit('TV REBUILD FAILED: declaración sin terminar')


def remove_method(s, name):
    p = re.compile(rf'(?m)^\s*(?:Future\s*<\s*void\s*>|void)\s+{re.escape(name)}\s*\([^)]*\)\s*(?:async\s*)?\{{')
    while True:
        m = p.search(s)
        if not m:
            return s
        s = s[:m.start()] + s[brace_end(s, s.find('{', m.start(), m.end())):]


def remove_getter(s, name):
    p = re.compile(rf'(?m)^\s*String\s+get\s+{re.escape(name)}\s*(?:=>|\{{)')
    while True:
        m = p.search(s)
        if not m:
            return s
        end = brace_end(s, s.find('{', m.start(), m.end())) if '{' in m.group(0) else statement_end(s, m.end())
        s = s[:m.start()] + s[end:]


def class_span(s, pos):
    candidates = list(re.finditer(r'\bclass\s+[A-Za-z_][A-Za-z0-9_]*[^\{]*\{', s[:pos]))
    for m in reversed(candidates):
        end = brace_end(s, s.find('{', m.start(), m.end()))
        if end > pos:
            return m.start(), end
    raise SystemExit('TV REBUILD FAILED: clase de stateMap no encontrada')


def escape_plain_dollars(s):
    out = []
    i = 0
    while i < len(s):
        if s[i] in "'\"":
            start = i
            triple = s.startswith(s[i] * 3, i)
            end = skip_string(s, i)
            body = s[start:end]
            if not triple:
                chars = []
                j = 0
                while j < len(body):
                    if body[j] == '\\' and j + 1 < len(body):
                        chars.append(body[j:j + 2]); j += 2
                    elif body[j] == '$' and (j + 1 == len(body) or (body[j + 1] not in '{' and not (body[j + 1].isalpha() or body[j + 1] == '_'))):
                        chars.append('\\$'); j += 1
                    else:
                        chars.append(body[j]); j += 1
                body = ''.join(chars)
            out.append(body); i = end
        else:
            out.append(s[i]); i += 1
    return ''.join(out)


source = TARGET.read_text()
for imp in ("import 'dart:io';", "import 'dart:convert';", "import 'package:flutter/services.dart';"):
    if imp not in source:
        imports = list(re.finditer(r'(?m)^import\s+[^\n]+\n', source))
        at = imports[-1].end() if imports else 0
        source = source[:at] + imp + '\n' + source[at:]

marker = re.search(r'\bMap\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap\s*\(\s*\)', source)
if not marker:
    raise SystemExit('TV REBUILD FAILED: stateMap ausente')
class_start, class_end = class_span(source, marker.start())
class_source = source[class_start:class_end]

for name in ('startLanServer', 'showTvConnection'):
    class_source = remove_method(class_source, name)
for name in ('tvHtml', 'tvHtmlLegacy1', 'tvHtmlLegacy2', 'tvHtmlLegacy3'):
    class_source = remove_getter(class_source, name)
class_source = re.sub(r'(?m)^\s*HttpServer\?\s+server\s*;\s*\n?', '', class_source)
class_source = re.sub(r'(?m)^\s*String\?\s+lanIp\s*;\s*\n?', '', class_source)

mdns = r'''
RawDatagramSocket? _billaresMdnsSocket;

Future<String?> _billaresLocalIp() async {
  try {
    final interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);
    for (final networkInterface in interfaces) {
      for (final address in networkInterface.addresses) {
        final p = address.address.split('.').map(int.tryParse).whereType<int>().toList();
        final privateIpv4 = p.length == 4 && (p[0] == 10 || (p[0] == 172 && p[1] >= 16 && p[1] <= 31) || (p[0] == 192 && p[1] == 168));
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
    for (var q = 0; q < questions; q++) {
      final labels = <String>[];
      while (offset < query.length) {
        final n = query[offset++];
        if (n == 0) break;
        if (n > 63 || offset + n > query.length) return;
        labels.add(String.fromCharCodes(query.sublist(offset, offset + n)));
        offset += n;
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
first = re.search(r'\bclass\s+[A-Za-z_][A-Za-z0-9_]*', source)
source = source[:first.start()] + mdns + '\n' + source[first.start():]

marker = re.search(r'\bMap\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap\s*\(\s*\)', source)
class_start, class_end = class_span(source, marker.start())
class_source = source[class_start:class_end]
state = re.search(r'\bMap\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap\s*\(\s*\)', class_source)

members = r'''
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
class_source = class_source[:state.start()] + members + getter + class_source[state.start():]
source = source[:class_start] + class_source + source[class_end:]
source = escape_plain_dollars(source)
TARGET.write_text(source)
print('OK: productor nuevo TV/LAN/mDNS reconstruido')
