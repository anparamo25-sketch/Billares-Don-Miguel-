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
    marker = 'Widget build(BuildContext context)'
    builds = []
    offset = class_start
    while True:
        start = source.find(marker, offset, class_end)
        if start < 0:
            break
        brace = source.find('{', start, class_end)
        if brace < 0:
            break
        end = brace_end(source, brace)
        prefix = source.rfind('@override', class_start, start)
        line_start = source.rfind('\n', class_start, start) + 1
        if prefix >= line_start:
            start = prefix
        builds.append((start, end))
        offset = end

    if not builds:
        raise SystemExit('ADMIN UI FAILED: build de BillaresApp ausente')

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
    for start, end in sorted(spans[1:], reverse=True):
        source = source[:start] + source[end:]
    return source


source = TARGET.read_text()

# Structural source correction only:
# 1) keep exactly one local-IP helper;
# 2) make BillaresApp the application root.
# The administrative DashboardPage is deliberately NOT rebuilt here. Its real
# implementation is produced by rebuild_tv_1_2_6.py and must remain intact,
# including the real start/finish/collect actions and responsive navigation.
source = remove_duplicate_local_ip(source)
source = repair_app_root(source)

TARGET.write_text(source)
print('OK: raíz Dart normalizada; DashboardPage administrativo preservado sin reconstrucción destructiva')
