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
    raise SystemExit('ADMIN UI FAILED: expresión build sin terminar')


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
class_start, class_end = class_span(source, '_DashboardPageState')

builds = method_spans(source, class_start, class_end, 'Widget build(BuildContext context)')
if not builds:
    raise SystemExit('ADMIN UI FAILED: no existe build() dentro de _DashboardPageState')

# La última build() es la versión administrativa nueva ya generada en la fuente.
# Se conserva su cuerpo y se eliminan las versiones anteriores para dejar exactamente
# un build() y un _summaryCard(), haciendo la transformación idempotente.
_, build_end = builds[-1]
build_template = source[builds[-1][0]:build_end]

summaries = method_spans(source, class_start, class_end, 'Widget _summaryCard(')
remove_ranges = builds + summaries
for start, end in sorted(remove_ranges, reverse=True):
    source = source[:start] + source[end:]
    if start < class_end:
        class_end -= end - start

# Recalcular el cierre real de la clase después de eliminar métodos.
class_start, class_end = class_span(source, '_DashboardPageState')
insert_at = class_end - 1
source = source[:insert_at] + '\n\n' + SUMMARY + build_template + source[insert_at:]
TARGET.write_text(source)
print('OK: interfaz administrativa normalizada estructuralmente en _DashboardPageState')
