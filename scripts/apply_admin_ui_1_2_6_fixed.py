from pathlib import Path

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


def brace_end(source, brace):
    depth = 0
    i = brace
    while i < len(source):
        if source[i] in "'\"":
            i = skip_string(source, i)
            continue
        if source.startswith('//', i):
            e = source.find('\n', i + 2)
            i = len(source) if e < 0 else e + 1
            continue
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise SystemExit('ADMIN UI FAILED: llaves sin cerrar')


def class_span(source, class_name):
    marker = 'class ' + class_name
    start = source.find(marker)
    if start < 0:
        raise SystemExit(f'ADMIN UI FAILED: clase {class_name} ausente')
    brace = source.find('{', start)
    if brace < 0:
        raise SystemExit(f'ADMIN UI FAILED: clase {class_name} sin cuerpo')
    return start, brace_end(source, brace)


def method_span(source, class_start, class_end, name):
    segment = source[class_start:class_end]
    marker = f'Widget {name}(BuildContext context)'
    rel = segment.find(marker)
    if rel < 0:
        raise SystemExit(f'ADMIN UI FAILED: {name} del administrador ausente')
    start = class_start + rel
    brace = source.find('{', start)
    if brace < 0 or brace >= class_end:
        raise SystemExit(f'ADMIN UI FAILED: {name} debe ser bloque')
    return start, brace_end(source, brace)


ui = r'''  Widget _summaryCard(String label, String value, Color color, IconData icon) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .12),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: .45)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, color: color),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(label, style: const TextStyle(fontSize: 12)),
              Text(value, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900)),
            ],
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final int columns = constraints.maxWidth >= 1200 ? 3 : constraints.maxWidth >= 650 ? 2 : 1;
        final int available = tableList.where((BillTable t) => t.status == TableStatus.available).length;
        final int playing = tableList.where((BillTable t) => t.status == TableStatus.playing).length;
        final int pending = tableList.where((BillTable t) => t.status == TableStatus.pending).length;
        final Widget home = Padding(
          padding: EdgeInsets.all(constraints.maxWidth >= 800 ? 22 : 14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text('Panel de administración', style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w900)),
                        const SizedBox(height: 4),
                        Text(workdayActive ? 'Jornada abierta • ${clock(workdayOpenedAt ?? DateTime.now())}' : 'Jornada cerrada'),
                      ],
                    ),
                  ),
                  Flexible(
                    child: Chip(
                      avatar: Icon(Icons.wifi, size: 18, color: lanIp != null ? Colors.green : Colors.red),
                      label: Text(lanIp != null ? 'LAN conectado' : 'LAN no disponible', overflow: TextOverflow.ellipsis),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: <Widget>[
                  _summaryCard('Disponibles', '$available', Colors.green, Icons.check_circle_outline),
                  _summaryCard('En juego', '$playing', Colors.red, Icons.sports_esports_outlined),
                  _summaryCard('Pendientes', '$pending', Colors.amber, Icons.payments_outlined),
                  _summaryCard('Generado hoy', money(todayTotal), Colors.blue, Icons.attach_money),
                ],
              ),
              const SizedBox(height: 14),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: <Widget>[
                      Chip(
                        avatar: Icon(Icons.circle, size: 12, color: workdayActive ? Colors.green : Colors.grey),
                        label: Text(workdayActive ? 'Jornada abierta' : 'Jornada cerrada'),
                      ),
                      if (workdayActive) Text('Apertura: ${clock(workdayOpenedAt!)}'),
                      if (workdayActive) Text('Juegos: $workdayGames'),
                      if (workdayActive) Text('Generado: ${money(workdayGenerated)}'),
                      if (!workdayActive && workdayClosedAt != null) Text('Cierre: ${clock(workdayClosedAt!)}'),
                      if (!workdayActive && workdayClosedAt != null) Text('Efectivo físico: ${money(workdayCashClose)}'),
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
              Row(
                children: <Widget>[
                  Expanded(child: Text('Mesas', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w900))),
                  const Text('🟢 Libre   🔴 En juego   🟡 Pendiente'),
                ],
              ),
              const SizedBox(height: 8),
              Expanded(
                child: GridView.builder(
                  padding: EdgeInsets.zero,
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: columns,
                    mainAxisExtent: columns == 1 ? 390 : 350,
                    crossAxisSpacing: 14,
                    mainAxisSpacing: 14,
                  ),
                  itemCount: tableList.length,
                  itemBuilder: (_, int index) => tableCard(tableList[index]),
                ),
              ),
            ],
          ),
        );

        return Scaffold(
          appBar: AppBar(
            title: const Text('Billares Don Miguel', style: TextStyle(fontWeight: FontWeight.bold)),
            actions: <Widget>[
              IconButton(tooltip: 'Pantalla exclusiva para TV', onPressed: showTvConnection, icon: const Icon(Icons.tv)),
              if (checkingUpdate) const Padding(padding: EdgeInsets.symmetric(horizontal: 12), child: Center(child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)))),
              IconButton(tooltip: 'Buscar actualización', onPressed: checkingUpdate ? null : () => checkForUpdate(showNoUpdate: true), icon: const Icon(Icons.system_update_alt)),
              IconButton(tooltip: 'Configuración', onPressed: showSettings, icon: const Icon(Icons.settings_outlined)),
              IconButton(tooltip: 'Cerrar sesión', onPressed: logout, icon: const Icon(Icons.logout)),
            ],
          ),
          body: tab == 0 ? home : tab == 1 ? workdayView() : historyPage(),
          bottomNavigationBar: NavigationBar(
            selectedIndex: tab,
            onDestinationSelected: (int index) => setState(() => tab = index),
            destinations: const <NavigationDestination>[
              NavigationDestination(icon: Icon(Icons.table_restaurant), selectedIcon: Icon(Icons.dashboard), label: 'Mesas'),
              NavigationDestination(icon: Icon(Icons.calendar_today), selectedIcon: Icon(Icons.calendar_today), label: 'Jornada'),
              NavigationDestination(icon: Icon(Icons.history), selectedIcon: Icon(Icons.history), label: 'Historial'),
            ],
          ),
        );
      },
    );
  }
'''

source = TARGET.read_text()
class_start, class_end = class_span(source, '_DashboardPageState')
start, end = method_span(source, class_start, class_end, 'build')
source = source[:start] + ui + source[end:]
TARGET.write_text(source)
print('OK: interfaz administrativa aplicada dentro de _DashboardPageState')
