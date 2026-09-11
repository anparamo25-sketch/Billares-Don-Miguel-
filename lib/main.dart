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
        final parts =
            address.address
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
      await const MethodChannel(
        'billaresdonmiguel/network',
      ).invokeMethod<void>('acquireMulticastLock');
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
    start =
        map['start'] == null ? null : DateTime.tryParse(map['start'] as String);
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
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Contraseña incorrecta')));
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
              child:
                  loading
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
                                onPressed:
                                    () => setState(() => obscure = !obscure),
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
  final List<BillTable> tableList =
      tableRates.entries
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
                'amount':
                    t.status == TableStatus.playing ? t.liveAmount : t.amount,
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
        history =
            data
                .map(
                  (dynamic item) => HistoryEntry.fromMap(
                    Map<String, dynamic>.from(item as Map),
                  ),
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
      builder:
          (BuildContext context) => AlertDialog(
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
                onPressed:
                    () => Navigator.pop(
                      context,
                      double.tryParse(
                            cashController.text.replaceAll(',', '.'),
                          ) !=
                          null,
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
    final String url =
        port == 80
            ? 'http://billaresdonmiguel.local/tv'
            : 'http://billaresdonmiguel.local:$port/tv';
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder:
          (dialogContext) => AlertDialog(
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
                          const SnackBar(
                            content: Text('Dirección de TV copiada'),
                          ),
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
      'PCFkb2N0eXBlIGh0bWw+CjxodG1sIGxhbmc9ImVzIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9InV0Zi04Ij4KPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEiPgo8bWV0YSBodHRwLWVxdWl2PSJDYWNoZS1Db250cm9sIiBjb250ZW50PSJuby1zdG9yZSwgbm8tY2FjaGUsIG11c3QtcmV2YWxpZGF0ZSwgbWF4LWFnZT0wIj4KPG1ldGEgaHR0cC1lcXVpdj0iUHJhZ21hIiBjb250ZW50PSJuby1jYWNoZSI+CjxtZXRhIGh0dHAtZXF1aXY9IkV4cGlyZXMiIGNvbnRlbnQ9IjAiPgo8dGl0bGU+QmlsbGFyZXMgRG9uIE1pZ3VlbCAtIFRWPC90aXRsZT4KPHN0eWxlPgoqe2JveC1zaXppbmc6Ym9yZGVyLWJveH1odG1sLGJvZHl7bWFyZ2luOjA7d2lkdGg6MTAwJTtoZWlnaHQ6MTAwJTtvdmVyZmxvdzpoaWRkZW47YmFja2dyb3VuZDojMDUwNzBiO2NvbG9yOiNmZmY7Zm9udC1mYW1pbHk6QXJpYWwsc2Fucy1zZXJpZn0ud3JhcHt3aWR0aDoxMDAlO2hlaWdodDoxMDB2aDtwYWRkaW5nOjAgMjBweCAxNnB4O2Rpc3BsYXk6ZmxleDtmbGV4LWRpcmVjdGlvbjpjb2x1bW47b3ZlcmZsb3c6aGlkZGVufWhlYWRlcntoZWlnaHQ6MTE4cHg7ZmxleDowIDAgMTE4cHg7cGFkZGluZzoxMHB4IDhweDtiYWNrZ3JvdW5kOiNmZmY7Ym9yZGVyLWJvdHRvbTozcHggc29saWQgIzE1NTdjMDtkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxLjE1ZnIgMWZyO2FsaWduLWl0ZW1zOmNlbnRlcn0udGl0bGV7anVzdGlmeS1zZWxmOnN0YXJ0O2NvbG9yOiMxNTU3YzA7Zm9udC1zaXplOmNsYW1wKDI4cHgsMy4zdncsNDhweCk7Zm9udC13ZWlnaHQ6OTAwO2xpbmUtaGVpZ2h0OjEuMDU7bGV0dGVyLXNwYWNpbmc6LjNweH0ubG9nb1dyYXB7anVzdGlmeS1zZWxmOmNlbnRlcjtoZWlnaHQ6MTA4cHg7d2lkdGg6bWluKDE5MHB4LDE4dncpO2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OmNlbnRlcn0ubG9nb1dyYXAgaW1ne3dpZHRoOjEwMCU7aGVpZ2h0OjEwMCU7b2JqZWN0LWZpdDpjb250YWluO2Rpc3BsYXk6YmxvY2t9LmxpdmVCb3h7anVzdGlmeS1zZWxmOmVuZDt0ZXh0LWFsaWduOmNlbnRlcjtjb2xvcjojMTU1N2MwfS5jbG9ja3tmb250LXNpemU6Y2xhbXAoMjBweCwyLjJ2dywzMnB4KTtmb250LXdlaWdodDo5MDA7bGluZS1oZWlnaHQ6MS4xfS5saXZle2ZvbnQtc2l6ZTpjbGFtcCgxN3B4LDEuOXZ3LDI1cHgpO2ZvbnQtd2VpZ2h0OjkwMDttYXJnaW4tdG9wOjZweH0uZ3JpZHt3aWR0aDoxMDAlO2ZsZXg6MTttaW4taGVpZ2h0OjA7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoNSxtaW5tYXgoMCwxZnIpKTtnYXA6MTRweDtwYWRkaW5nOjE0cHggMCAwO292ZXJmbG93OmhpZGRlbn0uY2FyZHtoZWlnaHQ6MTAwJTttaW4taGVpZ2h0OjA7Ym9yZGVyLXJhZGl1czoxOHB4O3BhZGRpbmc6MTZweDtib3JkZXI6M3B4IHNvbGlkICM2NDc0OGI7ZGlzcGxheTpmbGV4O2ZsZXgtZGlyZWN0aW9uOmNvbHVtbjtib3gtc2hhZG93OjAgOHB4IDE4cHggcmdiYSgwLDAsMCwuMjgpO292ZXJmbG93OmhpZGRlbn0uZ3JlZW57YmFja2dyb3VuZDojMTAzYjIyO2JvcmRlci1jb2xvcjojMjJjNTVlfS5yZWR7YmFja2dyb3VuZDojNTExYjFiO2JvcmRlci1jb2xvcjojZWY0NDQ0fS55ZWxsb3d7YmFja2dyb3VuZDojNTY0OTBhO2JvcmRlci1jb2xvcjojZWFiMzA4fS5udW17Zm9udC1zaXplOmNsYW1wKDI0cHgsMi43dncsMzhweCk7Zm9udC13ZWlnaHQ6OTAwO2xpbmUtaGVpZ2h0OjEuMDV9LnN0YXR1c3tmb250LXNpemU6Y2xhbXAoMThweCwydncsMjdweCk7Zm9udC13ZWlnaHQ6OTAwO21hcmdpbjo3cHggMCAxMHB4O2xpbmUtaGVpZ2h0OjEuMDV9LmdyZWVuIC5zdGF0dXN7Y29sb3I6IzRhZGU4MH0ucmVkIC5zdGF0dXN7Y29sb3I6I2Y4NzE3MX0ueWVsbG93IC5zdGF0dXN7Y29sb3I6I2ZkZTA0N30ubGluZXtmb250LXNpemU6Y2xhbXAoMThweCwxLjc1dncsMjVweCk7Zm9udC13ZWlnaHQ6NzAwO2xpbmUtaGVpZ2h0OjEuMjg7bWFyZ2luOjdweCAwfS5saW5lIGJ7Zm9udC13ZWlnaHQ6OTAwfS5wYXl7bWFyZ2luLXRvcDphdXRvO3BhZGRpbmctdG9wOjEycHg7Ym9yZGVyLXRvcDoycHggc29saWQgcmdiYSgyNTUsMjU1LDI1NSwuMjUpfS5wYXlMYWJlbHtmb250LXNpemU6Y2xhbXAoMTZweCwxLjZ2dywyMnB4KTtmb250LXdlaWdodDo5MDA7bGV0dGVyLXNwYWNpbmc6LjVweH0ubW9uZXl7Zm9udC1zaXplOmNsYW1wKDMxcHgsMy4zdncsNDhweCk7Zm9udC13ZWlnaHQ6OTAwO21hcmdpbi10b3A6NHB4O2xpbmUtaGVpZ2h0OjEuMDU7Y29sb3I6I2ZkZTA0N31AbWVkaWEobWF4LWhlaWdodDo3MDBweCl7aGVhZGVye2hlaWdodDo5NnB4O2ZsZXgtYmFzaXM6OTZweH0ud3JhcHtwYWRkaW5nOjAgMTRweCAxMHB4fS5sb2dvV3JhcHtoZWlnaHQ6ODhweH0uZ3JpZHtnYXA6MTBweDtwYWRkaW5nLXRvcDoxMHB4fS5jYXJke3BhZGRpbmc6MTJweDtib3JkZXItcmFkaXVzOjE0cHh9LnN0YXR1c3ttYXJnaW46NXB4IDAgOHB4fS5saW5le2ZvbnQtc2l6ZTpjbGFtcCgxNXB4LDEuNnZ3LDIxcHgpO21hcmdpbjo0cHggMH0ucGF5e3BhZGRpbmctdG9wOjhweH19QG1lZGlhKG1heC13aWR0aDoxMTAwcHgpe2hlYWRlcntncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmciAxZnJ9LnRpdGxle2ZvbnQtc2l6ZTpjbGFtcCgyMnB4LDN2dywzNnB4KX0ubG9nb1dyYXB7d2lkdGg6bWluKDE1NXB4LDIwdncpfX0KPC9zdHlsZT4KPC9oZWFkPgo8Ym9keT4KPG1haW4gY2xhc3M9IndyYXAiPgo8aGVhZGVyPgo8ZGl2IGNsYXNzPSJ0aXRsZSI+QmlsbGFyZXMgRG9uIE1pZ3VlbDwvZGl2Pgo8ZGl2IGNsYXNzPSJsb2dvV3JhcCI+PGltZyBzcmM9ImRhdGE6aW1hZ2Uvd2VicDtiYXNlNjQsVWtsR1JoeFJBQUJYUlVKUVZsQTRXQW9BQUFBUUFBQUEvd0FBL3dBQVFVeFFTRTBSQUFBQkRBWnRHMGxLK01PZWYrOEFSTVFFOExUNW52VmFmTVE5eXpzYmRtdzNVdU1KSUhDRDA1bUxQWGRibkxtTU9hNDF0Nnc4WTgzTXc4UXpPSE9mejRsNmxQNEVBd29WcVN0KzFSdTJiY3VjWnZ0M1RtVGlDZkVRM0c4OFZKQXFVSGQzZDNkdmNiL3Z1cnZpVWd2VW5lSlN4U0pvZ2p2eDVEeU8vY1BNbkRQWGNWNXp6YkxjbnlKaUFqelZ0aTNiMmlSSlRVbzVBU21tV0tRbVJBU0IwQkVnUWtNUVNFa1RBdCtZUTVLems3V1RjNlFhRVJPZ29tdnh3S0VETytXbEp2bVRrdnpKR2QxUDdhUmlhRi9SMGRkK3NxbW0vbERWMm1VTEZ5NWE5UHVTbGRzYnFyOGNjWDVKaDhMc3JLd0IzV0tjdkFjVzdtb0F3TVF3WkEwQWRmdXFOMjNhZUhEZnk5MWltT1E3S2dBd0VlbVFSRnByVFVTYUdJSE0yRGYzNW12dXo0eEZXbDIvRkNCSGRYQUVManBhcWV5WUluSG9sUFdBSm9lMXBrQ3RkUXNPem51bDRyeFk0Z0lDdEE1RFJ5Q2tEZ1NBZmVlMmo0OFZXazFGaTlhYWdtb2RvRU9HMEtGMElBVnExT3dlRXlOYytoZCtRTHAwQTZTVTlQLzVUNTZJQlhMZkk3UkFSaEpJa2g0VHc4Z3Y1WG0rWGt0QldwTWhPbjJvQWdoLzlQQjIvcnQzUW11dGt3UTZtUVVvU3FJMXlrL3djaVUvQWpyb1NPYXloSWh3OEVidmRzWXVFRkVRSUtIUkJWYm9BSUUvTzg2akRUOEFUVVJrTU5tQ3NJd0lqUy9HZTdFQkZhRGdtZ0lwcHBuVkdtc1N2SmZ2NHAwZ0EwaW9TUUxac09tTlhNK1Z1aGJhZ0VjWWdvRnhwK2d3bGgvbHRjNDVSTUVaZ1hYVFFJczAxdVY0cXdHN29ZT05qdTNiSXo0MDJGdDlBSXJnSE93d2l2TE9YdXFpR3BLd1BaWVVlNmYwUmF3akViSzdFNFRSM2lsN1BjZ1ZkWUFEUm5pbnk1cklKVExCdTQvMlNvWGxjSWxwalg4NmVLU25RQzZxQTBTNDBDTzlabzlWRHBRbVJ4ZWZMWDEyc1l1b1VVTVE3bzh1dHNiUEFybEpNc1MxVjN1aC8reGpPelNWUG1KQ05RMzFRcGxySUVydFdUR1BPWEVlYUhBZGl4bzFXNnhPOEQ2K21kQ1dWRHZCKzN0NkgxWHFNdE40MitkNUVoYlpwYTRxei9JOHc1dkladXZzelZHZTkyVm9keXZQOHp6WE1kbGQxdWVXSVo3bkJtaTdWdHBvSHVwNUpvc3gwVEYza0FrUGU1NlIwRnJHZ2FwRWVDdkQ2MXpyWHQyVzhuRTUzdVlKQzl5TWdWV2RQYzJ3V2hKM0lKWm1lNW5VRFhBL3d0TmVSbjBCY2xJdjhWZHk3T1VZMS9mMU1sT2huZGhiSFpuRmxWN21NWkI3Wk1Helh1Wmw5MWlLMytOZExDWFRzdmdmb2FQQndXNnVkZmEwTlpVLzNlVzNTVjJxS1JyaWVzdUd2ZmpsbkJGSFJ5TG5JMGJnKzRrMkRXeDBJUzE0eTZxNFNSb0FHbDVPbjBwZEFOS2FpRERScGt0WXUwOGxmclRxVVRBUkVXUHVUMmNlQW1sTlJKcm9Ib3Z1UW5UNDAyL1JCZlZNZ1pydzU0blVOYUNRYUR6WG5pNmIyVExkb3lMTG5pSDdRU0h4VjVKWjhWNER3dWJPMXNTdkJFV1Bjb3R0K2Riay93c3kyRk5vbGx0dFF2ZzV5NWIyTzRLNHdzMHNxaXF3SldrdXlHUmJ0cGx2bWhGaFhySWwxNExJUmN0bnJOSFltRzJKNzFWb2JUTFhaNllHSEdZVHdnUkxqbTlnMjJiTDFxUmFjaGVZRE5Gd2dncjNRYkFKTjU1bngxbEVyT2J5V0JSbng2Q0RJS054S3V5RU9UQWg3QjVpeGRVSXlQWG1LQ3M3clFlWjR0T2s4RlM3YlRBaGxMVzE0Um9RdmNHelZtVDhCRExGOXZZcWtoZHJOaUY4bldMQitRRzUzOE0yeEwwSE1tVjloWXJzQkJnUi9tZkJzWTFNTDRocmJYZ1laSXhKS3NJSmMySEVkTHU4ZHJzUkZjNno0TndHTTVUNkk2VTY3NEFKY2MxcDRscFZSZ1BXSjhuclVRVXl4ZFlPS3ZKWE5MTUpZVXMzYVJrYm9nSHFTOFJsTDRJMjRhWUxsWk5qWUVSWWxDVXNaYTA4UGFDbXM3VDQ2U0JqakZlT0puOERJOExyd2dvMlJRTnFtZHBMMkJNZ1k1UW1PYU02VjhPSTlhMDd4VjJ5bXJTNE03Ri9SSmFrOHhyWUNKVnRsTlBYRUpzUWpneVRNL2hyZ0tJa3NPWmFuNWlCdTBHbTNIeStjdjV0R0JIVzV3dHBOYVVPVE5FVG1OZGRTTzYvSUdPTVZ3SnpWc0dJTUQxQnhEbC9BeFErRnlQR2pyc1RKY1JQQlJuajJ5UUpxbVFQakFnVEJPUzkwUXlLdGhyNHJwZUE4U0JqVkhSUU1tOExnK2xheDRiK0RaRHI2d3dSWThjMWpsMmoyWWliemxSQ0V4ZkFpTEM3dHpPSno5U0JvalQ0elN4bmV1NEdHZU1sSmJielpoZ1JsdVE0MGZWTGdLSTI0N2VlVHVRdUFSbmpsd3c1NnJRNk50S1lrUkM1UDFXQlhGbjNJTUtPQ3lQbm53Y3lSblUzSlhrOGpJandlTVFlYmZwbkxxMmJFQnJ1aWRnSWtERzNYS2hFcHkrRUdUZWNIWm1NdDRDOFBuaGlZbVRPYm1BenZLNkVkOTBLSThLV3pwSG85aHVZUGlCalRuWWt1bTBGR1dOUnBqUjFtV1lqd2c5cDRmVmNEL0tHakc5YmhaZTFDTm9JZS9vbythL0NqUEJDV0FNclFaNFIzK1NIRS9jdU5Ka3kzNndzelA0YlpreTNoM0hHTG1qdlFGaldKWXlIUWViNHhHZURHbGJQUm9TREE0ek9QZ2hOWGhKL3RqRWFYaGNHMWhVb095ZkNqTEFpMitETVF5Q1BpZDl5RGRwVmdJeFJQMXhabXZZdGdtbXRpWWd3MVIvaTlMM0k1OFFQUlNIU3ZvWTJZanl1ck8yOEF5Wk1oQkhCVGpzQ3FxVkt2WXZXRUJabUIzc0paSTdQNCsxUmQ0R0RVVkErY2t4QXR5MmdTRlBqZGVyeGNWekFSUzFzaHAxZGxNV0o4eEJBSVFpckM1UnF1eElVTGtDaitqVUlZNVJTUGF0QXh0eHl1Yks2Y0IwQ0RQRkZmTUV5NkREb0xuaFA1b2RVMWdxUUtUT2VWWmFmVnM5bWpJbXpRT0gyZ0xjak5GNzhDc2dNaTlKc1UxTmdSZ1JRbUl5L0hxR3VoY3h4b0VSWjMrcFBhTE93YVNia0k0S0oySURwWnVXQ0o5U3dFL1ErcFFrK1ZxNDRBZzd3Q3JDZElTcUszU0g1RzBTS3dic2R6UFduS3Bmc3ZoY1JZVEREZkFsTVZxNzVNRWh2OHlXeE9OMDkvUE1SaWZUeVViR25yM0xSRHR0UUVTQ1FsOVpWek5jclY3MjB4WXB2aTVrK2QxRlRJVTF2NWc0b2I2dGNkcTZuYUxKcXNuTFpTelJMMElhZmdDdUwzQ1Z2UFVqd1c2eldlTjFkWGdaNWJtNDh4VTBHMW5FNDhBV0FKWVNsU2U3aCt3SVVWcnJxaDJDQ2NMTjdERzNpc0ViZkxhc3FDOTBpOFNlUTQ3VGZiaDdqM2VKQ0V0aksvV0d6cW54M1NGNEVLYms5ejZHc0l6emxEamVESXErZFFLcmhHaFJzeUxzNnVvRi9tUU9PWkFVdnBqSEpEWVpxZGlDRHZFQnFXTVhiV3J2QVZGQm9waExnd2JQcTdUSFN2cTRISWdNa29SMitURVhXY1dQL21kSUd2VUMrS3ZORnR1VldMR0FNWmdBK0FlR2JlTXV1UjZyU1NYTUVTR2grQTI0YVpKZHZmcVNlalhSTDhoSHhyRjNkRDBTR1JvQlVQdklwTnVkWjlTUW9Pa1VuNUJQalZwdmlGNElxQno0eXZvdXpxT2VoaUVBKzFwR2VGajBGY29oUFJIakNudmpmSWdMcHN3RDRFci9GVzlObFA0ZEZJTHZ3SVk3OHg1cGJvY09qUmZjZDJBb20xQkRoVVd2bVdKUXpvSWFkb0VJaS9CUm5TYzRXVVBqdlE3WXVpQWtSNyt0cXlTbWFISDFrNVJHMUV5eExRVlBqRGt2R3dwbGFSZzZHc1dHZXE2bzFQcmRrZ1Jqb3NBajJBS2hLY2dxaHVzQ0tWcHZrcEE4WHlKcHo4VzZjRGNjMHNZbExSaGZ0dXdWSjJJcnhzQTNYZ0l4YzVrVjJwTUZPaE5yaEZvd3pNUFhhc2ZHYUQ1YnBHS0dpbzd6NUJsdmVDQmJzYWJkRFdPQ1hsclplVmc3VEF2WlExeG1DY1o2MGRudWkzS2FxWmVseE1NS3owZ1kxY2pna0FhaDY2UW5LN0h6akUzWUppTmpzZVFldDhZeW9kaGhRazBUekhQZzNSZGc5QVN5QkFsMVU3QXJZcE1ram5VeGlXNTZ3Q1FGa3AzcEF0b0c1RE5OcXorMXJKK3dEa01WNndEekRFeVJSRzVwSjB2VTVZT053TjJIejVEbHl4U3BhNlN3czRkcStzbHFYc3pUMUx1MHBnQnhvcS80b1ViNFBRWkcyeDNQQ0M4MUMraDVBalFORkRXeDBYWEluYnRUbTVpR2lQa2EyVjNQOUFjMEpMU2RJS3FuaGI1S2p1Zms0U2ErRDl0VlcxdWdkZHRjR3ZhWWhndktxWkdsajhXbFFBY3ZTNm5QVFlFRTNna1QzWEhLZ1Y2SFJPRWhPM0EvQzByTURSK2xESFpxMHRUT3RobVBrdE4wbmJmNGtqZTNjdEVVdHcrVDhVZDlLaytTUnU3YndvSnkvL0RNdmJTc3hwWmFvVzdUeGlaeS9kcmdlTXk2enB3KzcyMmdzVHBEeWs3KzFlQmViV1RLcUpnNldhRWw1bHBSZi9iMjFQd1VBUzhZMUdWaXU2U1RwdVl5d3ExaktyLy94U3M5OThrZzBlL1BoYmxKKzh6K25sRUt1UHFCcm9GWFhYOG9mL245TWovcUlRS04rZ0ppRDRiZ0dQZy9QUmwwL0taMzNTUUw0VGtkNlNHbGRMZWtMQTJsaVo3R1VqSEt3V1FyVklvQlBvRVhyMHFVa0xBZXp3ZDRQWGsxYkdXWGsxM2dwYWc3SXByeWNadllCUEQ1UVlrZUJQTHZQaWFTamNaK2NpMktPTkZ0T2t0T2pCcDV0VUFkQ1ltdWVIUDhLNSt5d2dDSDFmUkxuNWlyQmt3UjRrTHFibHFqcjFJazdKQTFwWXFmU1dibmdRTFZJWFJPZkE2anRLY20vQlBadDZSYWFxRVZaYXBLSEF6L0ZTMUkzT3VidFlDd1Qrb2htcVk5RU0zQ3RFcDM1RHg3cTFWYU9iQXB6YVkxaVE1WXNkVmVRMUYxL3V5MzVmaVU4OCs5L1B2SldGK2FhRW1scWVtdTlMZ0ErQk5HYTAyVmx2cXJ6M3dicUgvUUo2cjRJdk11WEJqN0tFdE8vQWlSUzNVV3ZBeHhBaEcremhYUmFCL0krT1ZKalRwS0lwSzlBanF1cGg0SlI0QTduWW95SW8xdFloR1dzb0QwRDhQQWxxdklrZEQ4TTU2STVnRlY2Q0p2dEtKQ2dSa29vcDdrbzA3MllWeGlwUlBxL2dCMDhmL3pZTGdDUFY4UVhmaG1xUXdVYjZKd1dBZno0OFlNek9BWTJzWVUxeFVycVdEamhJdFpCQnhqSTlYd3dQYUNFcG84N3dnYUZNd0FOR2l6SnpCdnprVEhKSW81ZURKQlltZ250UnI0TEFULzBGSERaZnBEZ3FlYUN0SGd0Wmlac0g3YXM5MEdRdE96TE1pN0hBWVR5ZktjZUE3azIxL0Fzd3FsTzNSSmw0QWdQSVdZaTRvWVNwM0xMRVdWNGthQW9qWE5LUFJURlhwSDVIT1Y0em5xNFhNYkpsbHhFNHplL2MrcjZTTUMxM3JmeEZDVXdhU0VNNE1GZG9JNEhkOE1NSmZKODRoQmNoUjNJN2JtbXY0ekU3NkdEcFpYL0d2QytFanE4aWNLOVRNb0JkdEFlYk1jMWZhWEVsU0tjWENFbldjTUIrRUNKSGQ3TXdlaGNFc2pTWFhJUUgrd3R4emNESWRnTTF0VHFRQllVSDRCbmxlRCtoN21WYXJpRmI0SzlYU1MxMzR0R09kZktadGx0WTVha20wQ3JVcFUzM1kvMWFZSjhwVTU5ZEx3bXFNdCtOZ09XcVY3RlMyM0lsUE1BS01yZEU0WklueTdHdnp5YzdKR0Z3QXVvUlF6aFhURkhOWEk0T3k1aGp1WU1RQkxnbE95eE9WdktVeUJYM1NUbmJjbDBocENrNVM1VFNkNGFyd3NaMk1SdWQwL1lia09HalBHZ29FQWRuOG9CMW1lSlNQMUh3bWZIQnlKT2F1RmdJWi9XTTZvS0pEd1A4c2JxQVlSTEJXUnVzTWxYaWMzdFpnbzRuOG1ZQzhFT3dEN3V0cXQ0M1J2UXNvUmh5bUdJWGJJYXdROWdYTG9zL2UvL3pLNk1vTTM3SzVmTWZmN0JHejg0QUVScWxwek1IQVRZOU4ycVRmdnFFVElNWm5hQzhMNWpaMlZIQkczY3VmcXpGKzg5OTVqMm1YRXFzTnZFTFFBTE9Ec0lzUFdaUXBXWTNiNy82VGMrOWQ3M2YxZlZFSUl6RWJGalczT2RldnVmU3hpQnpmczIvUERHbzVjZVUreFg0Ulk5OUNjQVZ5Tm1vUHpKSW1XY1hOajdsSnZIdmxmNlIxVXRJWGhZYk1SOHRrT3RLcXNZZ2MzNy92Mzh2emVkMERGRFJUemx2UGsxQUxzV0E3VGlyaHdWWVg5KzcyRlhQZjdPd3NwREdvRnN3aWFFTnh5NmdHRU9nWHVYVGgxNXhjQjJ5Y3I1WG84dGJ3Skl1dzhEMlBUcXlVbkthVjltNStNdWYreUR4VnVhQUlBanNhM1FtZmN3d3dEcTE4MTY0dXgyOFVwdTRxQ3hmeFBBWWFuN3FTMEdVRDN6c2h3bE55NzdtRHRlK0dFSEFXQm1OaUZjNTBoV0pVaWZBVFJ1bUg1N3YzUWxQMjM0YTJzMWdMRGNyZzBBdTJkYzNscFpXRFQwOFFWVkRJQ05aanB5RGhrQzJQNzFZOGRrS0d2VFRwcTByQUhBUU15Ui93UnFWcjEwWVZ0bGIvNUpUNVp1QTZCRDdXamp4Q3NJWUFaUVBmT1NJbVY3NG9BSFM3Y0Q0R0RDbVprQWNOVVh0L1gwSyt2enpwKzFIVUFRd3BsT1BJM2dkZDlkV2FSY3N2akMxemN3QUpiQ29RQ2c5dThYenl4UWJsbDgvVGNIRWZSUUx5ZlNKNjQ5Y0dUSGIwLzE5U2szelR4MTdIZlZCRUJFY0FCTmxaL2UwU2RGdVd2WFcrYXQyYkp1N2pEbGJHcUhyb1UrNWNMNUp6Mno2QUFBRnNBQWRuL3o2TUFzNWNvcE9ha3Flc2QxdXVpdE5RMEF3QTRBYUY3NzltVnRWY3lhT3VEKytkVUFFQmtBaDM2ZmVFS2Fpblh6aG8zOXZRNElDOERPV1RkMzlhbllPSzdmNkQ5YndDWkEzZGMzdEZZeGRlclFtWTNnWU1DaE4wdFVERDV3YWpPSVNLUHUxWjRxUnIrd0NxUlJNVnpGN2oxWEE3OTBWTEY4MisvbjVxallQaUZPL2I4dkFGWlFPQ0NvUHdBQXNMb0FuUUVxQUFFQUFUNTFMcEpHSktLaG9USDZPNENRRG9sc2J2eERBd0N6QUNTUUxmT2RuOGgxOEdsZlNmM3IwTzYvL2lmN04vZy8rai9ndmVYME1kVCtWbjBCLzV2V3IvbS8vSC9pUGN6K29QL1g3Z242eGVwNy9pZnNmN292M0w5UWY3VmZ0NTd5WC9FL2JmM1lmNFgvZ2V3Ti9VUDlCLy8vWGM5amowQ2YyKzlZci92L3ZEOEtIOWYvNUg3aS85ejVHLzJsLy8vc0FmLy8yNGY0Qi8vK0pGL3Izb0s4Q3Z5WDVhZWEvNDk4Ky9qUDdsL2t2K1ovaVBqdisxdjlEd2lkSWY5ci9QZXFmOHgvQVA3WCs4L3U1L2gvZC8vamZiZDZYL21QNy8veGY4VjdBdjVCL1F2OVovZmYzSTk4RDdqL2w5Nk5hYi93LzZQMkR2ZGY2Ly94djhiK1Rud1FmZitjdjJpLzYvdUJmMDMrNGY4bmo3ZldmWUIvcHY5Ly85WCt1OTJIKzYvOS8razlCbjZOL28vL1gvc3ZnSy9tLzl0LzZmK0Q5dWovLys3WDkwdi8vN3EvN20vL1J4SjRVaEZ6MEI3Um84M1dtMy9rencreEpFdWtlMWYvWUpCYnZGMFNwNW0rdUVKQmxwUENra2Q3UmVFVnRpS1pwb2ZuelRxTVBHYjZsWXpOMXJaSGxaK3JIMS93c2M3WmV3b0hMWWNLMTFWRXd0MVpKK3ZBU203dHF0bTlOUVRGWThvaElvL0twYjFoMXdEOFNwWnMxSGFGRndlWmJhc1JVQXFnQ3ZaNTZYVlVtWnRURURIWURFK3IyWEF3WkJTY0hnRzJ1N3k3K29XV1daZ05uZ0x1R0xBVkJ0MlNOblNqd1RVMllQRVJFUHBsMDYvQktVWFAvOXlLcGNJUTFqa1diNHVxdGEzN1JZb3BuZTMrQ1FxY1JLdktUQ2hSdnByZ2gxbGREVDVlSDN2amMwdEtkL25TbXFZc2w3bk85Z2M4RUF1WUQvWU9WV0VpZlBlT3V4MXJnc0dMRFlIUXNMU2RlVmE5U1NCM1FKNzRvdGc5RWtRUHo3RUczNEFOdTFGcUpLVXNZMXFnVVM3cjc2TVF2UXAxQnRmUDlyYUViQzloVUFGdEJpcHNadFFsdVVaU0EweXRXVEsrTXk3ZENybDZJNmN5MGhlQVB2SlpaSWdERThRZWRvUEFyZStVZVdJamlNd25lQ0I4ZUtVK1gxMHdaNVZKQzN0K3ZLL3NhKzJwNTMxSUlpcVk1MlhSaTFQQWxLazFaRlZYQzJMV016N3RYdkpEMStmbHBTMlhlWG1kRzZQclNscDZKZjNqNWZlb3M3RkNGQzZKSkdDdm0vR1BJbit1dUdMS0ZvcXkvN2xWMVJQdjlCVmdLS2xpNkN4N2JwaEtTNTlwdkswSFZlTDRRb1VOS1ZJUnNubWVLM3haNnZDUW9yTUZaT3VVK1MzOHFXeHl2dW00VmlJaklwOWpwTDhHNCtBYkxZMktITXdwRnY5VCtQNjVXVmN5cTdmOTQ5RHJIeXZrcCt5S2RnQVFJWTYweWZkTGJiZEVQQVlPd0NnWlVnZTFzYWNmczc0dHlUQkY3MmN4dTFDRXQ4NEozRGlPVGRZMnF0Vlc2WnVmdGFma0hzNDgvQVJncTk2UTdiYjlJakZFL3ViRnlXM21Ja0FSL2ZBNko2RHI0Lzg5cno4YVpmZXprYXlZY09UTDA2aXFiN1dPZUNJUCtzWXB6LzEzNWpkTmhvUGpiTWRjemJwL2haNmI1WHB5MXNCQllWdlJYZDNjZnltUDZYQXFQZlpqOFNMUUhtRjA2enAxVkxpMWU5VzdDME14dm1UZzFwNGJBd0NGZFh2MmNVd1lSRzdubXlQYXkzTHF0VGlpR2lYQ0pZNEZQTW5ocWUxSnpFaFg4MzQ2YzkzNjRkY21RU040WWR0anZWMVFRU3RFcFNsNVhiOEhWSzBQZmpsWlNsR0xxeENIUTlmbllITHQ0QmJ2bCsvd0NUWDdMSVd2VWdISm5xdC8rZy91OGxFcVBZOVU2STZSNTEyMlB0UXRMUy9yZEc0YmVOc2pPMkUvVjNMcGdzdkc2RXFBWFJkOUhBR1pzcGthYS9aTTE2M1p5WXY4eU5QTVF2S0R3aW8yRitnL1BGWkFwS2hKOVpaUGRSSy8zc3U1M2RrZ1pMVUIzV1ZpdXh3MDNVdHB0blYyYXJnMk0zRlRhVXZrNmVFQ0pMN0dVcldVSE51UHJqOXBTZURGY3FKWFhESHQ3VW14cDZHb2xSWHViSDF2bW1zb2dwdklmU2RWcEdUd1NWbDBMOGtZUEYyVTdMUFcvcmcyZlpqcTIxSHJMNEl0L2FmRDk1OXovd1A0RFUxL2xjajUyYmVpYXpLdXUwT1RvUWx4T3BFK2U4NFEzNHZpQ3kxd2kzeTduenJzQnREUjlvYVhsSW5IZ3FGdmU1VmIvK2FhcDBxR0dYV0RqQ0pKaURUMmtnZjZ3MUM3WEZSd2tNL2cxOCtqbTREejJiU01aU3R3Skg1UGZ4bmlld0NzdkJFSlVLa0FyYzBzclp4VTdoZ2RqQ1AxNnhaRHJqVjZRd0kwVjQ5M1pXZC84SG1NbmZrM0RBLy96Nk9TLyt0dENyY1ZDbGJYQUFBL3VvdFNIbGR3RTdOQmdIK0NlSHFGYnNzRCtsdlkwQTJjZWhJc21iYzJEbS90Yjc1N2xZVjMvQytxckF4Y2FwOEl4QVM2WnZrb3ZMSUh4eE1IUS9PUW9oNHVTZUxUWVVDQS82VHNOZ2twR3VaQ1BnaWpNSlpnRUd1NUdjYXByQ1VKazFlTHd0OGNGSDlUZTNKYUFDV1FHUFFQWHd3Nk1PdTQzVDl6QWdrWWpYZGNXRUZtTTBPYTREeStzRm1LdWtiajZJZTR0Qy8wNWFLZ09tT0NiUlNZdjVEeUhXaUpTNG5WQ0ZOcTVCanhSRVhqc2Jvbm1FeXp3UTVwYzVyazNMOVMwamNKU2dLTW1GY3o5dUV2NWFySnU0YUttZWpIV0lTKzQxTmJ6VHppaDZFWE5IRnVxUzJVTEpHdzBRQkFTaFdRb2dsNWpOU3BWWTBZZWxqV2VmN1RDek8zbndBQTN6UWlZNFZZTVMyQ2Qra3diTUFhY0lOdDY0S2RZUkhIQ0RTSmhuWHo5enRkNGxuZTNWNGMzeEJGVVNrclcybzNIVFNMdzVUWmhueDNLVXpsN0xXWFFvbEZ5QXB5ODRhUmN4Qk1mV1JPUmdDMWM0TUxDeGxJZEFnOURhSkY2cnB6RmJVelJrUE5CWmdQMFVoSmYrTklxSmFEVVpvSUVHT1pVaEEyOS9jKy8vNWNiLzh2Ky81YzVuNksrcGYrWFA1LzllUDUvNlhKMnpqeGVLQUFBa3BHRGM3YnFXbHRESkgrVDBPeGxweWU4dnAzaGFnNUJXODR2eTZPQThMTXMvRzdOTjlLTTFOM2FVRFZQblpVcGovRjFCVGU4bkdHbEhremt5WEU0dnU2YWFGOEJPSjduU3FnWW1HUlBjeDFQUDVWQzI2YUJaNWR3ZTJtN01oZlJDREJ5a3JpQ3N0RExUUnVrbGVyN2ZmYytoUk1Pc1pyZEJXMHZGUEZ4aEtpdHJMU3lYM05HT1JNemtvSnR0YWwzSzJvRkpoRjdrbUt2OXlXZmFGQTJuVndZc3VwQVpuMnhSOUJRdkp1SVRPSGVzSDlHYmhOZExaVTdtNXZpTERzOElvSHlveHZqdytDWjQxb3pZWElKcTlVTEZMM0tsclYwT293WVU0TmdTTEU1REVOM2hpc3BtNWxpK2N0cUJxaWNraWltTDd1M0F0c0U4ZkRJcHVrUDhONjNvTVd2TkJoVElJOGdhajdEZ3J2M3VlUGViMERPOU1MdzhYcWlrblF1WmZxeGVONEcwQzBSL2RONWJ3bndsdUtrOXJiai81Mk9uaEJtVHZpTTJCMi8vdEtsc0xPSHg3U0R3N2kzN3FQaTJkM1dJcnhBOXVrNnlqRzR1NEZHNHpSWGhQSWxxQkQySEdWQUlpOFZEZ0FDRXZ1aUU4NmttaDJvM050UUprU2VDTHJ5c0pFWHFWaGFncjM3NklucGxLbzJMSmMzZ09LdkpNcFhhQlJUQUZQRy8yMWFHbWtXTE82bW5tNnVTVG14ZHpxMURvcGRpVzNqNmQ2UFlQMVN6SjlicGJlRlR1MmI3dnlVbDJJenV0cTZVQWN1SEVPd09ERXR2ZHRmRnRiV2NzbnFGd0ZxeVBhd1dKSnFHN0cvckcycVdydGNNOWFDMmVMMElUTlNXU0ZZNWlGRDhLS2gveFhtQkVHc0l1a3lBVmNkcjFWayswK3VDWkNuQjNlODYwVU81Z3AxTXNhaFdvZTdHK0o5M0FCNit5aVJFN3hoWjA0SVVaWWtKWWxDZnNyZ3FqWVpWZUFKVHJWdyt3QmZhTUlIQVorMVhFbVN3c0p4L1AvVXVXa09DNFZvR2hNaTl0a3VIR1hNdWV4dEh1ajFTU2w3RitCNkZZYVlmdENsR2dUVm1ZcnZlRVZQdEJtYW5xR2VXbm9nckR5YXJ5UmpDdnFnS3lEQmg3TFBtRkhGd0Rzb1lZQXhSNWpiUzVLTS9ES3VsR2xic0gveTNHZGVuZHNaL1ZpLzhqWGRPaVBHR1FSS3FHTnkwWWlzeTF5OGVuMFpacGQ3ZDVKZkQ2YjlYaWdZekdZUTNYSmdBM1ZBTnRpU2UyYmNQS0M3bE5KTXRnUHl6VjhSVGdPYVU5Z2Z0SktmUUxtR2ZYM1dCNkowanpYdkIyUStGemtWS3pVNENBR1dnQ0twUGV1WVlLWjhjL3Y1TGZqK25HZ295VE1qZ3pvYWVzM1lUWk1UMjJ3S3hYdlRQU2x1a1ZQQkwybTF4RytKVXZ1REJvZmg4THY4N3M3TkMyNUszRWNkdk5nN3hQcDFTdHBWSVMrNndFRDJjNkhwSFZ0dEpuUk1XRnJWZm0zdjhjbnMzUEhkSVpWdzY2bGNLUk5JaVo0YzZJSHBpZnkwbW9reUp2RG11Y0VNcDBnUmtrTFJIa29wcERJS3lzQUIzNEV1a1pacnRUU1RHc09CdmFrdkM5bGY0SHVGdzdySUZPSUR1UVMreksxeWFXZkpZbWZPejlvbXJhOWdmQWo5YjhpRUJZVWc2ZXBiNlJFc09WYU4xZEpNaXlHR2tGR2IrbDlrRGcrdzJYOCtlbURWK1h6U3NqWTFzckxpSXBuWmM0ZFdRNXhReTByNnd3WGpQMWpkY2RSSU1xZmx1a3Nzamt1NU5BalVIckhqa1dkRlNKMkxkZjg3TE0yTG52S1N6dHNSeGhNQ0xBMlJvYW13bUZZODd0QUFBPT0iIGFsdD0iQmlsbGFyZXMgRG9uIE1pZ3VlbCI+PC9kaXY+CjxkaXYgY2xhc3M9ImxpdmVCb3giPjxkaXYgaWQ9ImNsb2NrIiBjbGFzcz0iY2xvY2siPi0tOi0tIFBNPC9kaXY+PGRpdiBjbGFzcz0ibGl2ZSI+8J+foiBFTiBWSVZPPC9kaXY+PC9kaXY+CjwvaGVhZGVyPgo8c2VjdGlvbiBpZD0idGFibGVzIiBjbGFzcz0iZ3JpZCI+PC9zZWN0aW9uPgo8L21haW4+CjxzY3JpcHQ+CmNvbnN0IHJhdGVzPXsxOjEyMCwyOjEyMCwzOjEwMCw0OjEwMCw1OjcwfTtsZXQgbGFzdFN0YXRlPW51bGwsd3M9bnVsbCxyZWNvbm5lY3RUaW1lcj1udWxsLHBvbGxpbmdUaW1lcj1udWxsOwpmdW5jdGlvbiBzYWZlKHYpe3JldHVybiB2PT1udWxsfHx2PT09Jyc/J+KAlCc6U3RyaW5nKHYpfQpmdW5jdGlvbiBtb25leSh2KXtyZXR1cm4gJ0MkICcrTnVtYmVyKHZ8fDApLnRvRml4ZWQoMil9CmZ1bmN0aW9uIGNsb2NrVmFsdWUodil7aWYoIXYpcmV0dXJuICfigJQnO3ZhciBkPW5ldyBEYXRlKHYpO2lmKGlzTmFOKGQuZ2V0VGltZSgpKSlyZXR1cm4gU3RyaW5nKHYpO3JldHVybiBkLnRvTG9jYWxlVGltZVN0cmluZygnZXMtTkknLHtob3VyOicyLWRpZ2l0JyxtaW51dGU6JzItZGlnaXQnLGhvdXIxMjp0cnVlfSl9CmZ1bmN0aW9uIGVsYXBzZWRWYWx1ZSh0KXtpZih0JiZ0LmVsYXBzZWQmJnQuZWxhcHNlZCE9PScwMDowMDowMCcpcmV0dXJuIHQuZWxhcHNlZDtpZighdHx8IXQuc3RhcnQpcmV0dXJuICcwMDowMDowMCc7dmFyIGE9bmV3IERhdGUodC5zdGFydCksYj10LmVuZD9uZXcgRGF0ZSh0LmVuZCk6bmV3IERhdGUoKTtpZihpc05hTihhLmdldFRpbWUoKSl8fGlzTmFOKGIuZ2V0VGltZSgpKSlyZXR1cm4gJzAwOjAwOjAwJzt2YXIgc2VjPU1hdGgubWF4KDAsTWF0aC5mbG9vcigoYi1hKS8xMDAwKSksaD1NYXRoLmZsb29yKHNlYy8zNjAwKSxtPU1hdGguZmxvb3Ioc2VjJTM2MDAvNjApLHM9c2VjJTYwO3JldHVybiBTdHJpbmcoaCkucGFkU3RhcnQoMiwnMCcpKyc6JytTdHJpbmcobSkucGFkU3RhcnQoMiwnMCcpKyc6JytTdHJpbmcocykucGFkU3RhcnQoMiwnMCcpfQpmdW5jdGlvbiBzdGF0dXNOYW1lKHYpe3JldHVybiB2PT09J3BsYXlpbmcnPydFbiBqdWVnbyc6dj09PSdwZW5kaW5nJz8nUGVuZGllbnRlIGRlIGNvYnJvJzp2PT09J2F2YWlsYWJsZSc/J0Rpc3BvbmlibGUnOnNhZmUodil9CmZ1bmN0aW9uIHJlbmRlcihkKXtsYXN0U3RhdGU9ZHx8bGFzdFN0YXRlfHx7fTt2YXIgdGFibGVzPUFycmF5LmlzQXJyYXkobGFzdFN0YXRlLnRhYmxlcyk/bGFzdFN0YXRlLnRhYmxlczpbXTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndGFibGVzJykuaW5uZXJIVE1MPVsxLDIsMyw0LDVdLm1hcChmdW5jdGlvbihpKXt2YXIgdD10YWJsZXMuZmluZChmdW5jdGlvbih4KXtyZXR1cm4gTnVtYmVyKHgubnVtYmVyKT09PWl9KXx8e251bWJlcjppLHN0YXR1czonYXZhaWxhYmxlJyxyYXRlOnJhdGVzW2ldLGFtb3VudDowfTt2YXIgcz1zdGF0dXNOYW1lKHQuc3RhdHVzKSxjPXM9PT0nRW4ganVlZ28nPydyZWQnOnM9PT0nUGVuZGllbnRlIGRlIGNvYnJvJz8neWVsbG93JzonZ3JlZW4nO3JldHVybiAnPGFydGljbGUgY2xhc3M9ImNhcmQgJytjKyciPjxkaXYgY2xhc3M9Im51bSI+TWVzYSAnK2krJzwvZGl2PjxkaXYgY2xhc3M9InN0YXR1cyI+JytzYWZlKHMpKyc8L2Rpdj48ZGl2IGNsYXNzPSJsaW5lIj48Yj5Ib3JhIGRlIGluaWNpbzo8L2I+ICcrKHQuc3RhcnQmJlN0cmluZyh0LnN0YXJ0KS5pbmRleE9mKCdUJyk+MD9jbG9ja1ZhbHVlKHQuc3RhcnQpOnNhZmUodC5zdGFydCkpKyc8L2Rpdj48ZGl2IGNsYXNzPSJsaW5lIj48Yj5UaWVtcG8ganVnYWRvOjwvYj4gJytlbGFwc2VkVmFsdWUodCkrJzwvZGl2PjxkaXYgY2xhc3M9ImxpbmUiPjxiPkhvcmEgZmluYWxpemFkYTo8L2I+ICcrKHQuZW5kJiZTdHJpbmcodC5lbmQpLmluZGV4T2YoJ1QnKT4wP2Nsb2NrVmFsdWUodC5lbmQpOnNhZmUodC5lbmQpKSsnPC9kaXY+PGRpdiBjbGFzcz0icGF5Ij48ZGl2IGNsYXNzPSJwYXlMYWJlbCI+TU9OVE8gQSBQQUdBUjwvZGl2PjxkaXYgY2xhc3M9Im1vbmV5Ij4nK21vbmV5KHQuYW1vdW50KSsnPC9kaXY+PC9kaXY+PC9hcnRpY2xlPid9KS5qb2luKCcnKTt2YXIgY2xvY2s9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2Nsb2NrJyk7aWYoY2xvY2spY2xvY2sudGV4dENvbnRlbnQ9bmV3IERhdGUoKS50b0xvY2FsZVRpbWVTdHJpbmcoJ2VzLU5JJyx7aG91cjonMi1kaWdpdCcsbWludXRlOicyLWRpZ2l0Jyxob3VyMTI6dHJ1ZX0pfQphc3luYyBmdW5jdGlvbiBwb2xsU3RhdGUoKXt0cnl7dmFyIHI9YXdhaXQgZmV0Y2goJy9hcGkvc3RhdGU/dHM9JytEYXRlLm5vdygpLHtjYWNoZTonbm8tc3RvcmUnfSk7aWYoIXIub2spdGhyb3cgRXJyb3Ioci5zdGF0dXMpO3JlbmRlcihhd2FpdCByLmpzb24oKSl9Y2F0Y2goZSl7fX0KZnVuY3Rpb24gc3RhcnRQb2xsaW5nKCl7aWYocG9sbGluZ1RpbWVyKXJldHVybjtwb2xsU3RhdGUoKTtwb2xsaW5nVGltZXI9c2V0SW50ZXJ2YWwocG9sbFN0YXRlLDEwMDApfQpmdW5jdGlvbiBjb25uZWN0KCl7Y2xlYXJUaW1lb3V0KHJlY29ubmVjdFRpbWVyKTt0cnl7aWYod3Mpd3MuY2xvc2UoKX1jYXRjaChlKXt9dmFyIHA9bG9jYXRpb24ucHJvdG9jb2w9PT0naHR0cHM6Jz8nd3NzOic6J3dzOic7dHJ5e3dzPW5ldyBXZWJTb2NrZXQocCsnLy8nK2xvY2F0aW9uLmhvc3QrJy9hcGkvc3RyZWFtJyk7d3Mub25vcGVuPWZ1bmN0aW9uKCl7aWYocG9sbGluZ1RpbWVyKXtjbGVhckludGVydmFsKHBvbGxpbmdUaW1lcik7cG9sbGluZ1RpbWVyPW51bGx9fTt3cy5vbm1lc3NhZ2U9ZnVuY3Rpb24oZSl7dHJ5e3JlbmRlcihKU09OLnBhcnNlKGUuZGF0YSkpfWNhdGNoKF8pe319O3dzLm9uY2xvc2U9ZnVuY3Rpb24oKXtzdGFydFBvbGxpbmcoKTtyZWNvbm5lY3RUaW1lcj1zZXRUaW1lb3V0KGNvbm5lY3QsMzAwMCl9O3dzLm9uZXJyb3I9ZnVuY3Rpb24oKXt0cnl7d3MuY2xvc2UoKX1jYXRjaChfKXt9O3N0YXJ0UG9sbGluZygpfX1jYXRjaChlKXtzdGFydFBvbGxpbmcoKTtyZWNvbm5lY3RUaW1lcj1zZXRUaW1lb3V0KGNvbm5lY3QsMzAwMCl9fQpyZW5kZXIoe3RhYmxlczpbXX0pO2Nvbm5lY3QoKTtzZXRJbnRlcnZhbChmdW5jdGlvbigpe2lmKGxhc3RTdGF0ZSlyZW5kZXIobGFzdFN0YXRlKX0sMTAwMCk7Cjwvc2NyaXB0Pgo8L2JvZHk+CjwvaHRtbD4K',
    ),
  );

  Map<String, dynamic> stateMap() => <String, dynamic>{
    'app': 'Billares Don Miguel',
    'version': appVersion,
    'time': clock(DateTime.now()),
    'tables':
        tableList
            .map(
              (BillTable t) => <String, dynamic>{
                'number': t.number,
                'rate': t.rate,
                'status': t.statusText,
                'start': t.start == null ? null : t.start!.toIso8601String(),
                'end': t.end == null ? null : t.end!.toIso8601String(),
                'elapsed': duration(t.elapsedSeconds),
                'amount':
                    t.status == TableStatus.available
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

  Future<void> printReceipt(BillTable table) async {
    if (table.start == null || table.end == null) return;
    try {
      final bool enabled = await PrintBluetoothThermal.bluetoothEnabled;
      if (!enabled) {
        if (mounted)
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Activa Bluetooth en la tablet para imprimir.'),
            ),
          );
        return;
      }
      final bool permission =
          await PrintBluetoothThermal.isPermissionBluetoothGranted;
      if (!permission) {
        if (mounted)
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                'Concede el permiso de Bluetooth y vuelve a intentar.',
              ),
            ),
          );
        return;
      }
      final List<BluetoothInfo> printers =
          await PrintBluetoothThermal.pairedBluetooths;
      if (printers.isEmpty) {
        if (mounted)
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                'No hay impresoras Bluetooth emparejadas con la tablet.',
              ),
            ),
          );
        return;
      }
      if (!mounted) return;
      final BluetoothInfo? selected = await showDialog<BluetoothInfo>(
        context: context,
        builder:
            (BuildContext dialogContext) => AlertDialog(
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
                      title: Text(
                        printer.name.isEmpty
                            ? 'Impresora Bluetooth'
                            : printer.name,
                      ),
                      subtitle: Text(printer.macAdress),
                      onTap: () => Navigator.pop(dialogContext, printer),
                    );
                  },
                ),
              ),
              actions: <Widget>[
                TextButton(
                  onPressed: () => Navigator.pop(dialogContext),
                  child: const Text('Cancelar'),
                ),
              ],
            ),
      );
      if (selected == null) return;
      final bool connected = await PrintBluetoothThermal.connect(
        macPrinterAddress: selected.macAdress,
      );
      if (!connected) {
        if (mounted)
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('No se pudo conectar con la impresora.'),
            ),
          );
        return;
      }
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
      if (!printed && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('La impresora no aceptó el recibo.')),
        );
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Recibo enviado a la impresora.')),
        );
      }
    } catch (_) {
      if (mounted)
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No se pudo imprimir el recibo.')),
        );
    }
  }

  Future<void> collect(BillTable table) async {
    // Cobrar debe funcionar aunque no haya impresora Bluetooth disponible.
    // La impresión queda como acción independiente en 'Imprimir recibo'.
    if (table.status != TableStatus.pending ||
        table.start == null ||
        table.end == null)
      return;
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
      final Map<String, dynamic> manifest =
          jsonDecode(await response.transform(utf8.decoder).join())
              as Map<String, dynamic>;
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
        builder:
            (BuildContext context) => AlertDialog(
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
      final bool installPermission =
          await ApkInstall().onCheckInstallApkPermission();
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
      builder:
          (BuildContext context) => AlertDialog(
            title: const Text('Cambiar contraseña'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                TextField(
                  controller: newPassword,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: 'Nueva contraseña',
                  ),
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
                onPressed:
                    () => Navigator.pop(
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
    final double amount =
        table.status == TableStatus.playing ? table.liveAmount : table.amount;
    final String buttonText =
        table.status == TableStatus.available
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
            if (table.status == TableStatus.pending) ...<Widget>[
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: () => printReceipt(table),
                  icon: const Icon(Icons.print_outlined),
                  label: const Text('Imprimir recibo'),
                ),
              ),
              const SizedBox(height: 7),
            ],
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
      final int columns =
          width >= 1100
              ? 3
              : width >= 650
              ? 2
              : 1;
      final bool compact = width < 650;
      final int available =
          tableList
              .where((BillTable t) => t.status == TableStatus.available)
              .length;
      final int playing =
          tableList
              .where((BillTable t) => t.status == TableStatus.playing)
              .length;
      final int pending =
          tableList
              .where((BillTable t) => t.status == TableStatus.pending)
              .length;
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
              childAspectRatio:
                  width >= 1100
                      ? 2.35
                      : width >= 650
                      ? 2.7
                      : 3.1,
              children: <Widget>[
                metricCard(
                  'Disponibles',
                  '$available',
                  Icons.check_circle_outline,
                ),
                metricCard('En juego', '$playing', Icons.sports_bar),
                metricCard('Pendientes', '$pending', Icons.payments_outlined),
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
                                color:
                                    workdayActive
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
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
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
                mainAxisExtent:
                    width >= 1100
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
    final List<String> keys =
        groups.keys.toList()..sort((String a, String b) => b.compareTo(a));
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
          final List<HistoryEntry> items =
              groups[key]!..sort(
                (HistoryEntry a, HistoryEntry b) => b.end.compareTo(a.end),
              );
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
      builder:
          (BuildContext context) => AlertDialog(
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
    final String opened =
        workdayOpenedAt == null
            ? '—'
            : workdayOpenedAt!
                .toString()
                .replaceFirst('T', ' ')
                .split('.')
                .first;
    final String closed =
        workdayClosedAt == null
            ? '—'
            : workdayClosedAt!
                .toString()
                .replaceFirst('T', ' ')
                .split('.')
                .first;
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final int columns =
            constraints.maxWidth >= 900
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
                                color:
                                    workdayActive
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
