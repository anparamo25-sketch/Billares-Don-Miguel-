from pathlib import Path
import re

main = Path('lib/main.dart')
s = main.read_text()

show_tv = r'''  Future<void> showTvConnection() async {
    if (lanIp == null) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Esperando la conexión LAN de CENTRAL...')));
      return;
    }
    final String url = 'http://$lanIp:8080/tv';
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: const Text('Receptor exclusivo para TV'),
        content: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
            const Text('Esta opción NO duplica la pantalla del celular. La TV debe abrir el receptor web y mostrará únicamente las mesas.'),
            const SizedBox(height: 14),
            const Text('Dirección del receptor:', style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            SelectableText(url, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            FilledButton.icon(onPressed: () async { await Clipboard.setData(ClipboardData(text: url)); if (dialogContext.mounted) ScaffoldMessenger.of(dialogContext).showSnackBar(const SnackBar(content: Text('Dirección copiada'))); }, icon: const Icon(Icons.copy), label: const Text('Copiar dirección')),
            const SizedBox(height: 8),
            OutlinedButton.icon(onPressed: () async { try { final bool opened = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication); if (!opened && dialogContext.mounted) ScaffoldMessenger.of(dialogContext).showSnackBar(const SnackBar(content: Text('No se pudo abrir el receptor web'))); } catch (_) { if (dialogContext.mounted) ScaffoldMessenger.of(dialogContext).showSnackBar(const SnackBar(content: Text('No se pudo abrir el receptor web'))); } }, icon: const Icon(Icons.open_in_browser), label: const Text('Probar receptor web')),
            const SizedBox(height: 10),
            const Text('En la TV: abre su navegador y escribe exactamente la dirección anterior. El celular puede seguir usando CENTRAL normalmente.', style: TextStyle(fontSize: 12)),
            const SizedBox(height: 8),
            const Text('Importante: “Duplicar pantalla” de Android/Miracast muestra toda la pantalla. No se utiliza para este receptor.', style: TextStyle(fontSize: 12)),
          ]),
        ),
        actions: <Widget>[TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cerrar'))],
      ),
    );
  }
'''
s2 = re.sub(r"  Future<void> showTvConnection\(\) async \{.*?\n  int buildNumber\(String version\)", show_tv + "\n  int buildNumber(String version)", s, count=1, flags=re.S)
if s2 == s:
    raise SystemExit('No se encontró showTvConnection')
s = s2

server = r'''  Future<void> startLanServer() async {
    try {
      server?.close(force: true);
      server = await HttpServer.bind(InternetAddress.anyIPv4, 8080, shared: true);
      final List<NetworkInterface> interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);
      final List<String> candidates = <String>[];
      for (final NetworkInterface networkInterface in interfaces) {
        final String name = networkInterface.name.toLowerCase();
        for (final InternetAddress address in networkInterface.addresses) {
          final List<int> parts = address.address.split('.').map(int.parse).toList();
          final bool privateIpv4 = parts.length == 4 && ((parts[0] == 10) || (parts[0] == 172 && parts[1] >= 16 && parts[1] <= 31) || (parts[0] == 192 && parts[1] == 168));
          if (!address.isLoopback && !address.isMulticast && !address.isLinkLocal && privateIpv4) {
            final int priority = name.contains('wlan') || name.contains('wifi') ? 0 : name.contains('eth') ? 1 : 2;
            candidates.add('$priority|${address.address}');
          }
        }
      }
      candidates.sort();
      if (candidates.isNotEmpty) lanIp = candidates.first.split('|').last;
      server!.listen(handleRequest, onError: (_) {});
      if (mounted) setState(() {});
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo iniciar el receptor LAN en el puerto 8080')));
    }
  }

  Future<void> handleRequest(HttpRequest request) async {
    final HttpResponse response = request.response;
    response.headers.set('Access-Control-Allow-Origin', '*');
    response.headers.set('Access-Control-Allow-Methods', 'GET, OPTIONS');
    response.headers.set('Access-Control-Allow-Headers', '*');
    response.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    response.headers.set('Pragma', 'no-cache');
    if (request.method == 'OPTIONS') { response.statusCode = HttpStatus.noContent; await response.close(); return; }
    if (request.uri.path == '/health') {
      final String body = jsonEncode(<String, dynamic>{'ok': true, 'app': 'Billares Don Miguel', 'version': appVersion});
      response.headers.contentType = ContentType('application', 'json', charset: 'utf-8'); response.write(body);
    } else if (request.uri.path == '/api/state') {
      final String body = jsonEncode(stateMap());
      response.headers.contentType = ContentType('application', 'json', charset: 'utf-8'); response.write(body);
    } else if (request.uri.path == '/tv' || request.uri.path == '/') {
      response.headers.contentType = ContentType('text', 'html', charset: 'utf-8'); response.write(tvHtml);
    } else { response.statusCode = HttpStatus.notFound; response.write('Not found'); }
    await response.close();
  }
'''
s2 = re.sub(r"  Future<void> startLanServer\(\) async \{.*?\n  Map<String, dynamic> stateMap\(\)", server + "\n  Map<String, dynamic> stateMap()", s, count=1, flags=re.S)
if s2 == s:
    raise SystemExit('No se encontró startLanServer')
s = s2

if 'String get tvHtml {' not in s:
    placeholder = "  String get tvHtml { return '<!doctype html><html><body><div id=\\\"grid\\\"></div></body></html>'; }\n"
    marker = '  Map<String, dynamic> stateMap()'
    if marker not in s:
        raise SystemExit('No se encontró stateMap para insertar tvHtml')
    s = s.replace(marker, placeholder + marker, 1)

tv = r'''  String get tvHtml {
    final String initialState = jsonEncode(stateMap()).replaceAll('\\', '\\\\').replaceAll('</', '<\\/');
    return '''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-cache,no-store,must-revalidate"><title>Billares Don Miguel - TV</title><style>*{box-sizing:border-box}body{margin:0;background:#05070b;color:#fff;font-family:Arial,Helvetica,sans-serif;min-height:100vh}header{padding:18px 24px 12px;text-align:center;background:#fff;border-bottom:3px solid #123f91}h1{margin:0;font-size:clamp(28px,4vw,46px);letter-spacing:1px;color:#1557c0;text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff}.clock{font-size:clamp(18px,2vw,26px);margin-top:7px;color:#123f91;font-weight:700}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px;padding:22px;max-width:1800px;margin:0 auto}.card{border-radius:18px;padding:22px;background:#111827;border:3px solid #64748b;box-shadow:0 8px 28px #000;min-height:205px}.card.green{background:#103b22;border-color:#22c55e}.card.red{background:#511b1b;border-color:#ef4444}.card.yellow{background:#56490a;border-color:#eab308}.name{font-size:clamp(25px,3vw,38px);font-weight:900}.status{margin:10px 0;font-size:clamp(18px,2vw,25px);font-weight:800}.line{margin:8px 0;font-size:clamp(15px,1.6vw,20px);color:#f8fafc}.money{font-size:clamp(25px,2.7vw,36px);font-weight:900;margin-top:14px}.offline{position:fixed;right:12px;bottom:10px;background:#7f1d1d;padding:7px 12px;border-radius:10px;font-size:13px;display:none}</style></head><body><header><h1>Billares Don Miguel</h1><div id="clock" class="clock">Cargando...</div></header><main id="grid" class="grid"></main><div id="offline" class="offline">Sin conexión con CENTRAL</div><script>var state=INITIAL_STATE;function money(n){return 'C\$ '+Number(n||0).toFixed(2)}function render(d){state=d;document.getElementById('clock').textContent=d.time||'--:--:--';document.getElementById('grid').innerHTML=(d.tables||[]).map(function(t){var c=t.status==='Disponible'?'green':t.status==='En juego'?'red':'yellow';return '<section class="card '+c+'"><div class="name">Mesa '+t.number+'</div><div class="status">'+t.status+'</div><div class="line">Inicio: '+(t.start||'—')+'</div><div class="line">Finalización: '+(t.end||'—')+'</div><div class="line">Tiempo jugado: '+(t.elapsed||'00:00:00')+'</div><div class="money">'+money(t.amount)+'</div></section>'}).join('')}async function tick(){try{var r=await fetch('/api/state?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error();render(await r.json());document.getElementById('offline').style.display='none'}catch(e){document.getElementById('offline').style.display='block'}}render(state);setInterval(tick,1000);tick();</script></body></html>'''.replace('INITIAL_STATE', initialState);
  }
'''
s2 = re.sub(r"  String get tvHtml \{.*?\n  \}", tv, s, count=1, flags=re.S)
if s2 == s:
    raise SystemExit('No se pudo generar tvHtml')
s = s2

s = s.replace('ACTION_CAST_SETTINGS_DISABLED', 'ACTION_CAST_SETTINGS')
main.write_text(s)
print('OK: dedicated TV web receiver repair generated')
