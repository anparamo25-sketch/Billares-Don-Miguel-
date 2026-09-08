import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String appVersion = '1.0.1+101';
const String defaultPassword = '1234';
const Map<int, double> tableRates = {1: 120, 2: 120, 3: 100, 4: 100, 5: 70};

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
}

class HistoryEntry {
  HistoryEntry({required this.table, required this.start, required this.end, required this.seconds, required this.amount});
  final int table;
  final DateTime start;
  final DateTime end;
  final int seconds;
  final double amount;

  Map<String, dynamic> toMap() => {
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
        theme: ThemeData(useMaterial3: true, colorScheme: ColorScheme.fromSeed(seedColor: Colors.green), scaffoldBackgroundColor: const Color(0xfff4f6f5)),
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
    loadPassword();
  }

  Future<void> loadPassword() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      password = prefs.getString('admin_password') ?? defaultPassword;
      loading = false;
    });
  }

  void login() {
    if (controller.text == password) {
      Navigator.of(context).pushReplacement(MaterialPageRoute<void>(builder: (_) => const DashboardPage()));
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Contraseña incorrecta')));
      controller.clear();
    }
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
                elevation: 6,
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
                              keyboardType: TextInputType.visiblePassword,
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

class _DashboardPageState extends State<DashboardPage> {
  final List<BillTable> tableList = tableRates.entries.map((e) => BillTable(e.key, e.value)).toList();
  final TextEditingController newPassword = TextEditingController();
  final TextEditingController confirmPassword = TextEditingController();
  List<HistoryEntry> history = [];
  HttpServer? server;
  Timer? ticker;
  String? lanIp;
  int tab = 0;

  @override
  void initState() {
    super.initState();
    loadHistory();
    startLanServer();
    ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    ticker?.cancel();
    server?.close(force: true);
    newPassword.dispose();
    confirmPassword.dispose();
    super.dispose();
  }

  Future<void> loadHistory() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    final String? raw = prefs.getString('history');
    final DateTime cutoff = DateTime.now().subtract(const Duration(days: 7));
    List<HistoryEntry> loaded = [];
    if (raw != null && raw.isNotEmpty) {
      try {
        final List<dynamic> data = jsonDecode(raw) as List<dynamic>;
        loaded = data.map((e) => HistoryEntry.fromMap(Map<String, dynamic>.from(e as Map))).where((e) => e.end.isAfter(cutoff)).toList();
      } catch (_) {
        loaded = [];
      }
    }
    history = loaded;
    await saveHistory();
    if (mounted) setState(() {});
  }

  Future<void> saveHistory() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setString('history', jsonEncode(history.map((e) => e.toMap()).toList()));
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
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo iniciar el servidor LAN en el puerto 8080')));
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

  Map<String, dynamic> stateMap() => {
        'app': 'Billares Don Miguel',
        'version': appVersion,
        'time': clock(DateTime.now()),
        'tables': tableList.map((t) => {
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
<style>body{margin:0;background:#07120c;color:#fff;font-family:Arial,sans-serif}header{padding:20px;text-align:center;background:#0d2b1b;position:sticky;top:0}h1{margin:0;font-size:30px}.clock{font-size:20px;margin-top:6px;color:#d9f99d}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px;padding:22px}.card{border-radius:18px;padding:22px;background:#15251c;border:2px solid #31523e;box-shadow:0 8px 30px #0008}.green{border-color:#36d76b}.red{border-color:#ff5252}.yellow{border-color:#f5c542}.name{font-size:28px;font-weight:800}.status{margin:10px 0;font-size:20px;font-weight:700}.line{margin:8px 0;color:#d8e7dc}.money{font-size:30px;font-weight:800;margin-top:14px}</style></head>
<body><header><h1>BILLARES DON MIGUEL</h1><div id="clock" class="clock">Conectando...</div></header><main id="grid" class="grid"></main>
<script>function money(n){return 'C$ '+Number(n).toFixed(2)}function render(d){document.getElementById('clock').textContent=d.time;document.getElementById('grid').innerHTML=d.tables.map(function(t){var c=t.status==='Disponible'?'green':t.status==='En juego'?'red':'yellow';return '<section class="card '+c+'"><div class="name">Mesa '+t.number+'</div><div class="status">'+t.status+'</div><div class="line">Inicio: '+(t.start||'—')+'</div><div class="line">Finalización: '+(t.end||'—')+'</div><div class="line">Tiempo jugado: '+t.elapsed+'</div><div class="money">'+money(t.amount)+'</div></section>'}).join('')}async function tick(){try{var r=await fetch('/api/state?x='+Date.now());render(await r.json())}catch(e){document.getElementById('clock').textContent='Sin conexión con CENTRAL'}}tick();setInterval(tick,1000)</script></body></html>''';

  void startGame(BillTable table) {
    if (table.status != TableStatus.available) return;
    setState(() {
      table.status = TableStatus.playing;
      table.start = DateTime.now();
      table.end = null;
      table.amount = 0;
    });
  }

  void finishGame(BillTable table) {
    if (table.status != TableStatus.playing) return;
    setState(() {
      table.end = DateTime.now();
      table.amount = table.liveAmount;
      table.status = TableStatus.pending;
    });
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
  }

  Future<void> changePassword() async {
    newPassword.clear();
    confirmPassword.clear();
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
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
    return history.where((e) => e.end.year == now.year && e.end.month == now.month && e.end.day == now.day).fold<double>(0, (total, e) => total + e.amount);
  }

  Color statusColor(TableStatus status) {
    switch (status) {
      case TableStatus.available:
        return Colors.green;
      case TableStatus.playing:
        return Colors.red;
      case TableStatus.pending:
        return Colors.amber.shade800;
    }
  }

  Widget tableCard(BillTable table) {
    final double amount = table.status == TableStatus.playing ? table.liveAmount : table.amount;
    final String buttonText = table.status == TableStatus.available ? 'Iniciar' : table.status == TableStatus.playing ? 'Finalizar' : 'Cobrar';
    final VoidCallback action = table.status == TableStatus.available ? () => startGame(table) : table.status == TableStatus.playing ? () => finishGame(table) : () => collect(table);
    return Card(
      elevation: 3,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
          Row(children: <Widget>[
            Expanded(child: Text('Mesa ${table.number}', style: const TextStyle(fontSize: 23, fontWeight: FontWeight.bold))),
            Chip(label: Text(table.statusText), avatar: CircleAvatar(backgroundColor: statusColor(table.status), radius: 6)),
          ]),
          const Divider(),
          Text('Tarifa fija: ${money(table.rate)} / hora'),
          const SizedBox(height: 8),
          Text('Inicio: ${table.start == null ? '—' : clock(table.start!)}'),
          Text('Finalización: ${table.end == null ? '—' : clock(table.end!)}'),
          Text('Tiempo jugado: ${duration(table.elapsedSeconds)}'),
          const SizedBox(height: 8),
          Text(money(amount), style: const TextStyle(fontSize: 26, fontWeight: FontWeight.bold)),
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
          const SizedBox(height: 12),
          Expanded(child: GridView.builder(
            gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(maxCrossAxisExtent: 460, mainAxisExtent: 330, crossAxisSpacing: 14, mainAxisSpacing: 14),
            itemCount: tableList.length,
            itemBuilder: (_, index) => tableCard(tableList[index]),
          )),
        ]),
      );

  Widget historyPage() {
    final List<HistoryEntry> items = List<HistoryEntry>.from(history)..sort((a, b) => b.end.compareTo(a.end));
    return Column(children: <Widget>[
      Card(margin: const EdgeInsets.fromLTRB(16, 16, 16, 8), child: ListTile(leading: const Icon(Icons.today), title: const Text('Total de hoy'), trailing: Text(money(todayTotal), style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)))),
      Expanded(child: items.isEmpty
          ? const Center(child: Text('No hay movimientos en los últimos 7 días.'))
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: items.length,
              itemBuilder: (_, index) {
                final HistoryEntry e = items[index];
                return Card(child: ListTile(leading: CircleAvatar(child: Text('${e.table}')), title: Text('Mesa ${e.table} • ${money(e.amount)}'), subtitle: Text('${date(e.end)} • ${clock(e.start)} - ${clock(e.end)} • ${duration(e.seconds)}')));
              },
            )),
    ]);
  }

  void showSettings() {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
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
            IconButton(tooltip: 'Configuración', onPressed: showSettings, icon: const Icon(Icons.settings_outlined)),
            IconButton(tooltip: 'Cerrar sesión', onPressed: () => Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute<void>(builder: (_) => const LoginPage()), (_) => false), icon: const Icon(Icons.logout)),
          ],
        ),
        body: tab == 0 ? dashboard() : historyPage(),
        bottomNavigationBar: NavigationBar(
          selectedIndex: tab,
          onDestinationSelected: (index) => setState(() => tab = index),
          destinations: const <NavigationDestination>[
            NavigationDestination(icon: Icon(Icons.table_restaurant), label: 'Mesas'),
            NavigationDestination(icon: Icon(Icons.history), label: 'Historial'),
          ],
        ),
      );
}
