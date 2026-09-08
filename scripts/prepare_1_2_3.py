from pathlib import Path
import re

main = Path('lib/main.dart')
s = main.read_text()
s = s.replace("const String appVersion = '1.2.1+121';", "const String appVersion = '1.2.3+123';")
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
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo iniciar el servidor LAN en el puerto 8080')));
      }
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
    if (request.method == 'OPTIONS') {
      response.statusCode = HttpStatus.noContent;
      await response.close();
      return;
    }
    if (request.uri.path == '/health') {
      response.headers.contentType = ContentType.json;
      final String body = jsonEncode(<String, dynamic>{'ok': true, 'app': 'Billares Don Miguel', 'version': appVersion});
      response.headers.contentLength = utf8.encode(body).length;
      response.write(body);
    } else if (request.uri.path == '/api/state') {
      response.headers.contentType = ContentType.json;
      final String body = jsonEncode(stateMap());
      response.headers.contentLength = utf8.encode(body).length;
      response.write(body);
    } else {
      response.headers.contentType = ContentType.html;
      response.headers.contentLength = utf8.encode(tvHtml).length;
      response.write(tvHtml);
    }
    await response.close();
  }
'''
s2 = re.sub(r"  Future<void> startLanServer\(\) async \{.*?\n  Map<String, dynamic> stateMap\(\)", start_server + "\n  Map<String, dynamic> stateMap()", s, count=1, flags=re.S)
if s2 == s:
    raise SystemExit('No se pudo reemplazar startLanServer')
s = s2

show_tv = r'''  Future<void> showTvConnection() async {
    if (lanIp == null) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Esperando la conexión LAN de CENTRAL...')));
      return;
    }
    final String url = 'http://$lanIp:8080/tv';
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (BuildContext context) => AlertDialog(
        title: const Text('Conectar televisor'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Text('Método universal: la TV debe estar en la misma Wi‑Fi que CENTRAL y tener navegador web.'),
              const SizedBox(height: 10),
              SelectableText(url, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: () async {
                  await Clipboard.setData(ClipboardData(text: url));
                  if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Dirección de TV copiada')));
                },
                icon: const Icon(Icons.copy),
                label: const Text('Copiar dirección'),
              ),
              const SizedBox(height: 6),
              OutlinedButton.icon(
                onPressed: () async {
                  final Uri uri = Uri.parse(url);
                  if (!await launchUrl(uri, mode: LaunchMode.externalApplication) && context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo abrir el navegador')));
                  }
                },
                icon: const Icon(Icons.open_in_browser),
                label: const Text('Abrir receptor web'),
              ),
              const SizedBox(height: 6),
              FilledButton.icon(
                onPressed: () async {
                  try {
                    await const MethodChannel('com.billaresdonmiguel/tv_cast').invokeMethod<void>('openCastSettings');
                  } on PlatformException {
                    if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('La opción de transmisión no está disponible en este dispositivo')));
                  }
                },
                icon: const Icon(Icons.cast),
                label: const Text('Buscar TV / Chromecast / Miracast'),
              ),
              const SizedBox(height: 10),
              const Text('Para Smart TV y Android TV, abre la dirección en el navegador. Para Chromecast/Google Cast o Miracast, usa la opción de transmisión del dispositivo. La conexión web continúa actualizándose automáticamente.', style: TextStyle(fontSize: 13)),
            ],
          ),
        ),
        actions: <Widget>[TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cerrar'))],
      ),
    );
  }
'''
s2 = re.sub(r"  Future<void> showTvConnection\(\) async \{.*?\n  int buildNumber\(String version\)", show_tv + "\n  int buildNumber(String version)", s, count=1, flags=re.S)
if s2 == s:
    raise SystemExit('No se pudo reemplazar showTvConnection')
s = s2

s = s.replace("client = HttpClient()..connectionTimeout = const Duration(seconds: 8);", "client = HttpClient()..connectionTimeout = const Duration(seconds: 12);\n      client.userAgent = 'Billares-Don-Miguel/1.2.3';")
s = s.replace("client = HttpClient()..connectionTimeout = const Duration(seconds: 20);", "client = HttpClient()..connectionTimeout = const Duration(seconds: 30);\n      client.userAgent = 'Billares-Don-Miguel/1.2.3';")
main.write_text(s)

# The workflow runs after flutter create, so patch the generated MainActivity safely.
files = list(Path('android/app/src/main').rglob('MainActivity.kt'))
if not files:
    raise SystemExit('No se encontró MainActivity.kt')
activity = files[0]
text = activity.read_text()
package_line = next((line for line in text.splitlines() if line.startswith('package ')), 'package com.billaresdonmiguel.billares_don_miguel')
native = f'''{package_line}

import android.content.Intent
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {{
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {{
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "com.billaresdonmiguel/tv_cast").setMethodCallHandler {{ call, result ->
            if (call.method == "openCastSettings") {{
                try {{
                    startActivity(Intent(Settings.ACTION_CAST_SETTINGS))
                    result.success(true)
                }} catch (_: Exception) {{
                    try {{
                        startActivity(Intent(Settings.ACTION_SETTINGS))
                        result.success(true)
                    }} catch (_: Exception) {{
                        result.success(false)
                    }}
                }}
            }} else {{
                result.notImplemented()
            }}
        }}
    }}
}}
'''
activity.write_text(native)
