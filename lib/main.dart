import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:apk_install/apk_install.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_background/flutter_background.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String appVersion = '1.2.3+123';
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

  void startGame() {
    status = TableStatus.playing;
    start = DateTime.now();
    end = null;
    amount = 0;
  }

  void finishGame() {
    if (start == null) return;
    end = DateTime.now();
    amount = liveAmount;
    status = TableStatus.pending;
  }

  void collect() {
    status = TableStatus.available;
    start = null;
    end = null;
    amount = 0;
  }
}

class HistoryEntry {
  HistoryEntry({
    required this.table,
    required this.start,
    required this.end,
    required this.amount,
  });

  final int table;
  final DateTime start;
  final DateTime end;
  final double amount;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'table': table,
        'start': start.toIso8601String(),
        'end': end.toIso8601String(),
        'amount': amount,
      };

  static HistoryEntry fromJson(Map<String, dynamic> json) => HistoryEntry(
        table: json['table'] as int,
        start: DateTime.parse(json['start'] as String),
        end: DateTime.parse(json['end'] as String),
        amount: (json['amount'] as num).toDouble(),
      );
}

class BillaresApp extends StatelessWidget {
  const BillaresApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Billares Don Miguel',
      theme: ThemeData(useMaterial3: true, colorSchemeSeed: Colors.green),
      home: const LoginPage(),
    );
  }
}

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final TextEditingController passwordController = TextEditingController();
  bool obscure = true;
  String password = defaultPassword;

  @override
  void initState() {
    super.initState();
    _loadPassword();
  }

  Future<void> _loadPassword() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    final String? saved = prefs.getString('admin_password');
    if (saved != null && saved.isNotEmpty) {
      if (mounted) setState(() => password = saved);
    }
  }

  Future<void> _login() async {
    if (passwordController.text != password) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Contraseña incorrecta')),
      );
      return;
    }
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => const DashboardPage()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Billares Don Miguel')),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                const Icon(Icons.sports_bar, size: 80),
                const SizedBox(height: 16),
                const Text('Acceso de administrador', style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
                const SizedBox(height: 24),
                TextField(
                  controller: passwordController,
                  obscureText: obscure,
                  decoration: InputDecoration(
                    labelText: 'Contraseña',
                    border: const OutlineInputBorder(),
                    suffixIcon: IconButton(
                      icon: Icon(obscure ? Icons.visibility : Icons.visibility_off),
                      onPressed: () => setState(() => obscure = !obscure),
                    ),
                  ),
                  onSubmitted: (_) => _login(),
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(onPressed: _login, child: const Text('Iniciar sesión')),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  final List<BillTable> tables = <BillTable>[
    BillTable(1, 120),
    BillTable(2, 120),
    BillTable(3, 100),
    BillTable(4, 100),
    BillTable(5, 70),
  ];
  final List<HistoryEntry> history = <HistoryEntry>[];
  Timer? timer;
  HttpServer? server;
  bool serverRunning = false;
  bool checkingUpdate = false;
  String? serverAddress;

  @override
  void initState() {
    super.initState();
    _loadHistory();
    timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
    _startLanServer();
  }

  @override
  void dispose() {
    timer?.cancel();
    server?.close(force: true);
    super.dispose();
  }

  Future<void> _loadHistory() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    final String? raw = prefs.getString('history');
    if (raw == null) return;
    try {
      final List<dynamic> data = jsonDecode(raw) as List<dynamic>;
      history
        ..clear()
        ..addAll(data.map((dynamic item) => HistoryEntry.fromJson(item as Map<String, dynamic>)));
      if (mounted) setState(() {});
    } catch (_) {}
  }

  Future<void> _saveHistory() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setString('history', jsonEncode(history.map((HistoryEntry e) => e.toJson()).toList()));
  }

  Future<void> _startLanServer() async {
    try {
      server = await HttpServer.bind(InternetAddress.anyIPv4, 8080, shared: true);
      serverRunning = true;
      serverAddress = await _localIp();
      server!.listen(_handleRequest);
      if (mounted) setState(() {});
    } catch (_) {
      serverRunning = false;
      if (mounted) setState(() {});
    }
  }

  Future<String?> _localIp() async {
    try {
      final List<NetworkInterface> interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);
      for (final NetworkInterface interface in interfaces) {
        for (final InternetAddress address in interface.addresses) {
          if (!address.isLoopback) return address.address;
        }
      }
    } catch (_) {}
    return null;
  }

  Future<void> _handleRequest(HttpRequest request) async {
    if (request.uri.path == '/tv') {
      request.response
        ..headers.contentType = ContentType.html
        ..headers.set('Cache-Control', 'no-store')
        ..write(_tvHtml());
      await request.response.close();
      return;
    }
    if (request.uri.path == '/api/state') {
      request.response
        ..headers.contentType = ContentType.json
        ..headers.set('Access-Control-Allow-Origin', '*')
        ..write(jsonEncode(_stateJson()));
      await request.response.close();
      return;
    }
    request.response
      ..statusCode = HttpStatus.notFound
      ..write('Not found');
    await request.response.close();
  }

  Map<String, dynamic> _stateJson() => <String, dynamic>{
        'appVersion': appVersion,
        'server': serverRunning,
        'tables': tables
            .map((BillTable table) => <String, dynamic>{
                  'number': table.number,
                  'rate': table.rate,
                  'status': table.statusText,
                  'elapsed': table.elapsedSeconds,
                  'amount': table.status == TableStatus.playing ? table.liveAmount : table.amount,
                })
            .toList(),
      };

  String _tvHtml() {
    return '''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Billares Don Miguel</title><style>body{font-family:Arial,sans-serif;margin:0;padding:20px;background:#111;color:#fff}h1{text-align:center}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}.card{padding:20px;border-radius:16px;background:#222;text-align:center}.num{font-size:32px;font-weight:700}.status{font-size:20px;margin:8px}.amount{font-size:28px;font-weight:700}</style></head><body><h1>Billares Don Miguel</h1><div id="grid" class="grid"></div><script>async function load(){try{const r=await fetch('/api/state?x='+Date.now());const d=await r.json();document.getElementById('grid').innerHTML=d.tables.map(t=>`<div class="card"><div class="num">Mesa ${t.number}</div><div class="status">${t.status}</div><div>${Math.floor(t.elapsed/3600)}h ${Math.floor(t.elapsed/60)%60}m ${t.elapsed%60}s</div><div class="amount">C$ ${Number(t.amount).toFixed(2)}</div></div>`).join('')}catch(e){}}load();setInterval(load,1000)</script></body></html>''';
  }

  Future<void> _finishTable(BillTable table) async {
    table.finishGame();
    if (table.start != null && table.end != null) {
      history.add(HistoryEntry(table: table.number, start: table.start!, end: table.end!, amount: table.amount));
      await _saveHistory();
    }
    if (mounted) setState(() {});
  }

  Future<void> _changePassword() async {
    final TextEditingController controller = TextEditingController();
    final String? value = await showDialog<String>(
      context: context,
      builder: (BuildContext context) => AlertDialog(
        title: const Text('Cambiar contraseña'),
        content: TextField(controller: controller, obscureText: true, autofocus: true, decoration: const InputDecoration(labelText: 'Nueva contraseña')),
        actions: <Widget>[
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(context, controller.text), child: const Text('Guardar')),
        ],
      ),
    );
    if (value == null || value.isEmpty) return;
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setString('admin_password', value);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Contraseña actualizada')));
    }
  }

  int buildNumber(String version) {
    final String value = version.split('+').last.trim();
    return int.tryParse(value) ?? 0;
  }

  Future<void> checkForUpdate({bool showNoUpdate = true}) async {
    if (checkingUpdate || !mounted) return;
    setState(() => checkingUpdate = true);
    HttpClient? client;
    try {
      client = HttpClient()..connectionTimeout = const Duration(seconds: 12);
      client.userAgent = 'Billares-Don-Miguel/1.2.3';
      final HttpClientRequest request = await client.getUrl(Uri.parse('$updateManifestUrl?x=${DateTime.now().millisecondsSinceEpoch}'));
      request.headers.set(HttpHeaders.cacheControlHeader, 'no-cache');
      final HttpClientResponse response = await request.close();
      if (response.statusCode != 200) throw const HttpException('Manifest no disponible');
      final Map<String, dynamic> manifest = jsonDecode(await response.transform(utf8.decoder).join()) as Map<String, dynamic>;
      final String latestVersion = manifest['version'] as String? ?? appVersion;
      final String? downloadUrl = (manifest['downloadUrl'] ?? manifest['apk_url']) as String?;
      if (buildNumber(latestVersion) <= buildNumber(appVersion) || downloadUrl == null || downloadUrl.isEmpty) {
        if (showNoUpdate && mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('La aplicación ya está actualizada')));
        return;
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Nueva versión disponible: $latestVersion')));
      await downloadAndInstall(downloadUrl);
    } catch (_) {
      if (showNoUpdate && mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo comprobar la actualización. La aplicación continúa funcionando normalmente.')));
    } finally {
      client?.close(force: true);
      if (mounted) setState(() => checkingUpdate = false);
    }
  }

  Future<void> downloadAndInstall(String url) async {
    HttpClient? client;
    try {
      client = HttpClient()..connectionTimeout = const Duration(seconds: 30);
      final HttpClientRequest request = await client.getUrl(Uri.parse(url));
      final HttpClientResponse response = await request.close();
      if (response.statusCode != 200) throw const HttpException('APK no disponible');
      final Directory dir = await getApplicationDocumentsDirectory();
      final String path = '${dir.path}/billares-don-miguel-update.apk';
      final File file = File(path);
      final IOSink sink = file.openWrite();
      await response.pipe(sink);
      await ApkInstall().onInstallApk(path);
    } finally {
      client?.close(force: true);
    }
  }

  double get dailyTotal {
    final DateTime now = DateTime.now();
    return history.where((HistoryEntry e) => e.end.year == now.year && e.end.month == now.month && e.end.day == now.day).fold<double>(0, (double sum, HistoryEntry e) => sum + e.amount);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Billares Don Miguel'),
        actions: <Widget>[
          IconButton(onPressed: _changePassword, tooltip: 'Cambiar contraseña', icon: const Icon(Icons.lock_reset)),
          IconButton(onPressed: checkingUpdate ? null : () => checkForUpdate(), tooltip: 'Buscar actualización', icon: const Icon(Icons.system_update)),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: <Widget>[
          Card(child: ListTile(title: const Text('Versión'), subtitle: Text(appVersion), trailing: serverRunning ? Text('TV: http://${serverAddress ?? 'IP' }:8080/tv') : const Text('TV desconectada'))),
          Card(child: ListTile(title: const Text('Total del día'), subtitle: Text('C\$ ${dailyTotal.toStringAsFixed(2)}'), leading: const Icon(Icons.payments))),
          const SizedBox(height: 8),
          ...tables.map(_tableCard),
        ],
      ),
    );
  }

  Widget _tableCard(BillTable table) {
    final bool playing = table.status == TableStatus.playing;
    final bool pending = table.status == TableStatus.pending;
    final double amount = playing ? table.liveAmount : table.amount;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text('Mesa ${table.number}', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
            Text('Tarifa fija: C\$ ${table.rate.toStringAsFixed(0)} / hora'),
            const SizedBox(height: 8),
            Text(table.statusText),
            if (playing) ...<Widget>[
              Text('${table.elapsedSeconds ~/ 3600}h ${(table.elapsedSeconds ~/ 60) % 60}m ${table.elapsedSeconds % 60}s'),
              Text('C\$ ${amount.toStringAsFixed(2)}', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            ],
            if (pending) Text('Cobrar: C\$ ${amount.toStringAsFixed(2)}', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: <Widget>[
                if (!playing && !pending) FilledButton.icon(onPressed: () => setState(table.startGame), icon: const Icon(Icons.play_arrow), label: const Text('Iniciar')),
                if (playing) FilledButton.icon(onPressed: () => _finishTable(table), icon: const Icon(Icons.stop), label: const Text('Finalizar')),
                if (pending) FilledButton.icon(onPressed: () => setState(table.collect), icon: const Icon(Icons.payments), label: const Text('Cobrar')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const BillaresApp());
}
