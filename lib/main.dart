import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:apk_install/apk_install.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_background/flutter_background.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String appVersion = '1.2.0+120';
const String defaultPassword = '1234';
const String updateManifestUrl = 'https://raw.githubusercontent.com/anparamo25-sketch/Billares-Don-Miguel-/main/update.json';
const Map<int, double> tableRates = <int, double>{1: 120, 2: 120, 3: 100, 4: 100, 5: 70};

enum TableStatus { available, playing, pending }

class BillTable {
  BillTable(this.number, this.rate);
  final int number;
  final double rate;
  TableStatus status = TableStatus.available;
  DateTime? start;
  DateTime? end;
  double amount = 0;

  int get elapsedSeconds {
    if (start == null) return 0;
    final DateTime finish = end ?? DateTime.now();
    return finish.difference(start!).inSeconds.clamp(0, 2147483647);
  }

  double get liveAmount => elapsedSeconds * rate / 3600;

  String get statusText {
    switch (status) {
      case TableStatus.available:
        return 'Disponible';
      case TableStatus.playing:
        return 'En juego';
      case TableStatus.pending:
        return 'Pendiente de cobro';
    }
  }

  Map<String, dynamic> toMap() => <String, dynamic>{
        'number': number,
        'status': status.name,
        'start': start?.toIso8601String(),
        'end': end?.toIso8601String(),
        'amount': amount,
      };

  void restore(Map<String, dynamic> map) {
    final String statusName = map['status'] as String? ?? TableStatus.available.name;
    status = TableStatus.values.firstWhere((TableStatus value) => value.name == statusName, orElse: () => TableStatus.available);
    start = map['start'] == null ? null : DateTime.tryParse(map['start'] as String);
    end = map['end'] == null ? null : DateTime.tryParse(map['end'] as String);
    amount = (map['amount'] as num?)?.toDouble() ?? 0;
  }
}

class HistoryEntry {
  HistoryEntry({required this.table, required this.start, required this.end, required this.seconds, required this.amount});
  final int table;
  final DateTime start;
  final DateTime end;
  final int seconds;
  final double amount;

  Map<String, dynamic> toMap() => <String, dynamic>{
        'table': table,
        'start': start.toIso8601String(),
        'end': end.toIso8601String(),
        'seconds': seconds,
        'amount': amount,
      };

  factory HistoryEntry.fromMap(Map<String, dynamic> map) => HistoryEntry(
        table: (map['table'] as num).toInt(),
        start: DateTime.parse(map['start'] as String),
        end: DateTime.parse(map['end'] as String),
        seconds: (map['seconds'] as num).toInt(),
        amount: (map['amount'] as num).toDouble(),
      );
}

void main() => runApp(const BillaresApp());

class BillaresApp extends StatelessWidget {
  const BillaresApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        debugShowCheckedModeBanner: false,
        title: 'Billares Don Miguel',
        theme: ThemeData(
          useMaterial3: true,
          brightness: Brightness.dark,
          scaffoldBackgroundColor: Colors.black,
          colorScheme: ColorScheme.fromSeed(seedColor: Colors.green, brightness: Brightness.dark),
          appBarTheme: const AppBarTheme(backgroundColor: Colors.black, foregroundColor: Colors.white),
          navigationBarTheme: const NavigationBarThemeData(backgroundColor: Color(0xff111111)),
        ),
        home: const LoginPage(),
      );
}

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final TextEditingController controller = TextEditingController();
  bool obscure = true;
  bool loading = true;
  String password = defaultPassword;

  @override
  void initState() {
    super.initState();
    restoreSession();
  }

  Future<void> restoreSession() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    password = prefs.getString('admin_password') ?? defaultPassword;
    final bool sessionActive = prefs.getBool('session_active') ?? false;
    if (!mounted) return;
    if (sessionActive) {
      Navigator.of(context).pushReplacement(MaterialPageRoute<void>(builder: (_) => const DashboardPage()));
      return;
    }
    setState(() => loading = false);
  }

  Future<void> login() async {
    if (controller.text != password) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Contraseña incorrecta')));
      controller.clear();
      return;
    }
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setBool('session_active', true);
    if (!mounted) return;
    Navigator.of(context).pushReplacement(MaterialPageRoute<void>(builder: (_) => const DashboardPage()));
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 430),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Card(
                color: const Color(0xff151515),
                child: Padding(
                  padding: const EdgeInsets.all(28),
                  child: loading
                      ? const SizedBox(height: 180, child: Center(child: CircularProgressIndicator()))
                      : Column(
                          mainAxisSize: MainAxisSize.min,
                          children: <Widget>[
                            const Icon(Icons.sports_bar, size: 64, color: Colors.green),
                            const SizedBox(height: 12),
                            const Text('Billares Don Miguel', style: TextStyle(fontSize: 27, fontWeight: FontWeight.bold)),
                            const SizedBox(height: 6),
                            const Text('CENTRAL • Administrador'),
                            const SizedBox(height: 28),
                            TextField(
                              controller: controller,
                              obscureText: obscure,
                              onSubmitted: (_) => login(),
                              decoration: InputDecoration(
                                labelText: 'Contraseña',
                                prefixIcon: const Icon(Icons.lock_outline),
                                suffixIcon: IconButton(
                                  tooltip: obscure ? 'Mostrar' : 'Ocultar',
                                  onPressed: () => setState(() => obscure = !obscure),
                                  icon: Icon(obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                                ),
                                border: const OutlineInputBorder(),
                              ),
                            ),
                            const SizedBox(height: 20),
                            SizedBox(width: double.infinity, height: 50, child: FilledButton.icon(onPressed: login, icon: const Icon(Icons.login), label: const Text('Ingresar'))),
                            const SizedBox(height: 14),
                            Text('Versión $appVersion'),
                          ],
                        ),
                ),
              ),
            ),
          ),
        ),
      );
}

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> with WidgetsBindingObserver {
  final List<BillTable> tableList = tableRates.entries.map((MapEntry<int, double> e) => BillTable(e.key, e.value)).toList();
  final TextEditingController newPassword = TextEditingController();
  final TextEditingController confirmPassword = TextEditingController();
  List<HistoryEntry> history = <HistoryEntry>[];
  HttpServer? server;
  Timer? ticker;
  String? lanIp;
  int tab = 0;
  bool checkingUpdate = false;
  bool backgroundStarted = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    loadData();
    startLanServer();
    startBackgroundExecution();
    ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
    Future<void>.delayed(const Duration(seconds: 2), () => checkForUpdate(showNoUpdate: false));
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && !backgroundStarted) {
      startBackgroundExecution();
    }
  }

  Future<void> startBackgroundExecution() async {
    if (backgroundStarted) return;
    try {
      final bool initialized = await FlutterBackground.initialize(
        androidConfig: const FlutterBackgroundAndroidConfig(
          notificationTitle: 'Billares Don Miguel',
          notificationText: 'CENTRAL activo en segundo plano',
          notificationImportance: AndroidNotificationImportance.low,
          enableWifiLock: true,
        ),
      );
      if (initialized) {
        backgroundStarted = await FlutterBackground.enableBackgroundExecution();
      }
    } catch (_) {
      backgroundStarted = false;
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    ticker?.cancel();
    server?.close(force: true);
    newPassword.dispose();
    confirmPassword.dispose();
    super.dispose();
  }

  Future<void> loadData() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    final String? rawHistory = prefs.getString('history');
    final DateTime cutoff = DateTime.now().subtract(const Duration(days: 7));
    if (rawHistory != null && rawHistory.isNotEmpty) {
      try {
        final List<dynamic> data = jsonDecode(rawHistory) as List<dynamic>;
        history = data.map((dynamic item) => HistoryEntry.fromMap(Map<String, dynamic>.from(item as Map))).where((HistoryEntry e) => e.end.isAfter(cutoff)).toList();
      } catch (_) {
        history = <HistoryEntry>[];
      }
    }
    final String? rawTables = prefs.getString('tables');
    if (rawTables != null && rawTables.isNotEmpty) {
      try {
        final List<dynamic> data = jsonDecode(rawTables) as List<dynamic>;
        for (final dynamic item in data) {
          final Map<String, dynamic> map = Map<String, dynamic>.from(item as Map);
          final int number = (map['number'] as num).toInt();
          final BillTable table = tableList.firstWhere((BillTable t) => t.number == number);
          table.restore(map);
        }
      } catch (_) {
        // Keep the safe default state if persisted table data is damaged.
      }
    }
    await saveHistory();
    await saveTables();
    if (mounted) setState(() {});
  }

  Future<void> saveHistory() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setString('history', jsonEncode(history.map((HistoryEntry e) => e.toMap()).toList()));
  }

  Future<void> saveTables() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setString('tables', jsonEncode(tableList.map((BillTable t) => t.toMap()).toList()));
  }

  Future<void> startLanServer() async {
    try {
      server = await HttpServer.bind(InternetAddress.anyIPv4, 8080, shared: true);
      final List<NetworkInterface> interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);
      for (final NetworkInterface networkInterface in interfaces) {
        for (final InternetAddress address in networkInterface.addresses) {
          if (!address.isLoopback) {
            lanIp = address.address;
            break;
          }
        }
        if (lanIp != null) break;
      }
      server!.listen(handleRequest);
      if (mounted) setState(() {});
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo iniciar el servidor LAN en el puerto 8080')));
      }
    }
  }

  Future<void> handleRequest(HttpRequest request) async {
    request.response.headers.set('Access-Control-Allow-Origin', '*');
    request.response.headers.set('Cache-Control', 'no-store');
    if (request.uri.path == '/api/state') {
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode(stateMap()));
    } else {
      request.response.headers.contentType = ContentType.html;
      request.response.write(tvHtml);
    }
    await request.response.close();
  }

  Map<String, dynamic> stateMap() => <String, dynamic>{
        'app': 'Billares Don Miguel',
        'version': appVersion,
        'time': clock(DateTime.now()),
        'tables': tableList.map((BillTable t) => <String, dynamic>{
              'number': t.number,
              'rate': t.rate,
              'status': t.statusText,
              'start': t.start == null ? null : clock(t.start!),
              'end': t.end == null ? null : clock(t.end!),
              'elapsed': duration(t.elapsedSeconds),
              'amount': t.status == TableStatus.available ? 0 : t.status == TableStatus.playing ? t.liveAmount : t.amount,
            }).toList(),
      };

  String get tvHtml => r'''<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Billares Don Miguel</title>
<style>body{margin:0;background:#000;color:#fff;font-family:Arial,sans-serif}header{padding:20px;text-align:center;background:#050505;position:sticky;top:0;border-bottom:1px solid #222}h1{margin:0;font-size:30px}.clock{font-size:20px;margin-top:6px;color:#d9f99d}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px;padding:22px}.card{border-radius:18px;padding:22px;background:#151515;border:2px solid #444;box-shadow:0 8px 30px #000}.card.green{background:#123d24;border-color:#36d76b}.card.red{background:#541b1b;border-color:#ff5252}.card.yellow{background:#5a4a08;border-color:#f5c542}.name{font-size:28px;font-weight:800}.status{margin:10px 0;font-size:20px;font-weight:700}.line{margin:8px 0;color:#f0f7f2}.money{font-size:30px;font-weight:800;margin-top:14px}</style></head>
<body><header><h1>BILLARES DON MIGUEL</h1><div id="clock" class="clock">Conectando...</div></header><main id="grid" class="grid"></main>
<script>function money(n){return 'C$ '+Number(n).toFixed(2)}function render(d){document.getElementById('clock').textContent=d.time;document.getElementById('grid').innerHTML=d.tables.map(function(t){var c=t.status==='Disponible'?'green':t.status==='En juego'?'red':'yellow';return '<section class="card '+c+'"><div class="name">Mesa '+t.number+'</div><div class="status">'+t.status+'</div><div class="line">Inicio: '+(t.start||'—')+'</div><div class="line">Finalización: '+(t.end||'—')+'</div><div class="line">Tiempo jugado: '+t.elapsed+'</div><div class="money">'+money(t.amount)+'</div></section>'}).join('')}async function tick(){try{var r=await fetch('/api/state?x='+Date.now());render(await r.json())}catch(e){document.getElementById('clock').textContent='Sin conexión con CENTRAL'}}tick();setInterval(tick,1000)</script></body></html>''';

  Future<void> startGame(BillTable table) async {
    if (table.status != TableStatus.available) return;
    setState(() {
      table.status = TableStatus.playing;
      table.start = DateTime.now();
      table.end = null;
      table.amount = 0;
    });
    await saveTables();
  }

  Future<void> finishGame(BillTable table) async {
    if (table.status != TableStatus.playing) return;
    setState(() {
      table.end = DateTime.now();
      table.amount = table.liveAmount;
      table.status = TableStatus.pending;
    });
    await saveTables();
  }

  Future<void> collect(BillTable table) async {
    if (table.status != TableStatus.pending || table.start == null || table.end == null) return;
    final HistoryEntry entry = HistoryEntry(table: table.number, start: table.start!, end: table.end!, seconds: table.end!.difference(table.start!).inSeconds, amount: table.amount);
    setState(() {
      history.add(entry);
      table.status = TableStatus.available;
      table.start = null;
      table.end = null;
      table.amount = 0;
    });
    await saveHistory();
    await saveTables();
  }

  Future<void> showTvConnection() async {
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
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const Text('El botón anterior abría el navegador del mismo dispositivo. Esta versión ya no hace eso.'),
            const SizedBox(height: 12),
            const Text('En el navegador del televisor, conectado a la misma Wi‑Fi, abre esta dirección:'),
            const SizedBox(height: 12),
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
            const SizedBox(height: 8),
            const Text('Una vez abierta, la TV queda conectada a CENTRAL y se actualiza automáticamente cada segundo.'),
          ],
        ),
        actions: <Widget>[
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cerrar')),
        ],
      ),
    );
  }

  int buildNumber(String version) {
    final String value = version.split('+').last.trim();
    return int.tryParse(value) ?? 0;
  }

  Future<void> checkForUpdate({bool showNoUpdate = true}) async {
    if (checkingUpdate || !mounted) return;
    setState(() => checkingUpdate = true);
    try {
      final HttpClient client = HttpClient()..connectionTimeout = const Duration(seconds: 8);
      final HttpClientRequest request = await client.getUrl(Uri.parse('$updateManifestUrl?x=${DateTime.now().millisecondsSinceEpoch}'));
      request.headers.set(HttpHeaders.cacheControlHeader, 'no-cache');
      final HttpClientResponse response = await request.close();
      if (response.statusCode != 200) throw const HttpException('Manifest no disponible');
      final Map<String, dynamic> manifest = jsonDecode(await response.transform(utf8.decoder).join()) as Map<String, dynamic>;
      client.close(force: true);
      final String latestVersion = manifest['version'] as String? ?? appVersion;
      final String? downloadUrl = (manifest['downloadUrl'] ?? manifest['apk_url']) as String?;
      if (buildNumber(latestVersion) <= buildNumber(appVersion) || downloadUrl == null || downloadUrl.isEmpty) {
        if (showNoUpdate && mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('La aplicación ya está actualizada')));
        return;
      }
      if (!mounted) return;
      final bool? install = await showDialog<bool>(
        context: context,
        builder: (BuildContext context) => AlertDialog(
          title: const Text('Nueva actualización disponible'),
          content: Text('Hay una nueva versión ($latestVersion). ¿Deseas actualizar ahora?'),
          actions: <Widget>[
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Más tarde')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Actualizar ahora')),
          ],
        ),
      );
      if (install == true) await downloadAndInstall(downloadUrl);
    } catch (_) {
      if (showNoUpdate && mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo comprobar la actualización. La aplicación continúa funcionando normalmente.')));
    } finally {
      if (mounted) setState(() => checkingUpdate = false);
    }
  }

  Future<void> downloadAndInstall(String url) async {
    try {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Descargando actualización...')));
      final Directory directory = await getApplicationDocumentsDirectory();
      final String path = '${directory.path}/billares-don-miguel-update.apk';
      final HttpClient client = HttpClient()..connectionTimeout = const Duration(seconds: 20);
      final HttpClientResponse response = await (await client.getUrl(Uri.parse(url))).close();
      if (response.statusCode != 200) throw const HttpException('Descarga fallida');
      final File file = File(path);
      final IOSink sink = file.openWrite();
      await response.pipe(sink);
      await sink.flush();
      await sink.close();
      client.close(force: true);
      await ApkInstall().onInstallApk(path);
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo descargar o iniciar la instalación de la actualización.')));
    }
  }

  Future<void> changePassword() async {
    newPassword.clear();
    confirmPassword.clear();
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) => AlertDialog(
        title: const Text('Cambiar contraseña'),
        content: Column(mainAxisSize: MainAxisSize.min, children: <Widget>[
          TextField(controller: newPassword, obscureText: true, decoration: const InputDecoration(labelText: 'Nueva contraseña')),
          const SizedBox(height: 12),
          TextField(controller: confirmPassword, obscureText: true, decoration: const InputDecoration(labelText: 'Confirmar contraseña')),
        ]),
        actions: <Widget>[
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(context, newPassword.text.isNotEmpty && newPassword.text == confirmPassword.text), child: const Text('Guardar')),
        ],
      ),
    );
    if (saved == true) {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      await prefs.setString('admin_password', newPassword.text);
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Contraseña actualizada')));
    } else if (saved == false && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Las contraseñas no coinciden o están vacías')));
    }
  }

  Future<void> logout() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setBool('session_active', false);
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute<void>(builder: (_) => const LoginPage()), (_) => false);
  }

  String clock(DateTime value) {
    final int hour = value.hour % 12 == 0 ? 12 : value.hour % 12;
    final String minute = value.minute.toString().padLeft(2, '0');
    final String second = value.second.toString().padLeft(2, '0');
    return '$hour:$minute:$second ${value.hour >= 12 ? 'PM' : 'AM'}';
  }

  String date(DateTime value) => '${value.day.toString().padLeft(2, '0')}/${value.month.toString().padLeft(2, '0')}/${value.year}';

  String duration(int seconds) {
    final int h = seconds ~/ 3600;
    final int m = (seconds % 3600) ~/ 60;
    final int s = seconds % 60;
    return '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  String money(double value) => 'C\$${value.toStringAsFixed(2)}';

  double get todayTotal {
    final DateTime now = DateTime.now();
    return history.where((HistoryEntry e) => e.end.year == now.year && e.end.month == now.month && e.end.day == now.day).fold<double>(0, (double total, HistoryEntry e) => total + e.amount);
  }

  Color statusColor(TableStatus status) {
    switch (status) {
      case TableStatus.available:
        return Colors.green.shade100;
      case TableStatus.playing:
        return Colors.red.shade100;
      case TableStatus.pending:
        return Colors.yellow.shade200;
    }
  }

  Color statusTextColor(TableStatus status) {
    switch (status) {
      case TableStatus.available:
        return Colors.green.shade900;
      case TableStatus.playing:
        return Colors.red.shade900;
      case TableStatus.pending:
        return Colors.orange.shade900;
    }
  }

  Widget tableCard(BillTable table) {
    final double amount = table.status == TableStatus.playing ? table.liveAmount : table.amount;
    final String buttonText = table.status == TableStatus.available ? 'Iniciar' : table.status == TableStatus.playing ? 'Finalizar' : 'Cobrar';
    final Future<void> Function() action = table.status == TableStatus.available ? () => startGame(table) : table.status == TableStatus.playing ? () => finishGame(table) : () => collect(table);
    return Card(
      elevation: 3,
      color: statusColor(table.status),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
          Row(children: <Widget>[
            Expanded(child: Text('Mesa ${table.number}', style: TextStyle(fontSize: 23, fontWeight: FontWeight.bold, color: statusTextColor(table.status)))),
            Chip(label: Text(table.statusText, style: TextStyle(color: statusTextColor(table.status))), avatar: CircleAvatar(backgroundColor: statusTextColor(table.status), radius: 6)),
          ]),
          Divider(color: statusTextColor(table.status).withValues(alpha: 0.35)),
          Text('Tarifa fija: ${money(table.rate)} / hora', style: TextStyle(color: statusTextColor(table.status))),
          const SizedBox(height: 8),
          Text('Inicio: ${table.start == null ? '—' : clock(table.start!)}', style: TextStyle(color: statusTextColor(table.status))),
          Text('Finalización: ${table.end == null ? '—' : clock(table.end!)}', style: TextStyle(color: statusTextColor(table.status))),
          Text('Tiempo jugado: ${duration(table.elapsedSeconds)}', style: TextStyle(color: statusTextColor(table.status))),
          const SizedBox(height: 8),
          Text(money(amount), style: TextStyle(fontSize: 26, fontWeight: FontWeight.bold, color: statusTextColor(table.status))),
          const SizedBox(height: 12),
          SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: action, icon: Icon(table.status == TableStatus.playing ? Icons.stop : Icons.play_arrow), label: Text(buttonText))),
        ]),
      ),
    );
  }

  Widget dashboard() => Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
          Row(children: <Widget>[
            Expanded(child: Text('Estado de mesas', style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold))),
            if (lanIp != null) Chip(label: Text('LAN: $lanIp:8080')),
          ]),
          const SizedBox(height: 8),
          if (lanIp != null) Text('TV: http://$lanIp:8080/tv', style: const TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 10),
          SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: showTvConnection, icon: const Icon(Icons.tv), label: const Text('Conectar televisor'))),
          const SizedBox(height: 12),
          Expanded(child: GridView.builder(
            gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(maxCrossAxisExtent: 460, mainAxisExtent: 330, crossAxisSpacing: 14, mainAxisSpacing: 14),
            itemCount: tableList.length,
            itemBuilder: (_, int index) => tableCard(tableList[index]),
          )),
        ]),
      );

  Widget historyPage() {
    final List<HistoryEntry> items = List<HistoryEntry>.from(history)..sort((HistoryEntry a, HistoryEntry b) => b.end.compareTo(a.end));
    return Column(children: <Widget>[
      Card(margin: const EdgeInsets.fromLTRB(16, 16, 16, 8), child: ListTile(leading: const Icon(Icons.today), title: const Text('Total de hoy'), trailing: Text(money(todayTotal), style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)))),
      Expanded(child: items.isEmpty
          ? const Center(child: Text('No hay movimientos en los últimos 7 días.'))
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: items.length,
              itemBuilder: (_, int index) {
                final HistoryEntry e = items[index];
                return Card(child: ListTile(leading: CircleAvatar(child: Text('${e.table}')), title: Text('Mesa ${e.table} • ${money(e.amount)}'), subtitle: Text('${date(e.end)} • ${clock(e.start)} - ${clock(e.end)} • ${duration(e.seconds)}')));
              },
            )),
    ]);
  }

  void showSettings() {
    showDialog<void>(
      context: context,
      builder: (BuildContext context) => AlertDialog(
        title: const Text('Configuración'),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
          const Text('Tarifas fijas', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          const Text('Mesas 1 y 2: C\$120 por hora'),
          const Text('Mesas 3 y 4: C\$100 por hora'),
          const Text('Mesa 5: C\$70 por hora'),
          const SizedBox(height: 12),
          const Text('Las tarifas no pueden modificarse desde el administrador.'),
          const SizedBox(height: 16),
          if (lanIp != null) Text('Servidor LAN: http://$lanIp:8080/tv'),
        ]),
        actions: <Widget>[
          TextButton(onPressed: changePassword, child: const Text('Cambiar contraseña')),
          TextButton(onPressed: () => checkForUpdate(), child: const Text('Buscar actualización')),
          FilledButton(onPressed: () => Navigator.pop(context), child: const Text('Cerrar')),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Billares Don Miguel', style: TextStyle(fontWeight: FontWeight.bold)),
          actions: <Widget>[
            if (checkingUpdate) const Padding(padding: EdgeInsets.symmetric(horizontal: 12), child: Center(child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)))),
            IconButton(tooltip: 'Configuración', onPressed: showSettings, icon: const Icon(Icons.settings_outlined)),
            IconButton(tooltip: 'Cerrar sesión', onPressed: logout, icon: const Icon(Icons.logout)),
          ],
        ),
        body: tab == 0 ? dashboard() : historyPage(),
        bottomNavigationBar: NavigationBar(
          selectedIndex: tab,
          onDestinationSelected: (int index) => setState(() => tab = index),
          destinations: const <NavigationDestination>[
            NavigationDestination(icon: Icon(Icons.table_restaurant), label: 'Mesas'),
            NavigationDestination(icon: Icon(Icons.history), label: 'Historial'),
          ],
        ),
      );
}
