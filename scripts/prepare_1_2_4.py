from pathlib import Path
import re

main = Path('lib/main.dart')
s = main.read_text()

# Base 1.2.3 stability changes promoted to 1.2.5+125.
s = s.replace("const String appVersion = '1.2.1+121';", "const String appVersion = '1.2.5+125';")
s = s.replace("const String updateManifestUrl = 'https://raw.githubusercontent.com/anparamo25-sketch/Billares-Don-Miguel-/main/update.json';", "const String updateManifestUrl = 'https://github.com/anparamo25-sketch/Billares-Don-Miguel-/raw/refs/heads/main/update.json';")
if "package:url_launcher/url_launcher.dart" not in s:
    s = s.replace("import 'package:shared_preferences/shared_preferences.dart';", "import 'package:shared_preferences/shared_preferences.dart';\nimport 'package:url_launcher/url_launcher.dart';")

start_server = r'''  Future<void> startLanServer() async {
    try {
      server = await HttpServer.bind(InternetAddress.anyIPv4, 8080, shared: true);
      final List<NetworkInterface> interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);
      final List<String> candidates = <String>[];
      for (final NetworkInterface networkInterface in interfaces) {
        final String name = networkInterface.name.toLowerCase();
        for (final InternetAddress address in networkInterface.addresses) {
          final String ip = address.address;
          final List<int> parts = ip.split('.').map(int.parse).toList();
          final bool privateIpv4 = parts.length == 4 && ((parts[0] == 10) || (parts[0] == 172 && parts[1] >= 16 && parts[1] <= 31) || (parts[0] == 192 && parts[1] == 168));
          if (!address.isLoopback && !address.isMulticast && !address.isLinkLocal && privateIpv4) {
            final int priority = name.contains('wlan') || name.contains('wifi') ? 0 : name.contains('eth') ? 1 : 2;
            candidates.add('$priority|$ip');
          }
        }
      }
      candidates.sort();
      if (candidates.isNotEmpty) lanIp = candidates.first.split('|').last;
      server!.listen(handleRequest, onError: (_) {});
      if (mounted) setState(() {});
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo iniciar el servidor LAN en el puerto 8080')));
    }
  }

  Future<void> handleRequest(HttpRequest request) async {
    final HttpResponse response = request.response;
    response.headers.set('Access-Control-Allow-Origin', '*');
    response.headers.set('Access-Control-Allow-Methods', 'GET, OPTIONS');
    response.headers.set('Access-Control-Allow-Headers', 'Content-Type, Cache-Control');
    response.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    response.headers.set('Pragma', 'no-cache');
    response.headers.set('Connection', 'keep-alive');
    if (request.method == 'OPTIONS') { response.statusCode = HttpStatus.noContent; await response.close(); return; }
    if (request.uri.path == '/health') {
      response.headers.contentType = ContentType.json;
      final String body = jsonEncode(<String, dynamic>{'ok': true, 'app': 'Billares Don Miguel', 'version': appVersion});
      response.headers.contentLength = utf8.encode(body).length; response.write(body);
    } else if (request.uri.path == '/api/state') {
      response.headers.contentType = ContentType.json;
      final String body = jsonEncode(stateMap());
      response.headers.contentLength = utf8.encode(body).length; response.write(body);
    } else if (request.uri.path == '/tv' || request.uri.path == '/') {
      response.headers.contentType = ContentType.html;
      response.headers.contentLength = utf8.encode(tvHtml).length; response.write(tvHtml);
    } else { response.statusCode = HttpStatus.notFound; response.headers.contentType = ContentType.text; response.write('Not found'); }
    await response.close();
  }
'''
s2 = re.sub(r"  Future<void> startLanServer\(\) async \{.*?\n  Map<String, dynamic> stateMap\(\)", start_server + "\n  Map<String, dynamic> stateMap()", s, count=1, flags=re.S)
if s2 == s: raise SystemExit('No se pudo reemplazar el servidor LAN')
s = s2

show_tv = r'''  Future<void> showTvConnection() async {
    if (lanIp == null) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Esperando la conexión LAN de CENTRAL...'))); return; }
    final String url = 'http://$lanIp:8080/tv';
    if (!mounted) return;
    await showDialog<void>(context: context, builder: (BuildContext context) => AlertDialog(
      title: const Text('Pantalla exclusiva para TV'),
      content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
        const Text('La TV muestra solamente las mesas. CENTRAL puede seguir utilizándose normalmente en el celular.'),
        const SizedBox(height: 12), const Text('Receptor TV:'), const SizedBox(height: 6),
        SelectableText(url, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)), const SizedBox(height: 8),
        OutlinedButton.icon(onPressed: () async { await Clipboard.setData(ClipboardData(text: url)); if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Dirección de TV copiada'))); }, icon: const Icon(Icons.copy), label: const Text('Copiar dirección')),
        const SizedBox(height: 6), const Text('En la TV abre esta dirección con su navegador. El receptor /tv es independiente del panel administrativo.'),
        const SizedBox(height: 10), const Text('Para Google Cast real se requiere un Custom Web Receiver registrado y su Application ID. La duplicación Miracast no se usa para este receptor.', style: TextStyle(fontSize: 12)),
      ])),
      actions: <Widget>[TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cerrar'))],
    ));
  }
'''
s2 = re.sub(r"  Future<void> showTvConnection\(\) async \{.*?\n  int buildNumber\(String version\)", show_tv + "\n  int buildNumber(String version)", s, count=1, flags=re.S)
if s2 == s: raise SystemExit('No se pudo reemplazar la conexión TV')
s = s2

# More resilient updater.
s = s.replace("client = HttpClient()..connectionTimeout = const Duration(seconds: 8);", "client = HttpClient()..connectionTimeout = const Duration(seconds: 12);\n      client.userAgent = 'Billares-Don-Miguel/1.2.5';")
s = s.replace("client = HttpClient()..connectionTimeout = const Duration(seconds: 20);", "client = HttpClient()..connectionTimeout = const Duration(seconds: 30);\n      client.userAgent = 'Billares-Don-Miguel/1.2.5';")

# Preserve the previously agreed responsive/workday changes from the validated 1.2.4 preparation.
# The existing source transformation below is intentionally conservative: it does not alter rates or billing logic.

main.write_text(s)
print('OK: preparación 1.2.5+125')
