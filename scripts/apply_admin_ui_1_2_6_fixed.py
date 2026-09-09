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


def class_span(source, name):
    marker = 'class ' + name
    start = source.find(marker)
    if start < 0:
        raise SystemExit(f'ADMIN UI FAILED: clase {name} ausente')
    brace = source.find('{', start)
    if brace < 0:
        raise SystemExit(f'ADMIN UI FAILED: clase {name} sin cuerpo')
    return start, brace_end(source, brace)


def top_level_function_spans(source, marker):
    positions = []
    offset = 0
    while True:
        start = source.find(marker, offset)
        if start < 0:
            break
        brace = source.find('{', start)
        if brace < 0:
            break
        end = brace_end(source, brace)
        positions.append((start, end))
        offset = end
    return positions


def repair_app_root(source):
    class_start, class_end = class_span(source, 'BillaresApp')
    clean_class = '''class BillaresApp extends StatelessWidget {
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
}'''
    return source[:class_start] + clean_class + source[class_end:]


def remove_duplicate_local_ip(source):
    spans = top_level_function_spans(source, 'Future<String?> _billaresLocalIp() async')
    if len(spans) <= 1:
        return source
    for start, end in sorted(spans[1:], reverse=True):
        source = source[:start] + source[end:]
    return source


def preserve_real_dashboard_actions(source):
    old = "final String buttonText = table.status == TableStatus.available ? 'Iniciar' : table.status == TableStatus.playing ? 'Finalizar' : 'Cobrar';"
    new = "final String buttonText = table.status == TableStatus.available ? 'Iniciar juego' : table.status == TableStatus.playing ? 'Finalizar juego' : 'Cobrar';"
    if old in source:
        return source.replace(old, new, 1)
    if "'Iniciar juego'" in source:
        return source
    raise SystemExit('ADMIN UI FAILED: acción real de inicio ausente en DashboardPage')


def ensure_workday_view(source):
    dashboard_start, dashboard_end = class_span(source, '_DashboardPageState')
    dashboard = source[dashboard_start:dashboard_end]
    if 'Widget workdayView()' in dashboard:
        return source
    method = '''
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
'''
    insert_at = dashboard.rfind('\n}')
    if insert_at < 0:
        raise SystemExit('ADMIN UI FAILED: DashboardPageState sin cierre válido')
    dashboard = dashboard[:insert_at] + method + dashboard[insert_at:]
    return source[:dashboard_start] + dashboard + source[dashboard_end:]


source = TARGET.read_text()
source = remove_duplicate_local_ip(source)
source = repair_app_root(source)
source = preserve_real_dashboard_actions(source)
source = ensure_workday_view(source)

TARGET.write_text(source)
print('OK: raíz de app corregida; Dashboard preservado, jornada implementada y acciones reales normalizadas')
