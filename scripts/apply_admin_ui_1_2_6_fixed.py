from pathlib import Path
import re

TARGET = Path('lib/main.dart')


def skip_string(source, index):
    quote = source[index]
    token = quote * 3 if source.startswith(quote * 3, index) else quote
    index += len(token)
    while index < len(source):
        if source[index] == '\\':
            index += 2
            continue
        if source.startswith(token, index):
            return index + len(token)
        index += 1
    raise SystemExit('ADMIN UI FAILED: cadena Dart sin cerrar')


def find_build(source):
    match = re.search(r'(?m)^\s*@override\s*\n\s*Widget\s+build\s*\(\s*BuildContext\s+context\s*\)\s*(=>|\{)', source)
    if not match:
        raise SystemExit('ADMIN UI FAILED: build del administrador ausente')
    start = match.start()
    if match.group(1) == '=>':
        semi = source.find(';', match.end())
        if semi < 0:
            raise SystemExit('ADMIN UI FAILED: build flecha sin cierre')
        return start, semi + 1
    brace = source.find('{', match.start(), match.end())
    depth = 0
    i = brace
    while i < len(source):
        if source[i] in "'\"":
            i = skip_string(source, i); continue
        if source.startswith('//', i):
            e = source.find('\n', i + 2); i = len(source) if e < 0 else e + 1; continue
        if source[i] == '{': depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0: return start, i + 1
        i += 1
    raise SystemExit('ADMIN UI FAILED: llaves del build sin cerrar')


ui = r'''  @override
  Widget build(BuildContext context) {
    final Size size = MediaQuery.sizeOf(context);
    final bool wide = size.width >= 900;
    final int columns = wide ? 3 : size.width >= 600 ? 2 : 1;
    final int available = tableList.where((BillTable t) => t.status == TableStatus.available).length;
    final int playing = tableList.where((BillTable t) => t.status == TableStatus.playing).length;
    final int pending = tableList.where((BillTable t) => t.status == TableStatus.pending).length;

    Widget statusBadge(BillTable table) {
      final Color color = table.status == TableStatus.available ? Colors.green : table.status == TableStatus.playing ? Colors.red : Colors.amber;
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(color: color.withValues(alpha: .16), borderRadius: BorderRadius.circular(20), border: Border.all(color: color)),
        child: Text(table.statusText, style: TextStyle(color: color, fontWeight: FontWeight.w800, fontSize: 12)),
      );
    }

    Widget tableCard(BillTable table) {
      final Color color = table.status == TableStatus.available ? Colors.green : table.status == TableStatus.playing ? Colors.red : Colors.amber;
      final double currentAmount = table.status == TableStatus.playing ? table.liveAmount : table.amount;
      return Card(
        elevation: 2,
        clipBehavior: Clip.antiAlias,
        child: Container(
          decoration: BoxDecoration(border: Border(left: BorderSide(color: color, width: 6))),
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
            Row(children: <Widget>[Expanded(child: Text('Mesa ${table.number}', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900))), statusBadge(table)]),
            const SizedBox(height: 10),
            Text('Tarifa fija: ${money(table.rate)} / hora', style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 12),
            if (table.start != null) Text('Inicio: ${clock(table.start!)}'),
            if (table.end != null) Text('Finalización: ${clock(table.end!)}'),
            Text('Tiempo: ${duration(table.elapsedSeconds)}'),
            const SizedBox(height: 6),
            Text(money(currentAmount), style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w900)),
            const Spacer(),
            SizedBox(width: double.infinity, height: 46, child: table.status == TableStatus.available
                ? FilledButton.icon(onPressed: () => startGame(table), icon: const Icon(Icons.play_arrow), label: const Text('Iniciar juego'))
                : table.status == TableStatus.playing
                    ? FilledButton.icon(onPressed: () => finishGame(table), icon: const Icon(Icons.stop_circle_outlined), label: const Text('Finalizar juego'))
                    : FilledButton.icon(onPressed: () => collect(table), icon: const Icon(Icons.point_of_sale), label: const Text('Cobrar'))),
          ]),
        ),
      );
    }

    Widget dashboard() => ListView(padding: EdgeInsets.zero, children: <Widget>[
      Wrap(spacing: 10, runSpacing: 10, children: <Widget>[
        _summaryCard('Disponibles', '$available', Colors.green, Icons.check_circle_outline),
        _summaryCard('En juego', '$playing', Colors.red, Icons.sports_esports_outlined),
        _summaryCard('Pendientes', '$pending', Colors.amber, Icons.payments_outlined),
        _summaryCard('Generado hoy', money(workdayGenerated), Colors.blue, Icons.attach_money),
      ]),
      const SizedBox(height: 16),
      Container(
        width: double.infinity,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(color: const Color(0xff101826), borderRadius: BorderRadius.circular(18), border: Border.all(color: const Color(0xff1d4ed8))),
        child: Wrap(alignment: WrapAlignment.spaceBetween, crossAxisAlignment: WrapCrossAlignment.center, spacing: 12, runSpacing: 12, children: <Widget>[
          Row(mainAxisSize: MainAxisSize.min, children: <Widget>[const Icon(Icons.today, color: Colors.blue), const SizedBox(width: 10), Text(workdayActive ? 'Jornada abierta desde ${clock(workdayOpenedAt ?? DateTime.now())}' : 'Jornada cerrada', style: const TextStyle(fontWeight: FontWeight.w800))]),
          FilledButton.icon(onPressed: workdayActive ? closeWorkday : openWorkday, icon: Icon(workdayActive ? Icons.lock_clock : Icons.play_circle_outline), label: Text(workdayActive ? 'Cerrar jornada' : 'Abrir jornada')),
        ]),
      ),
      const SizedBox(height: 18),
      Text('Mesas', style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w900)),
      const SizedBox(height: 10),
      GridView.builder(shrinkWrap: true, physics: const NeverScrollableScrollPhysics(), itemCount: tableList.length, gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: columns, crossAxisSpacing: 14, mainAxisSpacing: 14, mainAxisExtent: 285), itemBuilder: (_, int index) => tableCard(tableList[index])),
    ]);

    Widget workdayView() => ListView(padding: EdgeInsets.zero, children: <Widget>[
      Text('Jornada', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w900)),
      const SizedBox(height: 14),
      Card(child: Padding(padding: const EdgeInsets.all(18), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
        Text(workdayActive ? 'Jornada abierta' : 'Jornada cerrada', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900)),
        const SizedBox(height: 10),
        if (workdayOpenedAt != null) Text('Fecha de apertura: ${date(workdayOpenedAt!)}'),
        if (workdayOpenedAt != null) Text('Hora de apertura: ${clock(workdayOpenedAt!)}'),
        Text('Juegos: $workdayGames'),
        Text('Total generado: ${money(workdayGenerated)}'),
        if (workdayClosedAt != null) Text('Hora de cierre: ${clock(workdayClosedAt!)}'),
        Text('Efectivo físico: ${money(workdayCashClose)}'),
        const SizedBox(height: 14),
        FilledButton.icon(onPressed: workdayActive ? closeWorkday : openWorkday, icon: Icon(workdayActive ? Icons.lock : Icons.lock_open), label: Text(workdayActive ? 'Cerrar jornada' : 'Abrir jornada')),
      ]))),
    ]);

    Widget historyView() {
      if (history.isEmpty) return const Center(child: Text('No hay jornadas registradas todavía.'));
      final Map<String, List<HistoryEntry>> grouped = <String, List<HistoryEntry>>{};
      for (final HistoryEntry entry in history) {
        final String key = date(entry.workDate);
        grouped.putIfAbsent(key, () => <HistoryEntry>[]).add(entry);
      }
      return ListView(padding: EdgeInsets.zero, children: grouped.entries.map((MapEntry<String, List<HistoryEntry>> group) {
        final double total = group.value.fold<double>(0, (double sum, HistoryEntry e) => sum + e.amount);
        return Card(margin: const EdgeInsets.only(bottom: 12), child: ExpansionTile(title: Text(group.key, style: const TextStyle(fontWeight: FontWeight.w900)), subtitle: Text('${group.value.length} juegos • ${money(total)} generado'), children: group.value.map((HistoryEntry e) => ListTile(leading: CircleAvatar(child: Text('${e.table}')), title: Text('Mesa ${e.table} • ${money(e.amount)}'), subtitle: Text('Inicio ${clock(e.start)} • Finalización ${clock(e.end)} • ${duration(e.seconds)}'))).toList()));
      }).toList());
    }

    return Scaffold(
      appBar: AppBar(
        title: Row(children: <Widget>[const Icon(Icons.sports_bar), const SizedBox(width: 8), const Flexible(child: Text('Billares Don Miguel', overflow: TextOverflow.ellipsis))]),
        actions: <Widget>[
          if (lanPort != null) const Padding(padding: EdgeInsets.symmetric(horizontal: 8), child: Chip(avatar: Icon(Icons.wifi, size: 16), label: Text('LAN conectado'))),
          IconButton(tooltip: 'Pantalla TV', onPressed: showTvConnection, icon: const Icon(Icons.tv)),
          IconButton(tooltip: 'Buscar actualización', onPressed: checkingUpdate ? null : () => checkForUpdate(showNoUpdate: true), icon: const Icon(Icons.system_update_alt)),
          IconButton(tooltip: 'Configuración', onPressed: showSettings, icon: const Icon(Icons.settings_outlined)),
          IconButton(tooltip: 'Cerrar sesión', onPressed: logout, icon: const Icon(Icons.logout)),
        ],
      ),
      body: SafeArea(child: Padding(padding: EdgeInsets.symmetric(horizontal: wide ? 24 : 14, vertical: 14), child: tab == 0 ? dashboard() : tab == 1 ? workdayView() : historyView())),
      bottomNavigationBar: NavigationBar(selectedIndex: tab, onDestinationSelected: (int value) => setState(() => tab = value), destinations: const <NavigationDestination>[
        NavigationDestination(icon: Icon(Icons.dashboard_outlined), selectedIcon: Icon(Icons.dashboard), label: 'Mesas'),
        NavigationDestination(icon: Icon(Icons.calendar_today_outlined), selectedIcon: Icon(Icons.calendar_today), label: 'Jornada'),
        NavigationDestination(icon: Icon(Icons.history_outlined), selectedIcon: Icon(Icons.history), label: 'Historial'),
      ]),
    );
  }

  Widget _summaryCard(String label, String value, Color color, IconData icon) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
    decoration: BoxDecoration(color: color.withValues(alpha: .12), borderRadius: BorderRadius.circular(16), border: Border.all(color: color.withValues(alpha: .45))),
    child: Row(mainAxisSize: MainAxisSize.min, children: <Widget>[Icon(icon, color: color), const SizedBox(width: 8), Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[Text(label, style: const TextStyle(fontSize: 12)), Text(value, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900))])],
  );
'''

source = TARGET.read_text()
start, end = find_build(source)
source = source[:start] + ui + source[end:]
TARGET.write_text(source)
print('OK: interfaz administrativa nueva aplicada sobre build flecha o build bloque')
