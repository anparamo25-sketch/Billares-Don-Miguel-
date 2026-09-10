import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:apk_install/apk_install.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_background/flutter_background.dart';
import 'package:path_provider/path_provider.dart';
import 'package:print_bluetooth_thermal_plus/print_bluetooth_thermal.dart';
import 'package:esc_pos_utils_plus/esc_pos_utils_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'cloud_tv_sync.dart';

const String appVersion = '1.2.9+129';
const String defaultPassword = '1234';
const String updateManifestUrl = 'https://github.com/anparamo25-sketch/Billares-Don-Miguel-/raw/refs/heads/main/update.json';
const Map<int, double> tableRates = <int, double>{1: 120, 2: 120, 3: 100, 4: 100, 5: 70};

enum TableStatus { available, playing, pending }

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
    final List<int> query = datagram.data;
    if (query.length < 12) return;
    final int questions = (query[4] << 8) | query[5];
    var offset = 12;
    var matched = false;
    for (var i = 0; i < questions; i++) {
      final labels = <String>[];
      while (offset < query.length) {
        final int length = query[offset++];
        if (length == 0) break;
        if (length > 63 || offset + length > query.length) return;
        labels.add(String.fromCharCodes(query.sublist(offset, offset + length)));
        offset += length;
      }
      if (offset + 4 > query.length) return;
      final int type = (query[offset] << 8) | query[offset + 1];
      offset += 4;
      if (labels.join('.').toLowerCase() == 'billaresdonmiguel.local' && (type == 1 || type == 255)) matched = true;
    }
    if (!matched) return;
    final String? ip = await _billaresLocalIp();
    if (ip == null) return;
    final List<int> octets = ip.split('.').map(int.parse).toList();
    if (octets.length != 4) return;

    final response = <int>[];
    response.addAll(query.sublist(0, 2));
    response.addAll(<int>[0x84, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]);
    response.addAll(<int>[0xC0, 0x0C]);
    response.addAll(<int>[0x00, 0x01, 0x00, 0x01]);
    response.addAll(<int>[0x00, 0x00, 0x00, 0x78]);
    response.addAll(<int>[0x00, 0x04]);
    response.addAll(octets);
    socket.send(response, InternetAddress('224.0.0.251'), 5353);
    if (datagram.address.address != '224.0.0.251' || datagram.port != 5353) {
      socket.send(response, datagram.address, datagram.port);
    }
  } catch (_) {}
}
Future<void> _startBillaresMdns() async {
  try {
    _billaresMdnsSocket?.close();
    final RawDatagramSocket socket = await RawDatagramSocket.bind(
      InternetAddress.anyIPv4,
      5353,
      reuseAddress: true,
      reusePort: true,
    );
    _billaresMdnsSocket = socket;
    socket.broadcastEnabled = true;
    socket.joinMulticast(InternetAddress('224.0.0.251'));
    socket.listen((RawSocketEvent event) {
      if (event != RawSocketEvent.read) return;
      final Datagram? datagram = socket.receive();
      if (datagram != null) {
        _answerBillaresMdns(socket, datagram);
      }
    });
    try {
      await const MethodChannel('billaresdonmiguel/network').invokeMethod<void>('acquireMulticastLock');
    } catch (_) {}
  } catch (_) {}
}

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
  HistoryEntry({required this.table, required this.start, required this.end, required this.seconds, required this.amount, DateTime? workDate}) : workDate = DateTime((workDate ?? end).year, (workDate ?? end).month, (workDate ?? end).day);
  final int table;
  final DateTime workDate;
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
        'workDate': workDate.toIso8601String(),
      };

  factory HistoryEntry.fromMap(Map<String, dynamic> map) => HistoryEntry(
        table: (map['table'] as num).toInt(),
        start: DateTime.parse(map['start'] as String),
        end: DateTime.parse(map['end'] as String),
        seconds: (map['seconds'] as num).toInt(),
        amount: (map['amount'] as num).toDouble(),
        workDate: DateTime.tryParse(map['workDate'] as String? ?? map['end'] as String),
      );
}

void main() => runApp(const BillaresApp());

class BillaresApp extends StatelessWidget {
  const BillaresApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Billares Don Miguel',
      theme: ThemeData(
        brightness: Brightness.dark,
        useMaterial3: true,
        colorSchemeSeed: Colors.blue,
      ),
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
Timer? ticker;
int tab = 0;
  bool checkingUpdate = false;
  bool backgroundStarted = false;
  bool workdayActive = false;
  DateTime? workdayOpenedAt;
  DateTime? workdayClosedAt;
  double workdayGenerated = 0;
  double workdayCashClose = 0;
  int workdayGames = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    loadData();
    startLanServer();
    startBackgroundExecution();
    ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
      publishCloudTvState(tableList.map((BillTable t) => <String, dynamic>{
        'number': t.number,
        'status': t.status.name,
        'start': t.start?.toIso8601String(),
        'end': t.end?.toIso8601String(),
        'amount': t.status == TableStatus.playing ? t.liveAmount : t.amount,
        'rate': t.rate,
      }).toList());
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
          notificationImportance: AndroidNotificationImportance.normal,
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
    disposeCloudTvSync();
    newPassword.dispose();
    confirmPassword.dispose();
    super.dispose();
  }

  Future<void> loadData() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    workdayActive = prefs.getBool('workday_active') ?? false;
    final String? opened = prefs.getString('workday_opened_at');
    final String? closed = prefs.getString('workday_closed_at');
    workdayOpenedAt = opened == null ? null : DateTime.tryParse(opened);
    workdayClosedAt = closed == null ? null : DateTime.tryParse(closed);
    workdayGenerated = prefs.getDouble('workday_generated') ?? 0;
    workdayCashClose = prefs.getDouble('workday_cash_close') ?? 0;
    workdayGames = prefs.getInt('workday_games') ?? 0;
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

  Future<void> saveWorkday() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setBool('workday_active', workdayActive);
    if (workdayOpenedAt != null) {
      await prefs.setString('workday_opened_at', workdayOpenedAt!.toIso8601String());
    } else {
      await prefs.remove('workday_opened_at');
    }
    if (workdayClosedAt != null) {
      await prefs.setString('workday_closed_at', workdayClosedAt!.toIso8601String());
    } else {
      await prefs.remove('workday_closed_at');
    }
    await prefs.setDouble('workday_generated', workdayGenerated);
    await prefs.setDouble('workday_cash_close', workdayCashClose);
    await prefs.setInt('workday_games', workdayGames);
  }

  Future<void> openWorkday() async {
    if (workdayActive) return;
    setState(() {
      workdayActive = true;
      workdayOpenedAt = DateTime.now();
      workdayClosedAt = null;
      workdayGenerated = 0;
      workdayCashClose = 0;
      workdayGames = 0;
    });
    await saveWorkday();
  }

  Future<void> closeWorkday() async {
    if (!workdayActive) return;
    final TextEditingController cashController = TextEditingController();
    final double generated = workdayGenerated;
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) => AlertDialog(
        title: const Text('Cerrar día'),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
          Text('Juegos: $workdayGames'),
          Text('Total generado: ${money(generated)}'),
          const SizedBox(height: 12),
          TextField(controller: cashController, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Efectivo físico al cierre', prefixText: 'C\$ ')),
        ]),
        actions: <Widget>[
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(context, double.tryParse(cashController.text.replaceAll(',', '.')) != null), child: const Text('Registrar cierre')),
        ],
      ),
    );
    final double? cash = double.tryParse(cashController.text.replaceAll(',', '.'));
    cashController.dispose();
    if (confirmed != true || cash == null) return;
    setState(() {
      workdayActive = false;
      workdayClosedAt = DateTime.now();
      workdayCashClose = cash;
    });
    await saveWorkday();
  }

  Future<void> saveTables() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setString('tables', jsonEncode(tableList.map((BillTable t) => t.toMap()).toList()));
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
    } else if (request.uri.path == '/tv' || request.uri.path == '/') {
      response.headers.contentType = ContentType.html;
      response.headers.contentLength = utf8.encode(tvHtml).length;
      response.write(tvHtml);
    } else {
      response.statusCode = HttpStatus.notFound;
      response.headers.contentType = ContentType.text;
      response.write('Not found');
    }
    await response.close();
  }

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
  String get tvHtml => "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta http-equiv=\"Cache-Control\" content=\"no-store, no-cache, must-revalidate, max-age=0\"><meta http-equiv=\"Pragma\" content=\"no-cache\"><meta http-equiv=\"Expires\" content=\"0\"><title>Billares Don Miguel - TV</title><style>*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#05070b;color:#fff;font-family:Arial,sans-serif}.wrap{width:100%;height:100vh;padding:0 20px 16px;display:flex;flex-direction:column;overflow:hidden}header{height:112px;flex:0 0 112px;padding:12px 4px;background:#fff;border-bottom:3px solid #1557c0;display:grid;grid-template-columns:1fr auto 1fr;align-items:center}.brandLogo{justify-self:start;display:flex;align-items:center;gap:10px;color:#1557c0;font-weight:900}.logoSvg{width:68px;height:68px;display:block;flex:none}.word{font-size:18px;letter-spacing:.5px}.brandTitle{justify-self:center}.brandTitle h1{margin:0;font-size:clamp(32px,4.5vw,54px);line-height:1;color:#1557c0;text-align:center;text-shadow:0 2px 3px rgba(0,0,0,.18)}.liveBox{justify-self:end;text-align:center;color:#1557c0}.clock{font-size:clamp(18px,2vw,28px);font-weight:900;line-height:1.1}.live{font-size:clamp(16px,1.8vw,25px);font-weight:900;margin-top:5px}.grid{width:100%;flex:1;min-height:0;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:16px;padding:16px 0 0;overflow:hidden}.card{height:100%;min-height:0;border-radius:18px;padding:18px;border:3px solid #64748b;display:flex;flex-direction:column;box-shadow:0 8px 18px rgba(0,0,0,.25);overflow:hidden}.green{background:#103b22;border-color:#22c55e}.red{background:#511b1b;border-color:#ef4444}.yellow{background:#56490a;border-color:#eab308}.num{font-size:clamp(24px,2.7vw,38px);font-weight:900;line-height:1.05}.status{font-size:clamp(18px,2vw,27px);font-weight:900;margin:7px 0 12px;line-height:1.05}.green .status{color:#4ade80}.red .status{color:#f87171}.yellow .status{color:#fde047}.rate{font-size:clamp(17px,1.7vw,24px);font-weight:900;margin-bottom:8px;line-height:1.1}.line{font-size:clamp(18px,1.7vw,24px);font-weight:700;line-height:1.3;margin:5px 0}.pay{margin-top:auto;padding-top:11px;border-top:2px solid rgba(255,255,255,.25)}.payLabel{font-size:clamp(15px,1.5vw,21px);font-weight:900;letter-spacing:.5px}.money{font-size:clamp(30px,3.2vw,46px);font-weight:900;margin-top:3px;line-height:1.05}@media(max-height:700px){header{height:92px;flex-basis:92px}.wrap{padding:0 14px 10px}.grid{gap:10px;padding-top:10px}.card{padding:13px;border-radius:14px}.status{margin:5px 0 8px}.line{margin:3px 0;font-size:clamp(16px,1.6vw,22px)}.rate{margin-bottom:5px}.logoSvg{width:56px;height:56px}.word{font-size:15px}}@media(max-width:1200px) and (min-height:701px){.wrap{padding-left:14px;padding-right:14px}.grid{gap:10px}.card{padding:14px}.line{font-size:clamp(16px,1.6vw,22px)}}</style></head><body><main class=\"wrap\"><header><div class=\"brandLogo\"><svg class=\"logoSvg\" viewBox=\"0 0 100 100\" aria-label=\"Logo Billares Don Miguel\" role=\"img\"><circle cx=\"50\" cy=\"50\" r=\"45\" fill=\"#1557c0\"/><circle cx=\"50\" cy=\"50\" r=\"37\" fill=\"#fff\"/><path d=\"M29 66V34h15c10 0 16 5 16 12 0 4-2 7-5 9 5 2 8 5 8 10 0 9-7 15-19 15H29zm10-20h5c4 0 6-1 6-4 0-3-2-4-6-4h-5v8zm0 15h8c4 0 7-2 7-5s-3-5-7-5h-8v10z\" fill=\"#1557c0\" transform=\"translate(0,-5)\"/><path d=\"M18 76h64\" stroke=\"#1557c0\" stroke-width=\"5\" stroke-linecap=\"round\"/><circle cx=\"24\" cy=\"76\" r=\"5\" fill=\"#1557c0\"/><circle cx=\"76\" cy=\"76\" r=\"5\" fill=\"#1557c0\"/></svg><div class=\"word\">BILLARES</div></div><div class=\"brandTitle\"><h1>Billares Don Miguel</h1></div><div class=\"liveBox\"><div id=\"clock\" class=\"clock\">--:-- PM</div><div class=\"live\">🟢 EN VIVO</div></div></header><section id=\"tables\" class=\"grid\"></section></main><script>const rates={1:120,2:120,3:100,4:100,5:70};function safe(v){return v==null||v===''?'—':String(v)}function money(v){return 'C\$ '+Number(v||0).toFixed(2)}function clockValue(v){if(!v)return '—';var d=new Date(v);if(isNaN(d.getTime()))return String(v);return d.toLocaleTimeString('es-NI',{hour:'2-digit',minute:'2-digit',hour12:true})}function statusName(v){return v==='playing'?'En juego':v==='pending'?'Pendiente de cobro':v==='available'?'Disponible':safe(v)}function elapsedValue(start,end){if(!start)return '00:00:00';var a=new Date(start);var b=end?new Date(end):new Date();if(isNaN(a.getTime())||isNaN(b.getTime()))return '00:00:00';var sec=Math.max(0,Math.floor((b-a)/1000));var h=Math.floor(sec/3600);var m=Math.floor((sec%3600)/60);var ss=sec%60;return String(h).padStart(2,'0')+':'+String(m).padStart(2,'0')+':'+String(ss).padStart(2,'0')}function render(d){document.getElementById('clock').textContent=d.time||new Date().toLocaleTimeString('es-NI',{hour:'2-digit',minute:'2-digit',hour12:true});var tables=d.tables||[];document.getElementById('tables').innerHTML=[1,2,3,4,5].map(function(i){var t=tables.find(function(x){return Number(x.number)===i})||{number:i,status:'available',rate:rates[i],amount:0};var s=statusName(t.status);var c=s==='En juego'?'red':s==='Pendiente de cobro'?'yellow':'green';return '<article class=\"card '+c+'\"><div class=\"num\">Mesa '+i+'</div><div class=\"status\">'+safe(s)+'</div><div class=\"rate\">Tarifa por hora: '+money(t.rate??rates[i])+'</div><div class=\"line\"><b>Hora de inicio:</b> '+(t.start&&t.start.indexOf('T')>0?clockValue(t.start):safe(t.start))+'</div><div class=\"line\"><b>Tiempo jugado:</b> '+elapsedValue(t.start,t.end)+'</div><div class=\"line\"><b>Hora finalizada:</b> '+(t.end&&t.end.indexOf('T')>0?clockValue(t.end):safe(t.end))+'</div><div class=\"pay\"><div class=\"payLabel\">MONTO A PAGAR</div><div class=\"money\">'+money(t.amount)+'</div></div></article>'}).join('')}async function tick(){try{var r=await fetch('/api/state?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);render(await r.json())}catch(e){}}function updateClock(){var el=document.getElementById('clock');if(el)el.textContent=new Date().toLocaleTimeString('es-NI',{hour:'2-digit',minute:'2-digit',hour12:true})}render({tables:[]});updateClock();tick();setInterval(tick,1000);setInterval(updateClock,1000);</script></body></html>";

Map<String, dynamic> stateMap() => <String, dynamic>{
        'app': 'Billares Don Miguel',
        'version': appVersion,
        'time': clock(DateTime.now()),
        'tables': tableList.map((BillTable t) => <String, dynamic>{
              'number': t.number,
              'rate': t.rate,
              'status': t.statusText,
              'start': t.start == null ? null : t.start!.toIso8601String(),
              'end': t.end == null ? null : t.end!.toIso8601String(),
              'elapsed': duration(t.elapsedSeconds),
              'amount': t.status == TableStatus.available ? 0 : t.status == TableStatus.playing ? t.liveAmount : t.amount,
            }).toList(),
      };


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

  Future<void> printReceipt(BillTable table) async {
    if (table.start == null || table.end == null) return;
    try {
      final bool enabled = await PrintBluetoothThermal.bluetoothEnabled;
      if (!enabled) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Activa Bluetooth en la tablet para imprimir.')));
        return;
      }
      final bool permission = await PrintBluetoothThermal.isPermissionBluetoothGranted;
      if (!permission) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Concede el permiso de Bluetooth y vuelve a intentar.')));
        return;
      }
      final List<BluetoothInfo> printers = await PrintBluetoothThermal.pairedBluetooths;
      if (printers.isEmpty) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No hay impresoras Bluetooth emparejadas con la tablet.')));
        return;
      }
      if (!mounted) return;
      final BluetoothInfo? selected = await showDialog<BluetoothInfo>(
        context: context,
        builder: (BuildContext dialogContext) => AlertDialog(
          title: const Text('Seleccionar impresora térmica'),
          content: SizedBox(
            width: 420,
            child: ListView.builder(
              shrinkWrap: true,
              itemCount: printers.length,
              itemBuilder: (_, int index) {
                final BluetoothInfo printer = printers[index];
                return ListTile(
                  leading: const Icon(Icons.print_outlined),
                  title: Text(printer.name.isEmpty ? 'Impresora Bluetooth' : printer.name),
                  subtitle: Text(printer.macAdress),
                  onTap: () => Navigator.pop(dialogContext, printer),
                );
              },
            ),
          ),
          actions: <Widget>[TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cancelar'))],
        ),
      );
      if (selected == null) return;
      final bool connected = await PrintBluetoothThermal.connect(macPrinterAddress: selected.macAdress);
      if (!connected) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo conectar con la impresora.')));
        return;
      }
      final CapabilityProfile profile = await CapabilityProfile.load();
      final Generator generator = Generator(PaperSize.mm58, profile);
      final List<int> bytes = <int>[];
      bytes.addAll(generator.text('Billares Don Miguel', styles: const PosStyles(align: PosAlign.center, bold: true, height: PosTextSize.size2, width: PosTextSize.size2)));
      bytes.addAll(generator.text('Mesa ${table.number}', styles: const PosStyles(align: PosAlign.center, bold: true)));
      bytes.addAll(generator.hr());
      bytes.addAll(generator.text('Hora de inicio: ${clock(table.start!)}'));
      bytes.addAll(generator.text('Hora finalizada: ${clock(table.end!)}'));
      bytes.addAll(generator.text('Tiempo jugado: ${duration(table.end!.difference(table.start!).inSeconds)}'));
      bytes.addAll(generator.text('Tarifa: ${money(table.rate)} / hora'));
      bytes.addAll(generator.hr());
      bytes.addAll(generator.text('MONTO A PAGAR', styles: const PosStyles(align: PosAlign.center, bold: true)));
      bytes.addAll(generator.text(money(table.amount), styles: const PosStyles(align: PosAlign.center, bold: true, height: PosTextSize.size2, width: PosTextSize.size2)));
      bytes.addAll(generator.feed(3));
      bytes.addAll(generator.cut());
      final bool printed = await PrintBluetoothThermal.writeBytes(bytes);
      if (!printed && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('La impresora no aceptó el recibo.')));
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Recibo enviado a la impresora.')));
      }
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo imprimir el recibo.')));
    }
  }

  Future<void> collect(BillTable table) async {
    if (table.start != null && table.end != null && table.amount > 0) {
      await printReceipt(table);
    }
    if (table.status != TableStatus.pending || table.start == null || table.end == null) return;
    final HistoryEntry entry = HistoryEntry(table: table.number, start: table.start!, end: table.end!, seconds: table.end!.difference(table.start!).inSeconds, amount: table.amount, workDate: workdayOpenedAt ?? table.end!);
    setState(() {
      history.add(entry);
      if (workdayActive) {
        workdayGenerated += table.amount;
        workdayGames += 1;
      }
      table.status = TableStatus.available;
      table.start = null;
      table.end = null;
      table.amount = 0;
    });
    await saveHistory();
    await saveTables();
    await saveWorkday();
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
      client.userAgent = 'Billares-Don-Miguel/1.2.6';
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
      client?.close(force: true);
      if (mounted) setState(() => checkingUpdate = false);
    }
  }
  Future<void> downloadAndInstall(String url) async {
    HttpClient? client;
    try {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Preparando actualización...')));
      final bool installPermission = await ApkInstall().onCheckInstallApkPermission();
      if (!installPermission) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Activa el permiso para instalar aplicaciones desconocidas y vuelve a pulsar Actualizar.')));
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Descargando actualización...')));
      final Directory directory = await getApplicationDocumentsDirectory();
      final String path = '${directory.path}/billares-don-miguel-update.apk';
      client = HttpClient()..connectionTimeout = const Duration(seconds: 30);
      client.userAgent = 'Billares-Don-Miguel/1.2.6';
      final HttpClientRequest request = await client.getUrl(Uri.parse(url));
      final HttpClientResponse response = await request.close();
      if (response.statusCode != HttpStatus.ok) throw HttpException('HTTP ${response.statusCode}');
      final File file = File(path);
      final IOSink sink = file.openWrite();
      await response.pipe(sink);
      await sink.flush();
      await sink.close();
      if (!await file.exists() || await file.length() < 1024 * 1024) throw const HttpException('APK inválido o incompleto');
      final bool installStarted = await ApkInstall().onInstallApk(path);
      if (!installStarted && mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Android no inició el instalador. Verifica el permiso de instalación.')));
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo descargar o iniciar la instalación de la actualización.')));
    } finally {
      client?.close(force: true);
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
    final String buttonText = table.status == TableStatus.available ? 'Iniciar juego' : table.status == TableStatus.playing ? 'Finalizar juego' : 'Cobrar';
    final Future<void> Function()? action = table.status == TableStatus.available
        ? (workdayActive ? () => startGame(table) : null)
        : table.status == TableStatus.playing
            ? () => finishGame(table)
            : () => collect(table);
    return Card(
      elevation: 4,
      color: statusColor(table.status),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
            Expanded(child: Text('Mesa ${table.number}', style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: statusTextColor(table.status)))),
            Flexible(child: Align(alignment: Alignment.topRight, child: Chip(label: Text(table.statusText, overflow: TextOverflow.ellipsis, style: TextStyle(color: statusTextColor(table.status))), avatar: CircleAvatar(backgroundColor: statusTextColor(table.status), radius: 6)))),
          ]),
          Divider(color: statusTextColor(table.status).withValues(alpha: 0.35)),
          Text('Tarifa: ${money(table.rate)} / hora', style: TextStyle(fontSize: 17, color: statusTextColor(table.status), fontWeight: FontWeight.w800)),
          const SizedBox(height: 7),
          Text('Hora de inicio: ${table.start == null ? '—' : clock(table.start!)}', style: TextStyle(fontSize: 17, color: statusTextColor(table.status), fontWeight: FontWeight.w700)),
          Text('Hora finalizada: ${table.end == null ? '—' : clock(table.end!)}', style: TextStyle(fontSize: 17, color: statusTextColor(table.status), fontWeight: FontWeight.w700)),
          Text('Tiempo jugado: ${duration(table.elapsedSeconds)}', style: TextStyle(fontSize: 17, color: statusTextColor(table.status), fontWeight: FontWeight.w700)),
          const Spacer(),
          Text('MONTO A PAGAR', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w900, color: statusTextColor(table.status))),
          Text(money(amount), style: TextStyle(fontSize: 29, fontWeight: FontWeight.w900, color: statusTextColor(table.status))),
          const SizedBox(height: 8),
          if (table.status == TableStatus.pending) ...<Widget>[
            SizedBox(width: double.infinity, child: OutlinedButton.icon(onPressed: () => printReceipt(table), icon: const Icon(Icons.print_outlined), label: const Text('Imprimir recibo'))),
            const SizedBox(height: 7),
          ],
          SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: action, icon: Icon(table.status == TableStatus.playing ? Icons.stop : table.status == TableStatus.pending ? Icons.payments : Icons.play_arrow), label: Text(buttonText))),
          if (table.status == TableStatus.available && !workdayActive) const Padding(padding: EdgeInsets.only(top: 5), child: Center(child: Text('Abra el día para iniciar partidas', style: TextStyle(fontSize: 11)))),
        ]),
      ),
    );
  }

  Widget dashboard() => LayoutBuilder(
        builder: (BuildContext context, BoxConstraints constraints) {
          final double width = constraints.maxWidth;
          final int columns = width >= 1100 ? 3 : width >= 650 ? 2 : 1;
          final bool compact = width < 650;
          final int available = tableList.where((BillTable t) => t.status == TableStatus.available).length;
          final int playing = tableList.where((BillTable t) => t.status == TableStatus.playing).length;
          final int pending = tableList.where((BillTable t) => t.status == TableStatus.pending).length;
          Widget metricCard(String title, String value, IconData icon) {
            return Card(elevation: 3, margin: EdgeInsets.zero, child: Padding(padding: EdgeInsets.all(compact ? 14 : 18), child: Row(children: <Widget>[
              Container(width: compact ? 42 : 48, height: compact ? 42 : 48, decoration: BoxDecoration(color: Theme.of(context).colorScheme.primaryContainer, borderRadius: BorderRadius.circular(14)), child: Icon(icon, color: Theme.of(context).colorScheme.onPrimaryContainer)),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
                Text(title, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 13)),
                const SizedBox(height: 3),
                Text(value, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: compact ? 21 : 24, fontWeight: FontWeight.w800)),
              ])),
            ])));
          }
          return SingleChildScrollView(
            padding: EdgeInsets.fromLTRB(compact ? 12 : 20, compact ? 12 : 18, compact ? 12 : 20, 24),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: <Widget>[
              Container(
                padding: EdgeInsets.all(compact ? 16 : 22),
                decoration: BoxDecoration(gradient: LinearGradient(colors: <Color>[Theme.of(context).colorScheme.primary, Theme.of(context).colorScheme.primaryContainer]), borderRadius: BorderRadius.circular(22)),
                child: Wrap(alignment: WrapAlignment.spaceBetween, crossAxisAlignment: WrapCrossAlignment.center, spacing: 16, runSpacing: 12, children: <Widget>[
                  Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
                    const Text('Billares Don Miguel', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900, color: Colors.white)),
                    const SizedBox(height: 4),
                    Text('Panel central • Control de mesas', style: TextStyle(color: Colors.white.withValues(alpha: 0.88))),
                  ]),
                  Chip(avatar: Icon(Icons.wifi, size: 18, color: lanIp != null ? Colors.green : Colors.red), label: Text(lanIp != null ? 'LAN conectado' : 'LAN no disponible')),
                ]),
              ),
              const SizedBox(height: 14),
              GridView.count(crossAxisCount: columns, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(), crossAxisSpacing: 12, mainAxisSpacing: 12, childAspectRatio: width >= 1100 ? 2.35 : width >= 650 ? 2.7 : 3.1, children: <Widget>[
                metricCard('Disponibles', '$available', Icons.check_circle_outline),
                metricCard('En juego', '$playing', Icons.sports_bar),
                metricCard('Pendientes', '$pending', Icons.payments_outlined),
                metricCard('Generado hoy', money(todayTotal), Icons.attach_money),
              ]),
              const SizedBox(height: 14),
              Card(elevation: 2, child: Padding(padding: EdgeInsets.all(compact ? 14 : 18), child: Wrap(alignment: WrapAlignment.spaceBetween, crossAxisAlignment: WrapCrossAlignment.center, spacing: 14, runSpacing: 12, children: <Widget>[
                Row(mainAxisSize: MainAxisSize.min, children: <Widget>[
                  Icon(workdayActive ? Icons.lock_open : Icons.lock_outline, color: workdayActive ? Colors.green : Colors.orange),
                  const SizedBox(width: 10),
                  Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
                    const Text('Jornada de trabajo', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                    Text(workdayActive ? 'ABIERTA • ${clock(workdayOpenedAt ?? DateTime.now())}' : 'CERRADA', style: TextStyle(color: workdayActive ? Colors.green : Colors.orange, fontWeight: FontWeight.w700)),
                  ]),
                ]),
                Wrap(spacing: 8, runSpacing: 8, children: <Widget>[
                  if (workdayActive) Text('Juegos: $workdayGames'),
                  if (workdayActive) Text('Generado: ${money(workdayGenerated)}'),
                  if (!workdayActive && workdayClosedAt != null) Text('Cierre: ${clock(workdayClosedAt!)}'),
                  FilledButton.icon(onPressed: workdayActive ? closeWorkday : openWorkday, icon: Icon(workdayActive ? Icons.lock : Icons.lock_open), label: Text(workdayActive ? 'Cerrar jornada' : 'Abrir jornada')),
                ]),
              ]))),
              const SizedBox(height: 12),
              Wrap(spacing: 10, runSpacing: 10, children: <Widget>[
                FilledButton.icon(onPressed: showTvConnection, icon: const Icon(Icons.tv), label: const Text('Mostrar en TV')),
                OutlinedButton.icon(onPressed: checkForUpdate, icon: const Icon(Icons.system_update_alt), label: const Text('Buscar actualización')),
              ]),
              const SizedBox(height: 16),
              Row(children: <Widget>[
                Expanded(child: Text('Estado de las mesas', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800))),
                if (!compact) const Text('🟢 Disponible   🔴 En juego   🟡 Pendiente'),
              ]),
              if (compact) const Padding(padding: EdgeInsets.only(top: 5), child: Align(alignment: Alignment.centerLeft, child: Text('🟢 Disponible   🔴 En juego   🟡 Pendiente', style: TextStyle(fontSize: 12)))),
              const SizedBox(height: 10),
              GridView.builder(padding: EdgeInsets.zero, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(), gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: columns, mainAxisExtent: width >= 1100 ? 350 : width >= 650 ? 365 : 390, crossAxisSpacing: 14, mainAxisSpacing: 14), itemCount: tableList.length, itemBuilder: (_, int index) => tableCard(tableList[index])),
            ]),
          );
        },
      );

  Widget historyPage() {
    final Map<String, List<HistoryEntry>> groups = <String, List<HistoryEntry>>{};
    for (final HistoryEntry entry in history) {
      final String key = '${entry.workDate.year}-${entry.workDate.month.toString().padLeft(2, '0')}-${entry.workDate.day.toString().padLeft(2, '0')}';
      groups.putIfAbsent(key, () => <HistoryEntry>[]).add(entry);
    }
    final List<String> keys = groups.keys.toList()..sort((String a, String b) => b.compareTo(a));
    return ListView(
      padding: const EdgeInsets.all(16),
      children: <Widget>[
        Card(child: ListTile(leading: const Icon(Icons.today), title: const Text('Últimos 7 días'), subtitle: const Text('Movimientos organizados por fecha de trabajo'), trailing: Text(money(todayTotal), style: const TextStyle(fontSize: 19, fontWeight: FontWeight.bold)))),
        if (keys.isEmpty) const Padding(padding: EdgeInsets.all(24), child: Center(child: Text('No hay movimientos en los últimos 7 días.'))),
        ...keys.map((String key) {
          final List<HistoryEntry> items = groups[key]!..sort((HistoryEntry a, HistoryEntry b) => b.end.compareTo(a.end));
          final HistoryEntry first = items.last;
          final HistoryEntry last = items.first;
          final double total = items.fold<double>(0, (double sum, HistoryEntry e) => sum + e.amount);
          final DateTime day = first.workDate;
          final bool isCurrent = workdayActive && workdayOpenedAt != null && day.year == workdayOpenedAt!.year && day.month == workdayOpenedAt!.month && day.day == workdayOpenedAt!.day;
          return Card(
            margin: const EdgeInsets.only(top: 12),
            child: ExpansionTile(
              initiallyExpanded: isCurrent,
              title: Text(date(day), style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
              subtitle: Text('Apertura: ${isCurrent ? clock(workdayOpenedAt!) : clock(first.start)} • ${items.length} juegos • Generado: ${money(total)}'),
              children: <Widget>[
                Padding(padding: const EdgeInsets.fromLTRB(16, 0, 16, 10), child: Align(alignment: Alignment.centerLeft, child: Text(workdayClosedAt != null && day.year == workdayClosedAt!.year && day.month == workdayClosedAt!.month && day.day == workdayClosedAt!.day ? 'Cierre: ${clock(workdayClosedAt!)} • Efectivo físico: ${money(workdayCashClose)}' : 'Último movimiento: ${clock(last.end)}'))),
                ...items.map((HistoryEntry e) => ListTile(leading: CircleAvatar(child: Text('${e.table}')), title: Text('Mesa ${e.table} • ${money(e.amount)}'), subtitle: Text('${clock(e.start)} - ${clock(e.end)} • ${duration(e.seconds)}'))),
              ],
            ),
          );
        }),
      ],
    );
  }

  void showSettings() {
    showDialog<void>(
      context: context,
      builder: (BuildContext context) => AlertDialog(
        title: const Text('Configuración'),
        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
          const Text('Tarifas fijas', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          const Text('Mesas 1 y 2: C\$120 por hora'),
          const Text('Mesas 3 y 4: C\$100 por hora'),
          const Text('Mesa 5: C\$70 por hora'),
          const SizedBox(height: 12),
          const Text('Las tarifas no pueden modificarse desde el administrador.'),
          const SizedBox(height: 16),
          if (lanIp != null) Text('Receptor TV: http://$lanIp:8080/tv'),
          const SizedBox(height: 8),
          const Text('La TV muestra únicamente la pantalla de mesas; el panel administrativo permanece en el celular.'),
        ])),
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
  Widget _summaryCard(String title, String value, IconData icon) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: <Widget>[
            Icon(icon, size: 28),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(title, style: const TextStyle(fontSize: 13)),
                  const SizedBox(height: 4),
                  Text(value, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget workdayView() {
    final String opened = workdayOpenedAt == null ? '—' : workdayOpenedAt!.toString().replaceFirst('T', ' ').split('.').first;
    final String closed = workdayClosedAt == null ? '—' : workdayClosedAt!.toString().replaceFirst('T', ' ').split('.').first;
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final int columns = constraints.maxWidth >= 900 ? 4 : constraints.maxWidth >= 600 ? 2 : 1;
        return SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Row(
                    children: <Widget>[
                      Icon(workdayActive ? Icons.lock_open : Icons.lock_outline, color: workdayActive ? Colors.green : Colors.orange, size: 30),
                      const SizedBox(width: 12),
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
                        const Text('Jornada de trabajo', style: TextStyle(fontSize: 21, fontWeight: FontWeight.bold)),
                        Text(workdayActive ? 'ABIERTA' : 'CERRADA', style: TextStyle(color: workdayActive ? Colors.green : Colors.orange, fontWeight: FontWeight.bold)),
                      ])),
                      FilledButton.icon(
                        onPressed: workdayActive ? closeWorkday : openWorkday,
                        icon: Icon(workdayActive ? Icons.lock : Icons.lock_open),
                        label: Text(workdayActive ? 'Cerrar jornada' : 'Abrir jornada'),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              GridView.count(
                crossAxisCount: columns,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
                childAspectRatio: constraints.maxWidth >= 600 ? 2.3 : 2.8,
                children: <Widget>[
                  _summaryCard('Juegos', '$workdayGames', Icons.sports_bar),
                  _summaryCard('Generado hoy', 'C\$ ${workdayGenerated.toStringAsFixed(2)}', Icons.payments),
                  _summaryCard('Efectivo físico', 'C\$ ${workdayCashClose.toStringAsFixed(2)}', Icons.account_balance_wallet),
                  _summaryCard('Apertura', opened, Icons.schedule),
                ],
              ),
              const SizedBox(height: 16),
              Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
                const Text('Detalle de jornada', style: TextStyle(fontSize: 19, fontWeight: FontWeight.bold)),
                const SizedBox(height: 10),
                Text('Inicio: $opened'),
                Text('Cierre: $closed'),
                Text('Partidas registradas: $workdayGames'),
                Text('Total generado: C\$ ${workdayGenerated.toStringAsFixed(2)}'),
                Text('Efectivo físico al cierre: C\$ ${workdayCashClose.toStringAsFixed(2)}'),
              ]))),
            ],
          ),
        );
      },
    );
  }

}
