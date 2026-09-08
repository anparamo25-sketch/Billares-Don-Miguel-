import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String appVersion = '1.0.0+100';
const String defaultPassword = '1234';

class TableConfig {
  final int number;
  final double rate;
  const TableConfig(this.number, this.rate);
}

const tables = <TableConfig>[
  TableConfig(1, 120),
  TableConfig(2, 120),
  TableConfig(3, 100),
  TableConfig(4, 100),
  TableConfig(5, 70),
];

enum TableStatus { available, playing, pending }

class BillTable {
  final int number;
  final double rate;
  TableStatus status;
  DateTime? start;
  DateTime? end;
  double amount;

  BillTable(this.number, this.rate)
      : status = TableStatus.available,
        amount = 0;

  int get elapsedSeconds {
    if (start == null) return 0;
    final finish = end ?? DateTime.now();
    return finish.difference(start!).inSeconds.clamp(0, 1 << 30);
  }

  double get currentAmount => (elapsedSeconds / 3600) * rate;

  String get statusText => switch (status) {
        TableStatus.available => 'Disponible',
        TableStatus.playing => 'En juego',
        TableStatus.pending => 'Pendiente de cobro',
      };

  String toJson() => jsonEncode({
        'number': number,
        'status': status.name,
        'start': start?.toIso8601String(),
        'end': end?.toIso8601String(),
        'amount': amount,
      });
}

class HistoryEntry {
  final int table;
  final DateTime start;
  final DateTime end;
  final int seconds;
  final double amount;

  HistoryEntry(this.table, this.start, this.end, this.seconds, this.amount);

  Map<String, dynamic> toMap() => {
        'table': table,
        'start': start.toIso8601String(),
        'end': end.toIso8601String(),
        'seconds': seconds,
        'amount': amount,
      };

  factory HistoryEntry.fromMap(Map<String, dynamic> m) => HistoryEntry(
        m['table'] as int,
        DateTime.parse(m['start'] as String),
        DateTime.parse(m['end'] as String),
        m['seconds'] as int,
        (m['amount'] as num).toDouble(),
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
          colorScheme: ColorScheme.fromSeed(seedColor: Colors.green),
          scaffoldBackgroundColor: const Color(0xfff4f6f5),
          fontFamily: 'sans',
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
  final controller = TextEditingController();
  bool obscure = true;
  String password = defaultPassword;
  bool loading = true;

  @override
  void initState() {
    super.initState();
    _loadPassword();
  }

  Future<void> _loadPassword() async {
    final p = await SharedPreferences.getInstance();
    setState(() {
      password = p.getString('admin_password') ?? defaultPassword;
      loading = false;
    });
  }

  void _login() {
    if (controller.text == password) {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const DashboardPage()),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Contraseña incorrecta')),
      );
      controller.clear();
    }
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
                      ? const Center(child: CircularProgressIndicator())
                      : Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.sports_bar,
                                size: 64, color: Colors.green),
                            const SizedBox(height: 12),
                            const Text('Billares Don Miguel',
                                style: TextStyle(
                                    fontSize: 27, fontWeight: FontWeight.bold)),
                            const SizedBox(height: 6),
                            const Text('CENTRAL • Administrador'),
                            const SizedBox(height: 28),
                            TextField(
                              controller: controller,
                              obscureText: obscure,
                              keyboardType: TextInputType.visiblePassword,
                              onSubmitted: (_) => _login(),
                              decoration: InputDecoration(
                                labelText: 'Contraseña',
                                prefixIcon: const Icon(Icons.lock_outline),
                                suffixIcon: IconButton(
                                  tooltip: obscure ? 'Mostrar' : 'Ocultar',
                                  onPressed: () => setState(() => obscure = !obscure),
                                  icon: Icon(obscure
                                      ? Icons.visibility_outlined
                                      : Icons.visibility_off_outlined),
                                ),
                                border: const OutlineInputBorder(),
                              ),
                            ),
                            const SizedBox(height: 20),
                            SizedBox(
                              width: double.infinity,
                              height: 50,
                              child: FilledButton.icon(
                                onPressed: _login,
                                icon: const Icon(Icons.login),
                                label: const Text('Ingresar'),
                              ),
                            ),
                            const SizedBox(height: 14),
                            Text('Versión $appVersion',
                                style: Theme.of(context).textTheme.bodySmall),
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
  final List<BillTable> tablesState =
      tables.map((t) => BillTable(t.number, t.rate)).toList();
  List<HistoryEntry> history = [];
  HttpServer? server;
  Timer? ticker;
  String? lanIp;
  int selectedTab = 0;

  @override
  void initState() {
    super.initState();
    _loadHistory();
    _startLanServer();
    ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    ticker?.cancel();
    server?.close(force: true);
    super.dispose();
  }

  Future<void> _loadHistory() async {
    final p = await SharedPreferences.getInstance();
    final raw = p.getString('history');
    if (raw != null) {
      final list = (jsonDecode(raw) as List)
          .map((e) => HistoryEntry.fromMap(Map<String, dynamic>.from(e)))
          .toList();
      final cutoff = DateTime.now().subtract(const Duration(days: 7));
      history = list.where((e) => e.end.isAfter(cutoff)).toList();
      await _saveHistory();
      if (mounted) setState(() {});
    }
  }

  Future<void> _saveHistory() async {
    final p = await SharedPreferences.getInstance();
    await p.setString('history', jsonEncode(history.map((e) => e.toMap()).toList()));
  }

  Future<void> _startLanServer() async {
    try {
      server = await HttpServer.bind(InternetAddress.anyIPv4, 8080,
          shared: true, v6Only: false);
      for (final interface in await NetworkInterface.list(
          type: InternetAddressType.IPv4, includeLoopback: false)) {
        for (final address in interface.addresses) {
          if (!address.isLoopback) {
            lanIp = address.address;
            break;
          }
        }
        if (lanIp != null) break;
      }
      server!.listen(_handleRequest);
      if (mounted) setState(() {});
    } catch (_) {}
  }

  Future<void> _handleRequest(HttpRequest req) async {
    req.response.headers.set('Access-Control-Allow-Origin', '*');
    req.response.headers.set('Cache-Control', 'no-store');
    if (req.uri.path == '/api/state') {
      req.response.headers.contentType = ContentType.json;
      req.response.write(jsonEncode(_stateMap()));
    } else {
      req.response.headers.contentType = ContentType.html;
      req.response.write(_tvHtml());
    }
    await req.response.close();
  }

  Map<String, dynamic> _stateMap() => {
        'app': 'Billares Don Miguel',
        'time': _clock(DateTime.now()),
        'tables': tablesState.map((t) => {
              'number': t.number,
              'rate': t.rate,
              'status': t.statusText,
              'start': t.start == null ? null : _clock(t.start!),
              'end': t.end == null ? null : _clock(t.end!),
              'elapsed': _duration(t.elapsedSeconds),
              'amount': t.status == TableStatus.available
                  ? 0
                  : (t.status == TableStatus.playing
                      ? t.currentAmount
                      : t.amount),
            }).toList(),
      };

  String _tvHtml() => '''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Billares Don Miguel</title><style>body{margin:0;background:#07120c;color:#fff;font-family:Arial,sans-serif}header{padding:22px;text-align:center;background:#0d2b1b;position:sticky;top:0}h1{margin:0;font-size:30px}.clock{font-size:20px;margin-top:6px;color:#d9f99d}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px;padding:22px}.card{border-radius:18px;padding:22px;background:#15251c;border:2px solid #31523e;box-shadow:0 8px 30px #0008}.green{border-color:#36d76b}.red{border-color:#ff5252}.yellow{border-color:#f5c542}.name{font-size:28px;font-weight:800}.status{margin:10px 0;font-size:20px;font-weight:700}.line{margin:8px 0;color:#d8e7dc}.money{font-size:30px;font-weight:800;margin-top:14px}</style></head><body><header><h1>BILLARES DON MIGUEL</h1><div id="clock" class="clock">Conectando...</div></header><main id="grid" class="grid"></main><script>function money(n){return 'C$ '+Number(n).toFixed(2)}function render(d){document.getElementById('clock').textContent=d.time;document.getElementById('grid').innerHTML=d.tables.map(t=>{let c=t.status==='Disponible'?'green':t.status==='En juego'?'red':'yellow';return `<section class="card ${c}"><div class="name">Mesa ${t.number}</div><div class="status">${t.status}</div><div class="line">Inicio: ${t.start||'—'}</div><div class="line">Finalización: ${t.end||'—'}</div><div class="line">Tiempo jugado: ${t.elapsed}</div><div class="money">${money(t.amount)}</div></section>`}).join('')}async function tick(){try{const r=await fetch('/api/state?x='+Date.now());render(await r.json())}catch(e){document.getElementById('clock').textContent='Sin conexión con CENTRAL'}}tick();setInterval(tick,1000)</script></body></html>''';

  void _startGame(BillTable t) {
    if (t.status != TableStatus.available) return;
    setState(() {
      t.status = TableStatus.playing;
      t.start = DateTime.now();
      t.end = null;
      t.amount = 0;
    });
  }

  Future<void> _finishGame(BillTable t) async {
    if (t.status != TableStatus.playing) return;
    setState(() {
      t.end = DateTime.now();
      t.amount = t.currentAmount;
      t.status = TableStatus.pending;
    });
  }

  Future<void> _collect(BillTable t) async {
    if (t.status != TableStatus.pending || t.start == null || t.end == null) return;
    final entry = HistoryEntry(t.number, t.start!, t.end!, t.end!.difference(t.start!).inSeconds, t.amount);
    setState(() {
      history.add(entry);
      t.status = TableStatus.available;
      t.start = null;
      t.end = null;
      t.amount = 0;
    });
    await _saveHistory();
  }

  Future<void> _changePassword() async {
    final c1 = TextEditingController();
    final c2 = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Cambiar contraseña'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: c1, obscureText: true, decoration: const InputDecoration(labelText: 'Nueva contraseña')),
          TextField(controller: c2, obscureText: true, decoration: const InputDecoration(labelText: 'Confirmar contraseña')),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(context, c1.text.isNotEmpty && c1.text == c2.text), child: const Text('Guardar')),
        ],
      ),
    );
    if (ok == true) {
      final p = await SharedPreferences.getInstance();
      await p.setString('admin_password', c1.text);
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Contraseña actualizada')));
    } else if (ok == false && c1.text != c2.text && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Las contraseñas no coinciden')));
    }
  }

  String _clock(DateTime d) {
    final h = d.hour % 12 == 0 ? 12 : d.hour % 12;
    final m = d.minute.toString().padLeft(2, '0');
    final s = d.second.toString().padLeft(2, '0');
    return '$h:$m:$s ${d.hour >= 12 ? 'PM' : 'AM'}';
  }

  String _duration(int seconds) {
    final h = seconds ~/ 3600;
    final m = (seconds % 3600) ~/ 60;
    final s = seconds % 60;
    return '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  String _todayKey(DateTime d) => '${d.year}-${d.month}-${d.day}';

  double get todayTotal => history.where((e) => _todayKey(e.end) == _todayKey(DateTime.now())).fold(0, (a, e) => a + e.amount);

  @override
  Widget build(BuildContext context) {
    final body = selectedTab == 0 ? _dashboard() : _historyPage();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Billares Don Miguel', style: TextStyle(fontWeight: FontWeight.bold)),
        actions: [
          IconButton(tooltip: 'Configuración', onPressed: () => _showSettings(context), icon: const Icon(Icons.settings_outlined)),
        ],
      ),
      body: body,
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedTab,
        onDestinationSelected: (i) => setState(() => selectedTab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.grid_view), label: 'Mesas'),
          NavigationDestination(icon: Icon(Icons.receipt_long), label: 'Historial'),
        ],
      ),
    );
  }

  Widget _dashboard() => LayoutBuilder(builder: (context, constraints) {
        final cols = constraints.maxWidth >= 1000 ? 3 : constraints.maxWidth >= 650 ? 2 : 1;
        return RefreshIndicator(
          onRefresh: () async => setState(() {}),
          child: ListView(padding: const EdgeInsets.all(18), children: [
            Row(children: [
              Expanded(child: _metric('Hora actual', _clock(DateTime.now()), Icons.schedule)),
              const SizedBox(width: 12),
              Expanded(child: _metric('Cobrado hoy', 'C\$ ${todayTotal.toStringAsFixed(2)}', Icons.payments_outlined)),
            ]),
            const SizedBox(height: 18),
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: cols, mainAxisExtent: 255, crossAxisSpacing: 16, mainAxisSpacing: 16),
              itemCount: tablesState.length,
              itemBuilder: (_, i) => _tableCard(tablesState[i]),
            ),
            const SizedBox(height: 18),
            Card(child: Padding(padding: const EdgeInsets.all(18), child: Row(children: [
              const Icon(Icons.tv, size: 30), const SizedBox(width: 12),
              Expanded(child: Text(lanIp == null ? 'TV: servidor LAN iniciando…' : 'TV: http://$lanIp:8080', style: const TextStyle(fontWeight: FontWeight.w600))),
              if (lanIp != null) IconButton(onPressed: () => _showTvInfo(context), icon: const Icon(Icons.info_outline)),
            ]))),
          ]),
        );
      });

  Widget _metric(String title, String value, IconData icon) => Card(child: Padding(padding: const EdgeInsets.all(18), child: Row(children: [Icon(icon, size: 30), const SizedBox(width: 14), Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: const TextStyle(color: Colors.black54)), Text(value, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold))])])));

  Color _statusColor(TableStatus s) => switch (s) { TableStatus.available => Colors.green, TableStatus.playing => Colors.red, TableStatus.pending => Colors.amber.shade800 };

  Widget _tableCard(BillTable t) {
    final amount = t.status == TableStatus.playing ? t.currentAmount : t.amount;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(children: [
        Container(height: 8, color: _statusColor(t.status)),
        Expanded(child: Padding(padding: const EdgeInsets.all(18), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [Expanded(child: Text('Mesa ${t.number}', style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold))), Text(t.statusText, style: TextStyle(color: _statusColor(t.status), fontWeight: FontWeight.bold))]),
          const SizedBox(height: 8),
          Text('Tarifa fija: C\$ ${t.rate.toStringAsFixed(0)} / hora', style: const TextStyle(color: Colors.black54)),
          const SizedBox(height: 10),
          Text('Inicio: ${t.start == null ? '—' : _clock(t.start!)}'),
          Text('Finalización: ${t.end == null ? '—' : _clock(t.end!)}'),
          Text('Tiempo: ${_duration(t.elapsedSeconds)}'),
          const Spacer(),
          Text('C\$ ${amount.toStringAsFixed(2)}', style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          if (t.status == TableStatus.available)
            SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: () => _startGame(t), icon: const Icon(Icons.play_arrow), label: const Text('Iniciar')))
          else if (t.status == TableStatus.playing)
            SizedBox(width: double.infinity, child: FilledButton.icon(style: FilledButton.styleFrom(backgroundColor: Colors.red), onPressed: () => _finishGame(t), icon: const Icon(Icons.stop), label: const Text('Finalizar juego')))
          else
            SizedBox(width: double.infinity, child: FilledButton.icon(style: FilledButton.styleFrom(backgroundColor: Colors.amber.shade800), onPressed: () => _collect(t), icon: const Icon(Icons.payments), label: const Text('Registrar cobro')),
        ]))),
      ]),
    );
  }

  Widget _historyPage() {
    final grouped = <String, List<HistoryEntry>>{};
    for (final e in history.reversed) {
      grouped.putIfAbsent(_dateLabel(e.end), () => []).add(e);
    }
    return ListView(padding: const EdgeInsets.all(18), children: [
      Card(child: ListTile(leading: const Icon(Icons.today), title: const Text('Total de hoy'), trailing: Text('C\$ ${todayTotal.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18)))),
      const SizedBox(height: 12),
      if (history.isEmpty) const Card(child: Padding(padding: EdgeInsets.all(28), child: Center(child: Text('No hay cobros registrados en los últimos 7 días.')))),
      ...grouped.entries.map((entry) => Card(child: ExpansionTile(title: Text(entry.key), subtitle: Text('${entry.value.length} cobro(s)'), children: entry.value.map((e) => ListTile(title: Text('Mesa ${e.table}'), subtitle: Text('${_clock(e.start)} → ${_clock(e.end)} • ${_duration(e.seconds)}'), trailing: Text('C\$ ${e.amount.toStringAsFixed(2)}')).toList()))),
    ]);
  }

  String _dateLabel(DateTime d) => '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year}';

  void _showTvInfo(BuildContext context) => showDialog(context: context, builder: (_) => AlertDialog(title: const Text('Pantalla TV'), content: Text('Conecta la TV a la misma red Wi‑Fi/LAN y abre:\n\nhttp://$lanIp:8080\n\nLa pantalla se actualiza automáticamente cada segundo.'), actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cerrar'))]));

  void _showSettings(BuildContext context) => showModalBottomSheet(context: context, showDragHandle: true, builder: (_) => SafeArea(child: Wrap(children: [
    const ListTile(title: Text('Configuración de administrador', style: TextStyle(fontWeight: FontWeight.bold))),
    ListTile(leading: const Icon(Icons.password), title: const Text('Cambiar contraseña'), onTap: () { Navigator.pop(context); _changePassword(); }),
    ListTile(leading: const Icon(Icons.tv), title: const Text('Configurar TV'), subtitle: Text(lanIp == null ? 'Servidor no disponible' : 'http://$lanIp:8080'), onTap: () { Navigator.pop(context); _showTvInfo(context); }),
    const ListTile(leading: Icon(Icons.lock_outline), title: Text('Tarifas protegidas'), subtitle: Text('Mesa 1-2: C\$120/h • Mesa 3-4: C\$100/h • Mesa 5: C\$70/h')),
    const ListTile(leading: Icon(Icons.system_update), title: Text('Actualizaciones'), subtitle: Text('La versión se controla mediante versionCode en cada compilación.')),
  ]));
}
