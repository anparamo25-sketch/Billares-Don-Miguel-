import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:apk_install/apk_install.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_background/flutter_background.dart';
import 'package:path_provider/path_provider.dart';
import 'package:print_bluetooth_thermal/print_bluetooth_thermal.dart';
import 'package:esc_pos_utils_plus/esc_pos_utils_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'cloud_tv_sync.dart';
import 'receipt_preview_page.dart';

const String appVersion = '1.2.9+129';
const String defaultPassword = '1234';
const String updateManifestUrl =
    'https://github.com/anparamo25-sketch/Billares-Don-Miguel-/raw/refs/heads/main/update.json';
const Map<int, double> tableRates = <int, double>{
  1: 120,
  2: 120,
  3: 100,
  4: 100,
  5: 70,
};

enum TableStatus { available, playing, pending }

RawDatagramSocket? _billaresMdnsSocket;
Future<String?> _billaresLocalIp() async {
  try {
    final interfaces = await NetworkInterface.list(
      type: InternetAddressType.IPv4,
      includeLoopback: false,
    );
    for (final network in interfaces) {
      for (final address in network.addresses) {
        final parts = address.address
            .split('.')
            .map(int.tryParse)
            .whereType<int>()
            .toList();
        final privateIpv4 =
            parts.length == 4 &&
            (parts[0] == 10 ||
                (parts[0] == 172 && parts[1] >= 16 && parts[1] <= 31) ||
                (parts[0] == 192 && parts[1] == 168));
        if (privateIpv4 &&
            !address.isLoopback &&
            !address.isLinkLocal &&
            !address.isMulticast)
          return address.address;
      }
    }
  } catch (_) {}
  return null;
}

Future<void> _answerBillaresMdns(
  RawDatagramSocket socket,
  Datagram datagram,
) async {
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
        labels.add(
          String.fromCharCodes(query.sublist(offset, offset + length)),
        );
        offset += length;
      }
      if (offset + 4 > query.length) return;
      final int type = (query[offset] << 8) | query[offset + 1];
      offset += 4;
      if (labels.join('.').toLowerCase() == 'billaresdonmiguel.local' &&
          (type == 1 || type == 255))
        matched = true;
    }
    if (!matched) return;
    final String? ip = await _billaresLocalIp();
    if (ip == null) return;
    final List<int> octets = ip.split('.').map(int.parse).toList();
    if (octets.length != 4) return;

    final response = <int>[];
    response.addAll(query.sublist(0, 2));
    response.addAll(<int>[
      0x84,
      0x00,
      0x00,
      0x00,
      0x00,
      0x01,
      0x00,
      0x00,
      0x00,
      0x00,
      0x00,
      0x00,
    ]);
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
      await const MethodChannel('billaresdonmiguel/network')
          .invokeMethod<void>('acquireMulticastLock');
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
    final String statusName =
        map['status'] as String? ?? TableStatus.available.name;
    status = TableStatus.values.firstWhere(
      (TableStatus value) => value.name == statusName,
      orElse: () => TableStatus.available,
    );
    start = map['start'] == null
        ? null
        : DateTime.tryParse(map['start'] as String);
    end = map['end'] == null ? null : DateTime.tryParse(map['end'] as String);
    amount = (map['amount'] as num?)?.toDouble() ?? 0;
  }
}

class HistoryEntry {
  HistoryEntry({
    required this.table,
    required this.start,
    required this.end,
    required this.seconds,
    required this.amount,
    DateTime? workDate,
  }) : workDate = DateTime(
         (workDate ?? end).year,
         (workDate ?? end).month,
         (workDate ?? end).day,
       );
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
    workDate: DateTime.tryParse(
      map['workDate'] as String? ?? map['end'] as String,
    ),
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
      Navigator.of(context).pushReplacement(
        MaterialPageRoute<void>(builder: (_) => const DashboardPage()),
      );
      return;
    }
    setState(() => loading = false);
  }

  Future<void> login() async {
    if (controller.text != password) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Contraseña incorrecta')));
      controller.clear();
      return;
    }
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setBool('session_active', true);
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => const DashboardPage()),
    );
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
                  ? const SizedBox(
                      height: 180,
                      child: Center(child: CircularProgressIndicator()),
                    )
                  : Column(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        const Icon(
                          Icons.sports_bar,
                          size: 64,
                          color: Colors.green,
                        ),
                        const SizedBox(height: 12),
                        const Text(
                          'Billares Don Miguel',
                          style: TextStyle(
                            fontSize: 27,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
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
                              onPressed: () =>
                                  setState(() => obscure = !obscure),
                              icon: Icon(
                                obscure
                                    ? Icons.visibility_outlined
                                    : Icons.visibility_off_outlined,
                              ),
                            ),
                            border: const OutlineInputBorder(),
                          ),
                        ),
                        const SizedBox(height: 20),
                        SizedBox(
                          width: double.infinity,
                          height: 50,
                          child: FilledButton.icon(
                            onPressed: login,
                            icon: const Icon(Icons.login),
                            label: const Text('Ingresar'),
                          ),
                        ),
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

class _DashboardPageState extends State<DashboardPage>
    with WidgetsBindingObserver {
  final List<BillTable> tableList = tableRates.entries
      .map((MapEntry<int, double> e) => BillTable(e.key, e.value))
      .toList();
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
      publishCloudTvState(
        tableList
            .map(
              (BillTable t) => <String, dynamic>{
                'number': t.number,
                'status': t.status.name,
                'start': t.start?.toIso8601String(),
                'end': t.end?.toIso8601String(),
                'amount': t.status == TableStatus.playing
                    ? t.liveAmount
                    : t.amount,
                'rate': t.rate,
              },
            )
            .toList(),
      );
    });
    Future<void>.delayed(
      const Duration(seconds: 2),
      () => checkForUpdate(showNoUpdate: false),
    );
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
        history = data
            .map(
              (dynamic item) =>
                  HistoryEntry.fromMap(Map<String, dynamic>.from(item as Map)),
            )
            .where((HistoryEntry e) => e.end.isAfter(cutoff))
            .toList();
      } catch (_) {
        history = <HistoryEntry>[];
      }
    }
    final String? rawTables = prefs.getString('tables');
    if (rawTables != null && rawTables.isNotEmpty) {
      try {
        final List<dynamic> data = jsonDecode(rawTables) as List<dynamic>;
        for (final dynamic item in data) {
          final Map<String, dynamic> map = Map<String, dynamic>.from(
            item as Map,
          );
          final int number = (map['number'] as num).toInt();
          final BillTable table = tableList.firstWhere(
            (BillTable t) => t.number == number,
          );
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
    await prefs.setString(
      'history',
      jsonEncode(history.map((HistoryEntry e) => e.toMap()).toList()),
    );
  }

  Future<void> saveWorkday() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setBool('workday_active', workdayActive);
    if (workdayOpenedAt != null) {
      await prefs.setString(
        'workday_opened_at',
        workdayOpenedAt!.toIso8601String(),
      );
    } else {
      await prefs.remove('workday_opened_at');
    }
    if (workdayClosedAt != null) {
      await prefs.setString(
        'workday_closed_at',
        workdayClosedAt!.toIso8601String(),
      );
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
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text('Juegos: $workdayGames'),
            Text('Total generado: ${money(generated)}'),
            const SizedBox(height: 12),
            TextField(
              controller: cashController,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: const InputDecoration(
                labelText: 'Efectivo físico al cierre',
                prefixText: 'C\$ ',
              ),
            ),
          ],
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(
              context,
              double.tryParse(cashController.text.replaceAll(',', '.')) != null,
            ),
            child: const Text('Registrar cierre'),
          ),
        ],
      ),
    );
    final double? cash = double.tryParse(
      cashController.text.replaceAll(',', '.'),
    );
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
    await prefs.setString(
      'tables',
      jsonEncode(tableList.map((BillTable t) => t.toMap()).toList()),
    );
  }

  Future<void> handleRequest(HttpRequest request) async {
    final HttpResponse response = request.response;
    response.headers.set('Access-Control-Allow-Origin', '*');
    response.headers.set('Access-Control-Allow-Methods', 'GET, OPTIONS');
    response.headers.set(
      'Access-Control-Allow-Headers',
      'Content-Type, Cache-Control',
    );
    response.headers.set(
      'Cache-Control',
      'no-store, no-cache, must-revalidate, max-age=0',
    );
    response.headers.set('Pragma', 'no-cache');
    response.headers.set('Connection', 'keep-alive');
    if (request.method == 'OPTIONS') {
      response.statusCode = HttpStatus.noContent;
      await response.close();
      return;
    }
    if (request.uri.path == '/tv-logo.webp') {
      try {
        final ByteData logo = await rootBundle.load('assets/tv-logo.webp');
        response.headers.contentType = ContentType('image', 'webp');
        response.headers.contentLength = logo.lengthInBytes;
        response.add(logo.buffer.asUint8List());
      } catch (_) {
        response.statusCode = HttpStatus.notFound;
      }
      await response.close();
      return;
    }
    if (request.uri.path == '/health') {
      response.headers.contentType = ContentType.json;
      final String body = jsonEncode(<String, dynamic>{
        'ok': true,
        'app': 'Billares Don Miguel',
        'version': appVersion,
      });
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
        server = await HttpServer.bind(
          InternetAddress.anyIPv4,
          80,
          shared: true,
        );
        lanPort = 80;
      } catch (_) {
        server = await HttpServer.bind(
          InternetAddress.anyIPv4,
          8080,
          shared: true,
        );
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
    final String url = port == 80
        ? 'http://billaresdonmiguel.local/tv'
        : 'http://billaresdonmiguel.local:$port/tv';
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Pantalla exclusiva para TV'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Text(
                'La TV mostrará solamente las mesas. La administración continúa funcionando de forma independiente.',
              ),
              const SizedBox(height: 12),
              SelectableText(
                url,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              FilledButton.icon(
                onPressed: () async {
                  await Clipboard.setData(ClipboardData(text: url));
                  if (dialogContext.mounted)
                    ScaffoldMessenger.of(dialogContext).showSnackBar(
                      const SnackBar(content: Text('Dirección de TV copiada')),
                    );
                },
                icon: const Icon(Icons.copy),
                label: const Text('Copiar dirección'),
              ),
              const SizedBox(height: 8),
              const Text(
                'Para la pantalla exclusiva utiliza esta dirección en el navegador de la TV. No uses Duplicar pantalla/Miracast.',
                style: TextStyle(fontSize: 12),
              ),
            ],
          ),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Cerrar'),
          ),
        ],
      ),
    );
  }

  String get tvHtml => utf8.decode(
    base64Decode(
      'PCFkb2N0eXBlIGh0bWw+CjxodG1sIGxhbmc9ImVzIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9InV0Zi04Ij4KPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEiPgo8bWV0YSBodHRwLWVxdWl2PSJDYWNoZS1Db250cm9sIiBjb250ZW50PSJuby1zdG9yZSwgbm8tY2FjaGUsIG11c3QtcmV2YWxpZGF0ZSwgbWF4LWFnZT0wIj4KPG1ldGEgaHR0cC1lcXVpdj0iUHJhZ21hIiBjb250ZW50PSJuby1jYWNoZSI+CjxtZXRhIGh0dHAtZXF1aXY9IkV4cGlyZXMiIGNvbnRlbnQ9IjAiPgo8dGl0bGU+QmlsbGFyZXMgRG9uIE1pZ3VlbCAtIFRWPC90aXRsZT4KPHN0eWxlPgoqe2JveC1zaXppbmc6Ym9yZGVyLWJveH1odG1sLGJvZHl7bWFyZ2luOjA7d2lkdGg6MTAwJTtoZWlnaHQ6MTAwJTtvdmVyZmxvdzpoaWRkZW47YmFja2dyb3VuZDojMDUwNzBiO2NvbG9yOiNmZmY7Zm9udC1mYW1pbHk6QXJpYWwsc2Fucy1zZXJpZn0ud3JhcHt3aWR0aDoxMDAlO2hlaWdodDoxMDB2aDtwYWRkaW5nOjAgMjBweCAxNnB4O2Rpc3BsYXk6ZmxleDtmbGV4LWRpcmVjdGlvbjpjb2x1bW47b3ZlcmZsb3c6aGlkZGVufWhlYWRlcntoZWlnaHQ6MTE4cHg7ZmxleDowIDAgMTE4cHg7cGFkZGluZzo2cHggOHB4O2JhY2tncm91bmQ6I2ZmZjtib3JkZXItYm90dG9tOjNweCBzb2xpZCAjMTU1N2MwO2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDEuMTVmciAxZnI7YWxpZ24taXRlbXM6Y2VudGVyfS50aXRsZXtqdXN0aWZ5LXNlbGY6c3RhcnQ7Y29sb3I6IzE1NTdjMDtmb250LXNpemU6Y2xhbXAoMjhweCwzLjN2dyw0OHB4KTtmb250LXdlaWdodDo5MDA7bGluZS1oZWlnaHQ6MS4wNTtsZXR0ZXItc3BhY2luZzouM3B4fS5sb2dvV3JhcHtqdXN0aWZ5LXNlbGY6Y2VudGVyO2hlaWdodDoxMDAlO3dpZHRoOmF1dG87ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO292ZXJmbG93OnZpc2libGV9LmxvZ29XcmFwIGltZ3toZWlnaHQ6OTBweDt3aWR0aDphdXRvO21heC13aWR0aDpub25lO29iamVjdC1maXQ6Y29udGFpbjtvYmplY3QtcG9zaXRpb246Y2VudGVyO2Rpc3BsYXk6YmxvY2t9LmxpdmVCb3h7anVzdGlmeS1zZWxmOmVuZDt0ZXh0LWFsaWduOmNlbnRlcjtjb2xvcjojMTU1N2MwfS5jbG9ja3tmb250LXNpemU6Y2xhbXAoMjBweCwyLjJ2dywzMnB4KTtmb250LXdlaWdodDo5MDA7bGluZS1oZWlnaHQ6MS4xfS5saXZle2ZvbnQtc2l6ZTpjbGFtcCgxN3B4LDEuOXZ3LDI1cHgpO2ZvbnQtd2VpZ2h0OjkwMDttYXJnaW4tdG9wOjZweH0uZ3JpZHt3aWR0aDoxMDAlO2ZsZXg6MTttaW4taGVpZ2h0OjA7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoNSxtaW5tYXgoMCwxZnIpKTtnYXA6MTRweDtwYWRkaW5nOjE0cHggMCAwO292ZXJmbG93OmhpZGRlbn0uY2FyZHtoZWlnaHQ6MTAwJTttaW4taGVpZ2h0OjA7Ym9yZGVyLXJhZGl1czoxOHB4O3BhZGRpbmc6MTZweDtib3JkZXI6M3B4IHNvbGlkICM2NDc0OGI7ZGlzcGxheTpmbGV4O2ZsZXgtZGlyZWN0aW9uOmNvbHVtbjtib3gtc2hhZG93OjAgOHB4IDE4cHggcmdiYSgwLDAsMCwuMjgpO292ZXJmbG93OmhpZGRlbn0uZ3JlZW57YmFja2dyb3VuZDojMTAzYjIyO2JvcmRlci1jb2xvcjojMjJjNTVlfS5yZWR7YmFja2dyb3VuZDojNTExYjFiO2JvcmRlci1jb2xvcjojZWY0NDQ0fS55ZWxsb3d7YmFja2dyb3VuZDojNTY0OTBhO2JvcmRlci1jb2xvcjojZWFiMzA4fS5udW17Zm9udC1zaXplOmNsYW1wKDI0cHgsMi43dncsMzhweCk7Zm9udC13ZWlnaHQ6OTAwO2xpbmUtaGVpZ2h0OjEuMDV9LnN0YXR1c3tmb250LXNpemU6Y2xhbXAoMThweCwydncsMjdweCk7Zm9udC13ZWlnaHQ6OTAwO21hcmdpbjo3cHggMCAxMHB4O2xpbmUtaGVpZ2h0OjEuMDV9LmdyZWVuIC5zdGF0dXN7Y29sb3I6IzRhZGU4MH0ucmVkIC5zdGF0dXN7Y29sb3I6I2Y4NzE3MX0ueWVsbG93IC5zdGF0dXN7Y29sb3I6I2ZkZTA0N30ubGluZXtmb250LXNpemU6Y2xhbXAoMjZweCwyLjA1dncsMzZweCk7Zm9udC13ZWlnaHQ6NzAwO2xpbmUtaGVpZ2h0OjEuMTg7bWFyZ2luOjEwcHggMH0ubGluZSBie2ZvbnQtd2VpZ2h0OjkwMH0ucGF5e21hcmdpbi10b3A6YXV0bztwYWRkaW5nLXRvcDoxMnB4O2JvcmRlci10b3A6MnB4IHNvbGlkIHJnYmEoMjU1LDI1NSwyNTUsLjI1KX0ucGF5TGFiZWx7Zm9udC1zaXplOmNsYW1wKDE2cHgsMS42dncsMjJweCk7Zm9udC13ZWlnaHQ6OTAwO2xldHRlci1zcGFjaW5nOi41cHh9Lm1vbmV5e2ZvbnQtc2l6ZTpjbGFtcCgzMXB4LDMuM3Z3LDQ4cHgpO2ZvbnQtd2VpZ2h0OjkwMDttYXJnaW4tdG9wOjRweDtsaW5lLWhlaWdodDoxLjA1O2NvbG9yOiNmZGUwNDd9QG1lZGlhKG1heC1oZWlnaHQ6NzAwcHgpe2hlYWRlcntoZWlnaHQ6OTZweDtmbGV4LWJhc2lzOjk2cHh9LndyYXB7cGFkZGluZzowIDE0cHggMTBweH0ubG9nb1dyYXAgaW1ne2hlaWdodDo5MHB4fS5ncmlke2dhcDoxMHB4O3BhZGRpbmctdG9wOjEwcHh9LmNhcmR7cGFkZGluZzoxMnB4O2JvcmRlci1yYWRpdXM6MTRweH0uc3RhdHVze21hcmdpbjo1cHggMCA4cHh9LmxpbmV7Zm9udC1zaXplOmNsYW1wKDIycHgsMS45dncsMzBweCk7bWFyZ2luOjdweCAwfS5wYXl7cGFkZGluZy10b3A6OHB4fX1AbWVkaWEobWF4LXdpZHRoOjExMDBweCl7aGVhZGVye2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgYXV0byAxZnJ9LnRpdGxle2ZvbnQtc2l6ZTpjbGFtcCgyMnB4LDN2dywzNnB4KX19Cjwvc3R5bGU+CjwvaGVhZD4KPGJvZHk+CjxtYWluIGNsYXNzPSJ3cmFwIj4KPGhlYWRlcj4KPGRpdiBjbGFzcz0idGl0bGUiPkJpbGxhcmVzIERvbiBNaWd1ZWw8L2Rpdj4KPGRpdiBjbGFzcz0ibG9nb1dyYXAiPjxpbWcgc3JjPSIvdHYtbG9nby53ZWJwIiBhbHQ9IkJpbGxhcmVzIERvbiBNaWd1ZWwiPjwvZGl2Pgo8ZGl2IGNsYXNzPSJsaXZlQm94Ij48ZGl2IGlkPSJjbG9jayIgY2xhc3M9ImNsb2NrIj4tLTotLSBQTTwvZGl2PjxkaXYgY2xhc3M9ImxpdmUiPvCfn6IgRU4gVklWTzwvZGl2PjwvZGl2Pgo8L2hlYWRlcj4KPHNlY3Rpb24gaWQ9InRhYmxlcyIgY2xhc3M9ImdyaWQiPjwvc2VjdGlvbj4KPC9tYWluPgo8c2NyaXB0Pgpjb25zdCByYXRlcz17MToxMjAsMjoxMjAsMzoxMDAsNDoxMDAsNTo3MH07bGV0IGxhc3RTdGF0ZT1udWxsLHdzPW51bGwscmVjb25uZWN0VGltZXI9bnVsbCxwb2xsaW5nVGltZXI9bnVsbDsKZnVuY3Rpb24gc2FmZSh2KXtyZXR1cm4gdj09bnVsbHx8dj09PScnPyfigJQnOlN0cmluZyh2KX0KZnVuY3Rpb24gbW9uZXkodil7cmV0dXJuICdDJCAnK051bWJlcih2fHwwKS50b0ZpeGVkKDIpfQpmdW5jdGlvbiBjbG9ja1ZhbHVlKHYpe2lmKCF2KXJldHVybiAn4oCUJzt2YXIgZD1uZXcgRGF0ZSh2KTtpZihpc05hTihkLmdldFRpbWUoKSkpcmV0dXJuIFN0cmluZyh2KTtyZXR1cm4gZC50b0xvY2FsZVRpbWVTdHJpbmcoJ2VzLU5JJyx7aG91cjonMi1kaWdpdCcsbWludXRlOicyLWRpZ2l0Jyxob3VyMTI6dHJ1ZX0pfQpmdW5jdGlvbiBlbGFwc2VkVmFsdWUodCl7aWYodCYmdC5lbGFwc2VkJiZ0LmVsYXBzZWQhPT0nMDA6MDA6MDAnKXJldHVybiB0LmVsYXBzZWQ7aWYoIXR8fCF0LnN0YXJ0KXJldHVybiAnMDA6MDA6MDAnO3ZhciBhPW5ldyBEYXRlKHQuc3RhcnQpLGI9dC5lbmQ/bmV3IERhdGUodC5lbmQpOm5ldyBEYXRlKCk7aWYoaXNOYU4oYS5nZXRUaW1lKCkpfHxpc05hTihiLmdldFRpbWUoKSkpcmV0dXJuICcwMDowMDowMCc7dmFyIHNlYz1NYXRoLm1heCgwLE1hdGguZmxvb3IoKGItYSkvMTAwMCkpLGg9TWF0aC5mbG9vcihzZWMvMzYwMCksbT1NYXRoLmZsb29yKHNlYyUzNjAwLzYwKSxzPXNlYyU2MDtyZXR1cm4gU3RyaW5nKGgpLnBhZFN0YXJ0KDIsJzAnKSsnOicrU3RyaW5nKG0pLnBhZFN0YXJ0KDIsJzAnKSsnOicrU3RyaW5nKHMpLnBhZFN0YXJ0KDIsJzAnKX0KZnVuY3Rpb24gc3RhdHVzTmFtZSh2KXtyZXR1cm4gdj09PSdwbGF5aW5nJz8nRW4ganVlZ28nOnY9PT0ncGVuZGluZyc/J1BlbmRpZW50ZSBkZSBjb2Jybyc6dj09PSdhdmFpbGFibGUnPydEaXNwb25pYmxlJzpzYWZlKHYpfQpmdW5jdGlvbiByZW5kZXIoZCl7bGFzdFN0YXRlPWR8fGxhc3RTdGF0ZXx8e307dmFyIHRhYmxlcz1BcnJheS5pc0FycmF5KGxhc3RTdGF0ZS50YWJsZXMpP2xhc3RTdGF0ZS50YWJsZXM6W107ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3RhYmxlcycpLmlubmVySFRNTD1bMSwyLDMsNCw1XS5tYXAoZnVuY3Rpb24oaSl7dmFyIHQ9dGFibGVzLmZpbmQoZnVuY3Rpb24oeCl7cmV0dXJuIE51bWJlcih4Lm51bWJlcik9PT1pfSl8fHtudW1iZXI6aSxzdGF0dXM6J2F2YWlsYWJsZScscmF0ZTpyYXRlc1tpXSxhbW91bnQ6MH07dmFyIHM9c3RhdHVzTmFtZSh0LnN0YXR1cyksYz1zPT09J0VuIGp1ZWdvJz8ncmVkJzpzPT09J1BlbmRpZW50ZSBkZSBjb2Jybyc/J3llbGxvdyc6J2dyZWVuJztyZXR1cm4gJzxhcnRpY2xlIGNsYXNzPSJjYXJkICcrYysnIj48ZGl2IGNsYXNzPSJudW0iPk1lc2EgJytpKyc8L2Rpdj48ZGl2IGNsYXNzPSJzdGF0dXMiPicrc2FmZShzKSsnPC9kaXY+PGRpdiBjbGFzcz0ibGluZSI+PGI+SG9yYSBkZSBpbmljaW86PC9iPiAnKyh0LnN0YXJ0JiZTdHJpbmcodC5zdGFydCkuaW5kZXhPZignVCcpPjA/Y2xvY2tWYWx1ZSh0LnN0YXJ0KTpzYWZlKHQuc3RhcnQpKSsnPC9kaXY+PGRpdiBjbGFzcz0ibGluZSI+PGI+VGllbXBvIGp1Z2Fkbzo8L2I+ICcrZWxhcHNlZFZhbHVlKHQpKyc8L2Rpdj48ZGl2IGNsYXNzPSJsaW5lIj48Yj5Ib3JhIGZpbmFsaXphZGE6PC9iPiAnKyh0LmVuZCYmU3RyaW5nKHQuZW5kKS5pbmRleE9mKCdUJyk+MD9jbG9ja1ZhbHVlKHQuZW5kKTpzYWZlKHQuZW5kKSkrJzwvZGl2PjxkaXYgY2xhc3M9InBheSI+PGRpdiBjbGFzcz0icGF5TGFiZWwiPk1PTlRPIEEgUEFHQVI8L2Rpdj48ZGl2IGNsYXNzPSJtb25leSI+Jyttb25leSh0LmFtb3VudCkrJzwvZGl2PjwvZGl2PjwvYXJ0aWNsZT4nfSkuam9pbignJyk7dmFyIGNsb2NrPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbG9jaycpO2lmKGNsb2NrKWNsb2NrLnRleHRDb250ZW50PW5ldyBEYXRlKCkudG9Mb2NhbGVUaW1lU3RyaW5nKCdlcy1OSScse2hvdXI6JzItZGlnaXQnLG1pbnV0ZTonMi1kaWdpdCcsaG91cjEyOnRydWV9KX0KYXN5bmMgZnVuY3Rpb24gcG9sbFN0YXRlKCl7dHJ5e3ZhciByPWF3YWl0IGZldGNoKCcvYXBpL3N0YXRlP3RzPScrRGF0ZS5ub3coKSx7Y2FjaGU6J25vLXN0b3JlJ30pO2lmKCFyLm9rKXRocm93IEVycm9yKHIuc3RhdHVzKTtyZW5kZXIoYXdhaXQgci5qc29uKCkpfWNhdGNoKGUpe319CmZ1bmN0aW9uIHN0YXJ0UG9sbGluZygpe2lmKHBvbGxpbmdUaW1lcilyZXR1cm47cG9sbFN0YXRlKCk7cG9sbGluZ1RpbWVyPXNldEludGVydmFsKHBvbGxTdGF0ZSwxMDAwKX0KZnVuY3Rpb24gY29ubmVjdCgpe2NsZWFyVGltZW91dChyZWNvbm5lY3RUaW1lcik7dHJ5e2lmKHdzKXdzLmNsb3NlKCl9Y2F0Y2goZSl7fXZhciBwPWxvY2F0aW9uLnByb3RvY29sPT09J2h0dHBzOic/J3dzczonOid3czonO3RyeXt3cz1uZXcgV2ViU29ja2V0KHArJy8vJytsb2NhdGlvbi5ob3N0KycvYXBpL3N0cmVhbScpO3dzLm9ub3Blbj1mdW5jdGlvbigpe2lmKHBvbGxpbmdUaW1lcil7Y2xlYXJJbnRlcnZhbChwb2xsaW5nVGltZXIpO3BvbGxpbmdUaW1lcj1udWxsfX07d3Mub25tZXNzYWdlPWZ1bmN0aW9uKGUpe3RyeXtyZW5kZXIoSlNPTi5wYXJzZShlLmRhdGEpKX1jYXRjaChfKXt9fTt3cy5vbmNsb3NlPWZ1bmN0aW9uKCl7c3RhcnRQb2xsaW5nKCk7cmVjb25uZWN0VGltZXI9c2V0VGltZW91dChjb25uZWN0LDMwMDApfTt3cy5vbmVycm9yPWZ1bmN0aW9uKCl7dHJ5e3dzLmNsb3NlKCl9Y2F0Y2goXyl7fTtzdGFydFBvbGxpbmcoKX19Y2F0Y2goZSl7c3RhcnRQb2xsaW5nKCk7cmVjb25uZWN0VGltZXI9c2V0VGltZW91dChjb25uZWN0LDMwMDApfX0KcmVuZGVyKHt0YWJsZXM6W119KTtjb25uZWN0KCk7c2V0SW50ZXJ2YWwoZnVuY3Rpb24oKXtpZihsYXN0U3RhdGUpcmVuZGVyKGxhc3RTdGF0ZSl9LDEwMDApOwo8L3NjcmlwdD4KPC9ib2R5Pgo8L2h0bWw+Cg==',
    ),
  );

  Map<String, dynamic> stateMap() => <String, dynamic>{
    'app': 'Billares Don Miguel',
    'version': appVersion,
    'time': clock(DateTime.now()),
    'tables': tableList
        .map(
          (BillTable t) => <String, dynamic>{
            'number': t.number,
            'rate': t.rate,
            'status': t.statusText,
            'start': t.start == null ? null : t.start!.toIso8601String(),
            'end': t.end == null ? null : t.end!.toIso8601String(),
            'elapsed': duration(t.elapsedSeconds),
            'amount': t.status == TableStatus.available
                ? 0
                : t.status == TableStatus.playing
                ? t.liveAmount
                : t.amount,
          },
        )
        .toList(),
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

  Future<bool> configureThermalPrinter() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    if (!mounted) return false;
    try {
      if (!await PrintBluetoothThermal.bluetoothEnabled) return false;
      if (!await PrintBluetoothThermal.isPermissionBluetoothGranted) return false;
      final List<BluetoothInfo> printers = await PrintBluetoothThermal.pairedBluetooths;
      if (printers.isEmpty) return false;
      final String? savedMac = prefs.getString('thermal_printer_mac');
      final String? selectedMac = await showDialog<String>(
        context: context,
        builder: (BuildContext dialogContext) => AlertDialog(
          title: const Text('Impresora térmica'),
          content: SizedBox(
            width: double.maxFinite,
            child: ListView(
              shrinkWrap: true,
              children: printers.map((BluetoothInfo printer) {
                final bool selected = printer.macAdress == savedMac;
                return ListTile(
                  leading: Icon(selected ? Icons.check_circle : Icons.print_outlined),
                  title: Text(printer.name.isEmpty ? 'Impresora térmica' : printer.name),
                  subtitle: Text(printer.macAdress),
                  onTap: () => Navigator.pop(dialogContext, printer.macAdress),
                );
              }).toList(),
            ),
          ),
          actions: <Widget>[
            if (savedMac != null)
              TextButton(
                onPressed: () async {
                  await prefs.remove('thermal_printer_mac');
                  await prefs.remove('thermal_printer_name');
                  if (dialogContext.mounted) Navigator.pop(dialogContext, '');
                },
                child: const Text('Quitar impresora'),
              ),
            FilledButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cerrar')),
          ],
        ),
      );
      if (selectedMac == null) return savedMac != null;
      if (selectedMac.isEmpty) return false;
      final BluetoothInfo selected = printers.firstWhere((BluetoothInfo p) => p.macAdress == selectedMac);
      await prefs.setString('thermal_printer_mac', selected.macAdress);
      await prefs.setString('thermal_printer_name', selected.name);
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<String?> printReceipt(BillTable table) async {
    if (table.start == null || table.end == null) {
      return 'La partida no tiene datos completos para imprimir.';
    }
    try {
      final bool enabled = await PrintBluetoothThermal.bluetoothEnabled;
      if (!enabled) return 'Activa Bluetooth en la tablet para imprimir.';
      final bool permission =
          await PrintBluetoothThermal.isPermissionBluetoothGranted;
      if (!permission) {
        return 'Concede el permiso de Bluetooth y vuelve a intentar.';
      }
      final List<BluetoothInfo> printers =
          await PrintBluetoothThermal.pairedBluetooths;
      if (printers.isEmpty) {
        return 'No hay impresoras Bluetooth emparejadas con la tablet.';
      }
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      final String? savedMac = prefs.getString('thermal_printer_mac');
      if (savedMac == null || savedMac.isEmpty) return 'Configura primero la impresora térmica desde Configuración.';
      BluetoothInfo? printer;
      for (final BluetoothInfo item in printers) {
        if (item.macAdress == savedMac) { printer = item; break; }
      }
      if (printer == null) return 'La impresora guardada ya no está emparejada. Ve a Configuración → Impresora térmica.';
      final bool connected = await PrintBluetoothThermal.connect(macPrinterAddress: printer.macAdress);
      if (!connected) return 'No se pudo conectar con la impresora.';

      final CapabilityProfile profile = await CapabilityProfile.load();
      final Generator generator = Generator(PaperSize.mm58, profile);
      final List<int> bytes = <int>[];
      bytes.addAll(
        generator.text(
          'Billares Don Miguel',
          styles: const PosStyles(
            align: PosAlign.center,
            bold: true,
            height: PosTextSize.size2,
            width: PosTextSize.size2,
          ),
        ),
      );
      bytes.addAll(
        generator.text(
          'Mesa ${table.number}',
          styles: const PosStyles(align: PosAlign.center, bold: true),
        ),
      );
      bytes.addAll(generator.hr());
      bytes.addAll(generator.text('Hora de inicio: ${clock(table.start!)}'));
      bytes.addAll(generator.text('Hora finalizada: ${clock(table.end!)}'));
      bytes.addAll(
        generator.text(
          'Tiempo jugado: ${duration(table.end!.difference(table.start!).inSeconds)}',
        ),
      );
      bytes.addAll(generator.text('Tarifa: ${money(table.rate)} / hora'));
      bytes.addAll(generator.hr());
      bytes.addAll(
        generator.text(
          'MONTO A PAGAR',
          styles: const PosStyles(align: PosAlign.center, bold: true),
        ),
      );
      bytes.addAll(
        generator.text(
          money(table.amount),
          styles: const PosStyles(
            align: PosAlign.center,
            bold: true,
            height: PosTextSize.size2,
            width: PosTextSize.size2,
          ),
        ),
      );
      bytes.addAll(generator.feed(3));
      bytes.addAll(generator.cut());
      final bool printed = await PrintBluetoothThermal.writeBytes(bytes);
      if (!printed) return 'La impresora no aceptó el recibo.';
      return null;
    } catch (_) {
      return 'No se pudo imprimir el recibo.';
    }
  }

  Future<void> collect(BillTable table) async {
    if (table.status != TableStatus.pending ||
        table.start == null ||
        table.end == null ||
        !mounted) {
      return;
    }
    final bool? printed = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => ReceiptPreviewPage(
          tableNumber: table.number,
          startText: clock(table.start!),
          endText: clock(table.end!),
          durationText: duration(table.end!.difference(table.start!).inSeconds),
          rateText: '${money(table.rate)} / hora',
          amountText: money(table.amount),
          onPrint: () async => printReceipt(table),
        ),
      ),
    );
    if (printed != true || !mounted) return;

    final HistoryEntry entry = HistoryEntry(
      table: table.number,
      start: table.start!,
      end: table.end!,
      seconds: table.end!.difference(table.start!).inSeconds,
      amount: table.amount,
      workDate: workdayOpenedAt ?? table.end!,
    );
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
      final HttpClientRequest request = await client.getUrl(
        Uri.parse(
          '$updateManifestUrl?x=${DateTime.now().millisecondsSinceEpoch}',
        ),
      );
      request.headers.set(HttpHeaders.cacheControlHeader, 'no-cache');
      final HttpClientResponse response = await request.close();
      if (response.statusCode != 200)
        throw const HttpException('Manifest no disponible');
      final Map<String, dynamic> manifest = jsonDecode(
        await response.transform(utf8.decoder).join(),
      ) as Map<String, dynamic>;
      final String latestVersion = manifest['version'] as String? ?? appVersion;
      final String? downloadUrl =
          (manifest['downloadUrl'] ?? manifest['apk_url']) as String?;
      if (buildNumber(latestVersion) <= buildNumber(appVersion) ||
          downloadUrl == null ||
          downloadUrl.isEmpty) {
        if (showNoUpdate && mounted)
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('La aplicación ya está actualizada')),
          );
        return;
      }
      if (!mounted) return;
      final bool? install = await showDialog<bool>(
        context: context,
        builder: (BuildContext context) => AlertDialog(
          title: const Text('Nueva actualización disponible'),
          content: Text(
            'Hay una nueva versión ($latestVersion). ¿Deseas actualizar ahora?',
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Más tarde'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Actualizar ahora'),
            ),
          ],
        ),
      );
      if (install == true) await downloadAndInstall(downloadUrl);
    } catch (_) {
      if (showNoUpdate && mounted)
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'No se pudo comprobar la actualización. La aplicación continúa funcionando normalmente.',
            ),
          ),
        );
    } finally {
      client?.close(force: true);
      if (mounted) setState(() => checkingUpdate = false);
    }
  }

  Future<void> downloadAndInstall(String url) async {
    HttpClient? client;
    try {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Preparando actualización...')),
      );
      final bool installPermission = await ApkInstall()
          .onCheckInstallApkPermission();
      if (!installPermission) {
        if (mounted)
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                'Activa el permiso para instalar aplicaciones desconocidas y vuelve a pulsar Actualizar.',
              ),
            ),
          );
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Descargando actualización...')),
      );
      final Directory directory = await getApplicationDocumentsDirectory();
      final String path = '${directory.path}/billares-don-miguel-update.apk';
      client = HttpClient()..connectionTimeout = const Duration(seconds: 30);
      client.userAgent = 'Billares-Don-Miguel/1.2.6';
      final HttpClientRequest request = await client.getUrl(Uri.parse(url));
      final HttpClientResponse response = await request.close();
      if (response.statusCode != HttpStatus.ok)
        throw HttpException('HTTP ${response.statusCode}');
      final File file = File(path);
      final IOSink sink = file.openWrite();
      await response.pipe(sink);
      await sink.flush();
      await sink.close();
      if (!await file.exists() || await file.length() < 1024 * 1024)
        throw const HttpException('APK inválido o incompleto');
      final bool installStarted = await ApkInstall().onInstallApk(path);
      if (!installStarted && mounted)
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Android no inició el instalador. Verifica el permiso de instalación.',
            ),
          ),
        );
    } catch (_) {
      if (mounted)
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'No se pudo descargar o iniciar la instalación de la actualización.',
            ),
          ),
        );
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
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            TextField(
              controller: newPassword,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'Nueva contraseña'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: confirmPassword,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: 'Confirmar contraseña',
              ),
            ),
          ],
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(
              context,
              newPassword.text.isNotEmpty &&
                  newPassword.text == confirmPassword.text,
            ),
            child: const Text('Guardar'),
          ),
        ],
      ),
    );
    if (saved == true) {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      await prefs.setString('admin_password', newPassword.text);
      if (mounted)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Contraseña actualizada')));
    } else if (saved == false && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Las contraseñas no coinciden o están vacías'),
        ),
      );
    }
  }

  Future<void> logout() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setBool('session_active', false);
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(builder: (_) => const LoginPage()),
      (_) => false,
    );
  }

  String clock(DateTime value) {
    final int hour = value.hour % 12 == 0 ? 12 : value.hour % 12;
    final String minute = value.minute.toString().padLeft(2, '0');
    final String second = value.second.toString().padLeft(2, '0');
    return '$hour:$minute:$second ${value.hour >= 12 ? 'PM' : 'AM'}';
  }

  String date(DateTime value) =>
      '${value.day.toString().padLeft(2, '0')}/${value.month.toString().padLeft(2, '0')}/${value.year}';

  String duration(int seconds) {
    final int h = seconds ~/ 3600;
    final int m = (seconds % 3600) ~/ 60;
    final int s = seconds % 60;
    return '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  String money(double value) => 'C\$${value.toStringAsFixed(2)}';

  double get todayTotal {
    final DateTime now = DateTime.now();
    return history
        .where(
          (HistoryEntry e) =>
              e.end.year == now.year &&
              e.end.month == now.month &&
              e.end.day == now.day,
        )
        .fold<double>(0, (double total, HistoryEntry e) => total + e.amount);
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
    final double amount = table.status == TableStatus.playing
        ? table.liveAmount
        : table.amount;
    final String buttonText = table.status == TableStatus.available
        ? 'Iniciar juego'
        : table.status == TableStatus.playing
        ? 'Finalizar juego'
        : 'Cobrar';
    final Future<void> Function()? action =
        table.status == TableStatus.available
        ? (workdayActive ? () => startGame(table) : null)
        : table.status == TableStatus.playing
        ? () => finishGame(table)
        : () => collect(table);
    return Card(
      elevation: 4,
      color: statusColor(table.status),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Expanded(
                  child: Text(
                    'Mesa ${table.number}',
                    style: TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                      color: statusTextColor(table.status),
                    ),
                  ),
                ),
                Flexible(
                  child: Align(
                    alignment: Alignment.topRight,
                    child: Chip(
                      label: Text(
                        table.statusText,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(color: statusTextColor(table.status)),
                      ),
                      avatar: CircleAvatar(
                        backgroundColor: statusTextColor(table.status),
                        radius: 6,
                      ),
                    ),
                  ),
                ),
              ],
            ),
            Divider(
              color: statusTextColor(table.status).withValues(alpha: 0.35),
            ),
            Text(
              'Tarifa: ${money(table.rate)} / hora',
              style: TextStyle(
                fontSize: 17,
                color: statusTextColor(table.status),
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 7),
            Text(
              'Hora de inicio: ${table.start == null ? '—' : clock(table.start!)}',
              style: TextStyle(
                fontSize: 17,
                color: statusTextColor(table.status),
                fontWeight: FontWeight.w700,
              ),
            ),
            Text(
              'Hora finalizada: ${table.end == null ? '—' : clock(table.end!)}',
              style: TextStyle(
                fontSize: 17,
                color: statusTextColor(table.status),
                fontWeight: FontWeight.w700,
              ),
            ),
            Text(
              'Tiempo jugado: ${duration(table.elapsedSeconds)}',
              style: TextStyle(
                fontSize: 17,
                color: statusTextColor(table.status),
                fontWeight: FontWeight.w700,
              ),
            ),
            const Spacer(),
            Text(
              'MONTO A PAGAR',
              style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w900,
                color: statusTextColor(table.status),
              ),
            ),
            Text(
              money(amount),
              style: TextStyle(
                fontSize: 29,
                fontWeight: FontWeight.w900,
                color: statusTextColor(table.status),
              ),
            ),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: action,
                icon: Icon(
                  table.status == TableStatus.playing
                      ? Icons.stop
                      : table.status == TableStatus.pending
                      ? Icons.payments
                      : Icons.play_arrow,
                ),
                label: Text(buttonText),
              ),
            ),
            if (table.status == TableStatus.available && !workdayActive)
              const Padding(
                padding: EdgeInsets.only(top: 5),
                child: Center(
                  child: Text(
                    'Abra el día para iniciar partidas',
                    style: TextStyle(fontSize: 11),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget dashboard() => LayoutBuilder(
    builder: (BuildContext context, BoxConstraints constraints) {
      final double width = constraints.maxWidth;
      final int columns = width >= 1100
          ? 3
          : width >= 650
          ? 2
          : 1;
      final bool compact = width < 650;
      Widget metricCard(String title, String value, IconData icon) {
        return Card(
          elevation: 3,
          margin: EdgeInsets.zero,
          child: Padding(
            padding: EdgeInsets.all(compact ? 14 : 18),
            child: Row(
              children: <Widget>[
                Container(
                  width: compact ? 42 : 48,
                  height: compact ? 42 : 48,
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.primaryContainer,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Icon(
                    icon,
                    color: Theme.of(context).colorScheme.onPrimaryContainer,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 13),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        value,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: compact ? 21 : 24,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      }

      return SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(
          compact ? 12 : 20,
          compact ? 12 : 18,
          compact ? 12 : 20,
          24,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Container(
              padding: EdgeInsets.all(compact ? 16 : 22),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: <Color>[
                    Theme.of(context).colorScheme.primary,
                    Theme.of(context).colorScheme.primaryContainer,
                  ],
                ),
                borderRadius: BorderRadius.circular(22),
              ),
              child: Wrap(
                alignment: WrapAlignment.spaceBetween,
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: 16,
                runSpacing: 12,
                children: <Widget>[
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      const Text(
                        'Billares Don Miguel',
                        style: TextStyle(
                          fontSize: 26,
                          fontWeight: FontWeight.w900,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Panel central • Control de mesas',
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.88),
                        ),
                      ),
                    ],
                  ),
                  Chip(
                    avatar: Icon(
                      Icons.wifi,
                      size: 18,
                      color: lanIp != null ? Colors.green : Colors.red,
                    ),
                    label: Text(
                      lanIp != null ? 'LAN conectado' : 'LAN no disponible',
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            GridView.count(
              crossAxisCount: columns,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
              childAspectRatio: width >= 1100
                  ? 2.35
                  : width >= 650
                  ? 2.7
                  : 3.1,
              children: <Widget>[
                metricCard(
                  'Generado hoy',
                  money(todayTotal),
                  Icons.attach_money,
                ),
              ],
            ),
            const SizedBox(height: 14),
            Card(
              elevation: 2,
              child: Padding(
                padding: EdgeInsets.all(compact ? 14 : 18),
                child: Wrap(
                  alignment: WrapAlignment.spaceBetween,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  spacing: 14,
                  runSpacing: 12,
                  children: <Widget>[
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        Icon(
                          workdayActive ? Icons.lock_open : Icons.lock_outline,
                          color: workdayActive ? Colors.green : Colors.orange,
                        ),
                        const SizedBox(width: 10),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            const Text(
                              'Jornada de trabajo',
                              style: TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            Text(
                              workdayActive
                                  ? 'ABIERTA • ${clock(workdayOpenedAt ?? DateTime.now())}'
                                  : 'CERRADA',
                              style: TextStyle(
                                color: workdayActive
                                    ? Colors.green
                                    : Colors.orange,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: <Widget>[
                        if (workdayActive) Text('Juegos: $workdayGames'),
                        if (workdayActive)
                          Text('Generado: ${money(workdayGenerated)}'),
                        if (!workdayActive && workdayClosedAt != null)
                          Text('Cierre: ${clock(workdayClosedAt!)}'),
                        FilledButton.icon(
                          onPressed: workdayActive ? closeWorkday : openWorkday,
                          icon: Icon(
                            workdayActive ? Icons.lock : Icons.lock_open,
                          ),
                          label: Text(
                            workdayActive ? 'Cerrar jornada' : 'Abrir jornada',
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: <Widget>[
                FilledButton.icon(
                  onPressed: showTvConnection,
                  icon: const Icon(Icons.tv),
                  label: const Text('Mostrar en TV'),
                ),
                OutlinedButton.icon(
                  onPressed: checkForUpdate,
                  icon: const Icon(Icons.system_update_alt),
                  label: const Text('Buscar actualización'),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    'Estado de las mesas',
                    style: Theme.of(context).textTheme.titleLarge
                        ?.copyWith(fontWeight: FontWeight.w800),
                  ),
                ),
                if (!compact)
                  const Text('🟢 Disponible   🔴 En juego   🟡 Pendiente'),
              ],
            ),
            if (compact)
              const Padding(
                padding: EdgeInsets.only(top: 5),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    '🟢 Disponible   🔴 En juego   🟡 Pendiente',
                    style: TextStyle(fontSize: 12),
                  ),
                ),
              ),
            const SizedBox(height: 10),
            GridView.builder(
              padding: EdgeInsets.zero,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: columns,
                mainAxisExtent: width >= 1100
                    ? 350
                    : width >= 650
                    ? 365
                    : 390,
                crossAxisSpacing: 14,
                mainAxisSpacing: 14,
              ),
              itemCount: tableList.length,
              itemBuilder: (_, int index) => tableCard(tableList[index]),
            ),
          ],
        ),
      );
    },
  );

  Widget historyPage() {
    final Map<String, List<HistoryEntry>> groups =
        <String, List<HistoryEntry>>{};
    for (final HistoryEntry entry in history) {
      final String key =
          '${entry.workDate.year}-${entry.workDate.month.toString().padLeft(2, '0')}-${entry.workDate.day.toString().padLeft(2, '0')}';
      groups.putIfAbsent(key, () => <HistoryEntry>[]).add(entry);
    }
    final List<String> keys = groups.keys.toList()
      ..sort((String a, String b) => b.compareTo(a));
    return ListView(
      padding: const EdgeInsets.all(16),
      children: <Widget>[
        Card(
          child: ListTile(
            leading: const Icon(Icons.today),
            title: const Text('Últimos 7 días'),
            subtitle: const Text(
              'Movimientos organizados por fecha de trabajo',
            ),
            trailing: Text(
              money(todayTotal),
              style: const TextStyle(fontSize: 19, fontWeight: FontWeight.bold),
            ),
          ),
        ),
        if (keys.isEmpty)
          const Padding(
            padding: EdgeInsets.all(24),
            child: Center(
              child: Text('No hay movimientos en los últimos 7 días.'),
            ),
          ),
        ...keys.map((String key) {
          final List<HistoryEntry> items = groups[key]!
            ..sort((HistoryEntry a, HistoryEntry b) => b.end.compareTo(a.end));
          final HistoryEntry first = items.last;
          final HistoryEntry last = items.first;
          final double total = items.fold<double>(
            0,
            (double sum, HistoryEntry e) => sum + e.amount,
          );
          final DateTime day = first.workDate;
          final bool isCurrent =
              workdayActive &&
              workdayOpenedAt != null &&
              day.year == workdayOpenedAt!.year &&
              day.month == workdayOpenedAt!.month &&
              day.day == workdayOpenedAt!.day;
          return Card(
            margin: const EdgeInsets.only(top: 12),
            child: ExpansionTile(
              initiallyExpanded: isCurrent,
              title: Text(
                date(day),
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 18,
                ),
              ),
              subtitle: Text(
                'Apertura: ${isCurrent ? clock(workdayOpenedAt!) : clock(first.start)} • ${items.length} juegos • Generado: ${money(total)}',
              ),
              children: <Widget>[
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      workdayClosedAt != null &&
                              day.year == workdayClosedAt!.year &&
                              day.month == workdayClosedAt!.month &&
                              day.day == workdayClosedAt!.day
                          ? 'Cierre: ${clock(workdayClosedAt!)} • Efectivo físico: ${money(workdayCashClose)}'
                          : 'Último movimiento: ${clock(last.end)}',
                    ),
                  ),
                ),
                ...items.map(
                  (HistoryEntry e) => ListTile(
                    leading: CircleAvatar(child: Text('${e.table}')),
                    title: Text('Mesa ${e.table} • ${money(e.amount)}'),
                    subtitle: Text(
                      '${clock(e.start)} - ${clock(e.end)} • ${duration(e.seconds)}',
                    ),
                  ),
                ),
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
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Text(
                'Tarifas fijas',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              const Text('Mesas 1 y 2: C\$120 por hora'),
              const Text('Mesas 3 y 4: C\$100 por hora'),
              const Text('Mesa 5: C\$70 por hora'),
              const SizedBox(height: 12),
              const Text(
                'Las tarifas no pueden modificarse desde el administrador.',
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: () async {
                  Navigator.pop(context);
                  await configureThermalPrinter();
                },
                icon: const Icon(Icons.print_outlined),
                label: const Text('Impresora térmica'),
              ),
              const SizedBox(height: 16),
              if (lanIp != null) Text('Receptor TV: http://$lanIp:8080/tv'),
              const SizedBox(height: 8),
              const Text(
                'La TV muestra únicamente la pantalla de mesas; el panel administrativo permanece en el celular.',
              ),
            ],
          ),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: changePassword,
            child: const Text('Cambiar contraseña'),
          ),
          TextButton(
            onPressed: () => checkForUpdate(),
            child: const Text('Buscar actualización'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cerrar'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text(
        'Billares Don Miguel',
        style: TextStyle(fontWeight: FontWeight.bold),
      ),
      actions: <Widget>[
        if (checkingUpdate)
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 12),
            child: Center(
              child: SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
          ),
        IconButton(
          tooltip: 'Configuración',
          onPressed: showSettings,
          icon: const Icon(Icons.settings_outlined),
        ),
        IconButton(
          tooltip: 'Cerrar sesión',
          onPressed: logout,
          icon: const Icon(Icons.logout),
        ),
      ],
    ),
    body: tab == 0 ? dashboard() : historyPage(),
    bottomNavigationBar: NavigationBar(
      selectedIndex: tab,
      onDestinationSelected: (int index) => setState(() => tab = index),
      destinations: const <NavigationDestination>[
        NavigationDestination(
          icon: Icon(Icons.table_restaurant),
          label: 'Mesas',
        ),
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
                  Text(
                    value,
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget workdayView() {
    final String opened = workdayOpenedAt == null
        ? '—'
        : workdayOpenedAt!.toString().replaceFirst('T', ' ').split('.').first;
    final String closed = workdayClosedAt == null
        ? '—'
        : workdayClosedAt!.toString().replaceFirst('T', ' ').split('.').first;
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final int columns = constraints.maxWidth >= 900
            ? 4
            : constraints.maxWidth >= 600
            ? 2
            : 1;
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
                      Icon(
                        workdayActive ? Icons.lock_open : Icons.lock_outline,
                        color: workdayActive ? Colors.green : Colors.orange,
                        size: 30,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            const Text(
                              'Jornada de trabajo',
                              style: TextStyle(
                                fontSize: 21,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            Text(
                              workdayActive ? 'ABIERTA' : 'CERRADA',
                              style: TextStyle(
                                color: workdayActive
                                    ? Colors.green
                                    : Colors.orange,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                      ),
                      FilledButton.icon(
                        onPressed: workdayActive ? closeWorkday : openWorkday,
                        icon: Icon(
                          workdayActive ? Icons.lock : Icons.lock_open,
                        ),
                        label: Text(
                          workdayActive ? 'Cerrar jornada' : 'Abrir jornada',
                        ),
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
                  _summaryCard(
                    'Generado hoy',
                    'C\$ ${workdayGenerated.toStringAsFixed(2)}',
                    Icons.payments,
                  ),
                  _summaryCard(
                    'Efectivo físico',
                    'C\$ ${workdayCashClose.toStringAsFixed(2)}',
                    Icons.account_balance_wallet,
                  ),
                  _summaryCard('Apertura', opened, Icons.schedule),
                ],
              ),
              const SizedBox(height: 16),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      const Text(
                        'Detalle de jornada',
                        style: TextStyle(
                          fontSize: 19,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 10),
                      Text('Inicio: $opened'),
                      Text('Cierre: $closed'),
                      Text('Partidas registradas: $workdayGames'),
                      Text(
                        'Total generado: C\$ ${workdayGenerated.toStringAsFixed(2)}',
                      ),
                      Text(
                        'Efectivo físico al cierre: C\$ ${workdayCashClose.toStringAsFixed(2)}',
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
