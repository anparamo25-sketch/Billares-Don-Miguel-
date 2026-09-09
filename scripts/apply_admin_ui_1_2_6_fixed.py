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


def statement_end(source, index):
    paren = bracket = brace = 0
    i = index
    while i < len(source):
        if source[i] in "'\"":
            i = skip_string(source, i)
            continue
        if source.startswith('//', i):
            e = source.find('\n', i + 2)
            i = len(source) if e < 0 else e + 1
            continue
        c = source[i]
        if c == '(':
            paren += 1
        elif c == ')':
            paren -= 1
        elif c == '[':
            bracket += 1
        elif c == ']':
            bracket -= 1
        elif c == '{':
            brace += 1
        elif c == '}':
            if brace:
                brace -= 1
        elif c == ';' and paren == 0 and bracket == 0 and brace == 0:
            return i + 1
        i += 1
    raise SystemExit('ADMIN UI FAILED: expresión sin terminar')


def class_span(source, name):
    marker = 'class ' + name
    start = source.find(marker)
    if start < 0:
        raise SystemExit(f'ADMIN UI FAILED: clase {name} ausente')
    brace = source.find('{', start)
    if brace < 0:
        raise SystemExit(f'ADMIN UI FAILED: clase {name} sin cuerpo')
    return start, brace_end(source, brace)


def method_spans(source, class_start, class_end, marker):
    segment = source[class_start:class_end]
    positions = []
    offset = 0
    while True:
        rel = segment.find(marker, offset)
        if rel < 0:
            break
        start = class_start + rel
        brace = source.find('{', start, class_end)
        arrow = source.find('=>', start, class_end)
        if brace >= 0 and (arrow < 0 or brace < arrow):
            end = brace_end(source, brace)
        elif arrow >= 0:
            end = statement_end(source, arrow + 2)
        else:
            raise SystemExit(f'ADMIN UI FAILED: método {marker} inválido')
        prefix = source.rfind('@override', class_start, start)
        line_start = source.rfind('\n', class_start, start) + 1
        if prefix >= line_start:
            start = prefix
        positions.append((start, end))
        offset = rel + len(marker)
    return positions


def top_level_function_spans(source, marker):
    positions = []
    offset = 0
    while True:
        start = source.find(marker, offset)
        if start < 0:
            break
        # A top-level function is identified by the function's opening brace.
        brace = source.find('{', start)
        if brace < 0:
            break
        end = brace_end(source, brace)
        positions.append((start, end))
        offset = end
    return positions


def repair_app_root(source):
    class_start, class_end = class_span(source, 'BillaresApp')
    builds = method_spans(source, class_start, class_end, 'Widget build(BuildContext context)')
    if not builds:
        raise SystemExit('ADMIN UI FAILED: build de BillaresApp ausente')

    # BillaresApp debe contener únicamente el arranque de la aplicación.
    # La interfaz administrativa pertenece exclusivamente a DashboardPage.
    build_start, build_end = builds[-1]
    clean_build = '''  @override
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
  }'''
    for start, end in sorted(builds, reverse=True):
        source = source[:start] + source[end:]
    class_start, class_end = class_span(source, 'BillaresApp')
    insert_at = class_end - 1
    source = source[:insert_at] + '\n' + clean_build + '\n' + source[insert_at:]
    return source


def remove_duplicate_local_ip(source):
    spans = top_level_function_spans(source, 'Future<String?> _billaresLocalIp() async')
    if len(spans) <= 1:
        return source
    # Preserve the first canonical implementation and remove every duplicate.
    for start, end in sorted(spans[1:], reverse=True):
        source = source[:start] + source[end:]
    return source


SUMMARY = r'''  Widget _summaryCard(String label, String value, Color color, IconData icon) {
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

'''

source = TARGET.read_text()

# First restore the actual Dart ownership of the widgets and remove the duplicate
# top-level helper. These are structural corrections to the source, not regex patches.
source = remove_duplicate_local_ip(source)
source = repair_app_root(source)

class_start, class_end = class_span(source, '_DashboardPageState')
builds = method_spans(source, class_start, class_end, 'Widget build(BuildContext context)')
if not builds:
    raise SystemExit('ADMIN UI FAILED: no existe build() dentro de _DashboardPageState')

# The last build is the intended administrative UI. Keep it, remove any previous or
# duplicate implementations, and place exactly one summary helper plus one build in
# _DashboardPageState.
_, build_end = builds[-1]
build_template = source[builds[-1][0]:build_end]
summaries = method_spans(source, class_start, class_end, 'Widget _summaryCard(')
remove_ranges = builds + summaries
for start, end in sorted(remove_ranges, reverse=True):
    source = source[:start] + source[end:]

class_start, class_end = class_span(source, '_DashboardPageState')
insert_at = class_end - 1
source = source[:insert_at] + '\n\n' + SUMMARY + build_template + '\n' + source[insert_at:]
TARGET.write_text(source)
print('OK: Dart reparado estructuralmente; BillaresApp y DashboardPage normalizados')
