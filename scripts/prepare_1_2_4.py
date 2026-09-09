from pathlib import Path
import re
import subprocess

# Construye la base estable de jornadas/historial/responsive y la promueve a 1.2.6.
BASE_COMMIT = '21c20b4fdf72303398bb46c35dc109e1df373856'
source = subprocess.check_output(['git', 'show', f'{BASE_COMMIT}:scripts/prepare_1_2_4.py'], text=True)
source = source.replace('1.2.4+124', '1.2.6+126').replace('Billares-Don-Miguel/1.2.4', 'Billares-Don-Miguel/1.2.6')
exec(compile(source, 'prepare_1_2_6_from_history.py', 'exec'), {'__name__': '__main__'})

main = Path('lib/main.dart')
s = main.read_text()
s = s.replace('1.2.4+124', '1.2.6+126').replace('Billares-Don-Miguel/1.2.4', 'Billares-Don-Miguel/1.2.6')

# Estado LAN visible y explícito, sin introducir una segunda arquitectura de dispositivos.
old_lan = "if (lanIp != null) Flexible(child: Chip(avatar: const Icon(Icons.wifi, size: 18), label: Text('LAN $lanIp:8080', overflow: TextOverflow.ellipsis))),"
new_lan = "Flexible(child: Chip(avatar: Icon(Icons.wifi, size: 18, color: lanIp != null ? Colors.green : Colors.red), label: Text(lanIp != null ? 'LAN conectado • $lanIp' : 'LAN no disponible', overflow: TextOverflow.ellipsis))),"
if old_lan in s:
    s = s.replace(old_lan, new_lan, 1)

# Actualización OTA: comprobar permiso antes de abrir el instalador y distinguir descarga de instalación.
pattern = re.compile(r"  Future<void> downloadAndInstall\(String url\) async \{.*?\n  Future<void> changePassword\(\)", re.S)
replacement = '''  Future<void> downloadAndInstall(String url) async {
    HttpClient? client;
    final Directory directory = await getApplicationDocumentsDirectory();
    final String path = '${directory.path}/billares-don-miguel-update.apk';
    try {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Descargando actualización...')));
      client = HttpClient()..connectionTimeout = const Duration(seconds: 30);
      client.userAgent = 'Billares-Don-Miguel/1.2.6';
      final HttpClientRequest request = await client.getUrl(Uri.parse(url));
      request.headers.set(HttpHeaders.cacheControlHeader, 'no-cache');
      final HttpClientResponse response = await request.close();
      if (response.statusCode != 200) throw const HttpException('Descarga fallida');
      final File file = File(path);
      final IOSink sink = file.openWrite();
      await response.pipe(sink);
      await sink.flush();
      await sink.close();
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Error de descarga: no se pudo obtener la nueva versión.')));
      client?.close(force: true);
      return;
    } finally {
      client?.close(force: true);
    }

    try {
      if (!mounted) return;
      final ApkInstall installer = ApkInstall();
      final dynamic permission = await installer.onCheckInstallApkPermission();
      if (permission == false) {
        if (mounted) {
          await showDialog<void>(
            context: context,
            builder: (BuildContext context) => AlertDialog(
              title: const Text('Permiso de instalación'),
              content: const Text('Android necesita autorizar a Billares Don Miguel para instalar actualizaciones. Activa el permiso y vuelve a buscar la actualización.'),
              actions: <Widget>[TextButton(onPressed: () => Navigator.pop(context), child: const Text('Entendido'))],
            ),
          );
        }
        return;
      }
      await installer.onInstallApk(path);
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Error de instalación: Android no pudo iniciar la instalación.')));
    }
  }

  Future<void> changePassword()'''
s2 = pattern.sub(replacement, s, count=1)
if s2 == s:
    raise SystemExit('No se encontró downloadAndInstall para actualizar')
s = s2

# Las tarifas siguen siendo fijas y la administración no obtiene controles para editarlas.
if "const Map<int, double> tableRates = <int, double>{1: 120, 2: 120, 3: 100, 4: 100, 5: 70};" not in s:
    anchor = "const String updateManifestUrl"
    position = s.index(anchor)
    line_end = s.index('\n', position)
    s = s[:line_end + 1] + "const Map<int, double> tableRates = <int, double>{1: 120, 2: 120, 3: 100, 4: 100, 5: 70};\n" + s[line_end + 1:]

main.write_text(s)
print('OK: base funcional 1.2.6 preparada; dashboard/jornada/historial, LAN y OTA quedan listos para la reconstrucción TV/LAN/mDNS')
