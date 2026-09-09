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
    # Replace the entire BillaresApp class, not only its build method.
    # This removes any accidentally injected Dashboard methods from the
    # application-root class and leaves DashboardPage as the sole owner of
    # dashboard state/actions.
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
    # The real DashboardPage already owns the table controls. Normalize only
    # the visible label of its existing start action; do not rebuild or remove
    # the Dashboard implementation.
    old = "final String buttonText = table.status == TableStatus.available ? 'Iniciar' : table.status == TableStatus.playing ? 'Finalizar' : 'Cobrar';"
    new = "final String buttonText = table.status == TableStatus.available ? 'Iniciar juego' : table.status == TableStatus.playing ? 'Finalizar juego' : 'Cobrar';"
    if old in source:
        return source.replace(old, new, 1)
    if "'Iniciar juego'" in source:
        return source
    raise SystemExit('ADMIN UI FAILED: acción real de inicio ausente en DashboardPage')


source = TARGET.read_text()

# Structural source correction only:
# 1) keep exactly one local-IP helper;
# 2) replace the entire BillaresApp class with a clean application root;
# 3) preserve the real DashboardPage and normalize its existing action labels.
source = remove_duplicate_local_ip(source)
source = repair_app_root(source)
source = preserve_real_dashboard_actions(source)

TARGET.write_text(source)
print('OK: BillaresApp reconstruida estructuralmente; DashboardPage preservado y acciones reales normalizadas')