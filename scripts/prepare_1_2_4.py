from pathlib import Path
import re

main = Path('lib/main.dart')
s = main.read_text()

# Base 1.2.3 stability changes.
s = s.replace("const String appVersion = '1.2.1+121';", "const String appVersion = '1.2.4+124';")
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
'''
s2 = re.sub(r"  Future<void> startLanServer\(\) async \{.*?\n  Map<String, dynamic> stateMap\(\)", start_server + "\n  Map<String, dynamic> stateMap()", s, count=1, flags=re.S)
if s2 == s:
    raise SystemExit('No se pudo reemplazar el servidor LAN')
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
        title: const Text('Pantalla exclusiva para TV'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Text('La TV debe mostrar solamente las mesas. CENTRAL puede seguir utilizándose normalmente en el celular.'),
              const SizedBox(height: 12),
              const Text('Receptor TV:'),
              const SizedBox(height: 6),
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
              const Text('En la TV abre esta dirección con su navegador. El receptor /tv es independiente del panel administrativo.'),
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: () async {
                  try {
                    final bool result = await const MethodChannel('com.billaresdonmiguel/tv_cast').invokeMethod<bool>('openCastSettings') ?? false;
                    if (!result && context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('La transmisión no está disponible en este dispositivo')));
                  } on PlatformException {
                    if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('La transmisión no está disponible en este dispositivo')));
                  }
                },
                icon: const Icon(Icons.cast),
                label: const Text('Buscar TV / Chromecast'),
              ),
              const SizedBox(height: 6),
              const Text('Nota: la duplicación Miracast del sistema puede reflejar toda la pantalla. Para mostrar exclusivamente las mesas, utiliza el receptor TV indicado arriba.', style: TextStyle(fontSize: 12)),
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
    raise SystemExit('No se pudo reemplazar la conexión TV')
s = s2

# More resilient updater.
s = s.replace("client = HttpClient()..connectionTimeout = const Duration(seconds: 8);", "client = HttpClient()..connectionTimeout = const Duration(seconds: 12);\n      client.userAgent = 'Billares-Don-Miguel/1.2.4';")
s = s.replace("client = HttpClient()..connectionTimeout = const Duration(seconds: 20);", "client = HttpClient()..connectionTimeout = const Duration(seconds: 30);\n      client.userAgent = 'Billares-Don-Miguel/1.2.4';")

# Workday state.
anchor = "  bool backgroundStarted = false;\n"
replacement = """  bool backgroundStarted = false;
  bool workdayActive = false;
  DateTime? workdayOpenedAt;
  DateTime? workdayClosedAt;
  double workdayGenerated = 0;
  double workdayCashClose = 0;
  int workdayGames = 0;
"""
if anchor not in s:
    raise SystemExit('No se encontró el estado del dashboard')
s = s.replace(anchor, replacement, 1)

# Extend HistoryEntry with the workday date while remaining compatible with old history.
s = s.replace("  HistoryEntry({required this.table, required this.start, required this.end, required this.seconds, required this.amount});\n  final int table;", "  HistoryEntry({required this.table, required this.start, required this.end, required this.seconds, required this.amount, DateTime? workDate}) : workDate = DateTime((workDate ?? end).year, (workDate ?? end).month, (workDate ?? end).day);\n  final int table;\n  final DateTime workDate;")
s = s.replace("        'amount': amount,\n      };\n\n  factory HistoryEntry.fromMap", "        'amount': amount,\n        'workDate': workDate.toIso8601String(),\n      };\n\n  factory HistoryEntry.fromMap", 1)
s = s.replace("        amount: (map['amount'] as num).toDouble(),\n      );", "        amount: (map['amount'] as num).toDouble(),\n        workDate: DateTime.tryParse(map['workDate'] as String? ?? map['end'] as String),\n      );", 1)

# Load/save the active workday.
load_anchor = "    final String? rawHistory = prefs.getString('history');"
load_insert = """    workdayActive = prefs.getBool('workday_active') ?? false;
    final String? opened = prefs.getString('workday_opened_at');
    final String? closed = prefs.getString('workday_closed_at');
    workdayOpenedAt = opened == null ? null : DateTime.tryParse(opened);
    workdayClosedAt = closed == null ? null : DateTime.tryParse(closed);
    workdayGenerated = prefs.getDouble('workday_generated') ?? 0;
    workdayCashClose = prefs.getDouble('workday_cash_close') ?? 0;
    workdayGames = prefs.getInt('workday_games') ?? 0;
""" + load_anchor
s = s.replace(load_anchor, load_insert, 1)

save_anchor = "  Future<void> saveTables() async {"
workday_methods = r'''  Future<void> saveWorkday() async {
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
          TextField(controller: cashController, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Efectivo físico al cierre', prefixText: 'C$ ')),
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

'''
s = s.replace(save_anchor, workday_methods + save_anchor, 1)

# Associate collected games with the active workday and accumulate the day's generated amount.
s = s.replace("    final HistoryEntry entry = HistoryEntry(table: table.number, start: table.start!, end: table.end!, seconds: table.end!.difference(table.start!).inSeconds, amount: table.amount);", "    final HistoryEntry entry = HistoryEntry(table: table.number, start: table.start!, end: table.end!, seconds: table.end!.difference(table.start!).inSeconds, amount: table.amount, workDate: workdayOpenedAt ?? table.end!);")
s = s.replace("      history.add(entry);\n      table.status", "      history.add(entry);\n      if (workdayActive) {\n        workdayGenerated += table.amount;\n        workdayGames += 1;\n      }\n      table.status", 1)
s = s.replace("    await saveHistory();\n    await saveTables();\n  }\n\n  Future<void> showTvConnection", "    await saveHistory();\n    await saveTables();\n    await saveWorkday();\n  }\n\n  Future<void> showTvConnection", 1)

# Replace table card with a responsive, clearer card.
new_table_card = r'''  Widget tableCard(BillTable table) {
    final double amount = table.status == TableStatus.playing ? table.liveAmount : table.amount;
    final String buttonText = table.status == TableStatus.available ? 'Iniciar' : table.status == TableStatus.playing ? 'Finalizar' : 'Cobrar';
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
          Text('Tarifa fija: ${money(table.rate)} / hora', style: TextStyle(color: statusTextColor(table.status), fontWeight: FontWeight.w600)),
          const SizedBox(height: 7),
          Text('Inicio: ${table.start == null ? '—' : clock(table.start!)}', style: TextStyle(color: statusTextColor(table.status))),
          Text('Finalización: ${table.end == null ? '—' : clock(table.end!)}', style: TextStyle(color: statusTextColor(table.status))),
          Text('Tiempo jugado: ${duration(table.elapsedSeconds)}', style: TextStyle(color: statusTextColor(table.status))),
          const Spacer(),
          Text(money(amount), style: TextStyle(fontSize: 27, fontWeight: FontWeight.bold, color: statusTextColor(table.status))),
          const SizedBox(height: 10),
          SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: action, icon: Icon(table.status == TableStatus.playing ? Icons.stop : table.status == TableStatus.pending ? Icons.payments : Icons.play_arrow), label: Text(buttonText))),
          if (table.status == TableStatus.available && !workdayActive) const Padding(padding: EdgeInsets.only(top: 5), child: Center(child: Text('Abra el día para iniciar partidas', style: TextStyle(fontSize: 11)))),
        ]),
      ),
    );
  }
'''
s2 = re.sub(r"  Widget tableCard\(BillTable table\) \{.*?\n  Widget dashboard\(\)", new_table_card + "\n  Widget dashboard()", s, count=1, flags=re.S)
if s2 == s:
    raise SystemExit('No se pudo reemplazar la tarjeta de mesa')
s = s2

# Responsive dashboard.
new_dashboard = r'''  Widget dashboard() => LayoutBuilder(
        builder: (BuildContext context, BoxConstraints constraints) {
          final bool wide = constraints.maxWidth >= 800;
          final int columns = constraints.maxWidth >= 1200 ? 3 : constraints.maxWidth >= 700 ? 2 : 1;
          final double cardHeight = columns == 1 ? 390 : 350;
          return Padding(
            padding: EdgeInsets.all(wide ? 22 : 14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
                  Text('Inicio', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Text(workdayActive ? 'Jornada activa • ${date(workdayOpenedAt ?? DateTime.now())}' : workdayClosedAt != null ? 'Día cerrado • ${date(workdayClosedAt!)}' : 'Sin jornada abierta'),
                ])),
                if (lanIp != null) Flexible(child: Chip(avatar: const Icon(Icons.wifi, size: 18), label: Text('LAN $lanIp:8080', overflow: TextOverflow.ellipsis))),
              ]),
              const SizedBox(height: 12),
              Card(child: Padding(padding: const EdgeInsets.all(14), child: Wrap(spacing: 10, runSpacing: 10, crossAxisAlignment: WrapCrossAlignment.center, children: <Widget>[
                Chip(avatar: Icon(Icons.circle, size: 12, color: workdayActive ? Colors.green : Colors.grey), label: Text(workdayActive ? 'Día abierto' : 'Día cerrado')),
                if (workdayActive) Text('Apertura: ${clock(workdayOpenedAt!)}'),
                if (workdayActive) Text('Juegos: $workdayGames'),
                if (workdayActive) Text('Generado: ${money(workdayGenerated)}'),
                if (!workdayActive && workdayClosedAt != null) Text('Cierre: ${clock(workdayClosedAt!)}'),
                if (!workdayActive && workdayClosedAt != null) Text('Efectivo físico: ${money(workdayCashClose)}'),
                FilledButton.icon(onPressed: workdayActive ? closeWorkday : openWorkday, icon: Icon(workdayActive ? Icons.lock : Icons.lock_open), label: Text(workdayActive ? 'Cerrar día' : 'Abrir día')),
              ]))),
              const SizedBox(height: 10),
              Wrap(spacing: 10, runSpacing: 10, children: <Widget>[
                FilledButton.icon(onPressed: showTvConnection, icon: const Icon(Icons.tv), label: const Text('Mostrar en TV')),
                if (lanIp != null) OutlinedButton.icon(onPressed: () async { await Clipboard.setData(ClipboardData(text: 'http://$lanIp:8080/tv')); if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Dirección de TV copiada'))); }, icon: const Icon(Icons.copy), label: const Text('Copiar receptor TV')),
              ]),
              const SizedBox(height: 14),
              Row(children: <Widget>[
                Expanded(child: Text('Mesas', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold))),
                const Text('🟢 Libre   🔴 En juego   🟡 Pendiente'),
              ]),
              const SizedBox(height: 8),
              Expanded(child: GridView.builder(
                padding: EdgeInsets.zero,
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: columns, mainAxisExtent: cardHeight, crossAxisSpacing: 14, mainAxisSpacing: 14),
                itemCount: tableList.length,
                itemBuilder: (_, int index) => tableCard(tableList[index]),
              )),
            ]),
          );
        },
      );
'''
s2 = re.sub(r"  Widget dashboard\(\) => .*?\n  Widget historyPage\(\)", new_dashboard + "\n  Widget historyPage()", s, count=1, flags=re.S)
if s2 == s:
    raise SystemExit('No se pudo reemplazar el dashboard')
s = s2

# Group history by work date and show opening/closing summaries.
new_history = r'''  Widget historyPage() {
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
'''
s2 = re.sub(r"  Widget historyPage\(\) \{.*?\n  void showSettings\(\)", new_history + "\n  void showSettings()", s, count=1, flags=re.S)
if s2 == s:
    raise SystemExit('No se pudo reemplazar el historial')
s = s2

# Settings remains lightweight but includes the new TV endpoint and locked rates.
new_settings = r'''  void showSettings() {
    showDialog<void>(
      context: context,
      builder: (BuildContext context) => AlertDialog(
        title: const Text('Configuración'),
        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
          const Text('Tarifas fijas', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          const Text('Mesas 1 y 2: C$120 por hora'),
          const Text('Mesas 3 y 4: C$100 por hora'),
          const Text('Mesa 5: C$70 por hora'),
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
'''
s2 = re.sub(r"  void showSettings\(\) \{.*?\n  @override\n  Widget build", new_settings + "\n  @override\n  Widget build", s, count=1, flags=re.S)
if s2 == s:
    raise SystemExit('No se pudo reemplazar configuración')
s = s2

# Make the main shell responsive and keep the same two primary destinations.
new_build = r'''  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Billares Don Miguel', style: TextStyle(fontWeight: FontWeight.bold)),
          actions: <Widget>[
            if (checkingUpdate) const Padding(padding: EdgeInsets.symmetric(horizontal: 12), child: Center(child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)))),
            IconButton(tooltip: 'Configuración', onPressed: showSettings, icon: const Icon(Icons.settings_outlined)),
            IconButton(tooltip: 'Cerrar sesión', onPressed: logout, icon: const Icon(Icons.logout)),
          ],
        ),
        body: SafeArea(child: tab == 0 ? dashboard() : historyPage()),
        bottomNavigationBar: NavigationBar(
          selectedIndex: tab,
          onDestinationSelected: (int index) => setState(() => tab = index),
          destinations: const <NavigationDestination>[
            NavigationDestination(icon: Icon(Icons.dashboard_outlined), selectedIcon: Icon(Icons.dashboard), label: 'Inicio'),
            NavigationDestination(icon: Icon(Icons.history), label: 'Historial'),
          ],
        ),
      );
'''
s2 = re.sub(r"  @override\n  Widget build\(BuildContext context\) => Scaffold\(.*?\n\}", new_build + "\n}", s, count=1, flags=re.S)
if s2 == s:
    raise SystemExit('No se pudo reemplazar la interfaz principal')
s = s2

# Background notification level from the successful 1.2.3 build.
s = s.replace('AndroidNotificationImportance.low', 'AndroidNotificationImportance.normal')

main.write_text(s)

# Patch generated Android MainActivity with a cast-settings bridge; this is only a fallback/system cast entry.
activity_dir = Path('android/app/src/main')
files = list(activity_dir.rglob('MainActivity.kt'))
if not files:
    raise SystemExit('No se encontró MainActivity.kt')
activity = files[0]
package_line = next((line for line in activity.read_text().splitlines() if line.startswith('package ')), 'package com.billaresdonmiguel.billares_don_miguel')
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
