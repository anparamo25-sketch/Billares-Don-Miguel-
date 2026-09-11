from pathlib import Path
import base64
import re
import subprocess

ROOT = Path('.')
MAIN = ROOT / 'lib/main.dart'
TEMPLATE = ROOT / 'cloud-tv/public/index.html'
LOGO = ROOT / 'assets/tv-logo.webp'

# La TV se incorpora al código Dart como datos Base64. Esto evita que el HTML,
# JavaScript o CSS puedan ser interpretados como interpolación Dart ($) o como
# escapes de una cadena Dart. No se modifica la lógica de la TV: se corrige la
# representación del HTML para que el código generado sea siempre sintácticamente válido.
html = TEMPLATE.read_text(encoding='utf-8')
logo64 = base64.b64encode(LOGO.read_bytes()).decode('ascii')
html = html.replace('src="/tv-logo.webp"', f'src="data:image/webp;base64,{logo64}"')
html64 = base64.b64encode(html.encode('utf-8')).decode('ascii')

source = MAIN.read_text(encoding='utf-8')

# Sustituye únicamente la definición del getter por una representación Dart
# segura. La cadena Base64 usa únicamente caracteres ASCII sin significado
# especial para el parser de Dart.
getter_pattern = r'String\s+get\s+tvHtml\s*=>.*?;\s*(?=Map\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap)'
replacement = "String get tvHtml => utf8.decode(base64Decode('" + html64 + "'));\n\n"
source, getter_count = re.subn(getter_pattern, replacement, source, count=1, flags=re.S)
if getter_count != 1:
    raise SystemExit('ERROR: no se pudo generar tvHtml correctamente para 1.2.9+129')

old_collect = '''  Future<void> collect(BillTable table) async {
    // Cobrar debe funcionar aunque no haya impresora Bluetooth disponible.
    // La impresión queda como acción independiente en 'Imprimir recibo'.
    if (table.status != TableStatus.pending || table.start == null || table.end == null) return;
    final HistoryEntry entry = HistoryEntry(table: table.number, start: table.start!, end: table.end!, seconds: table.end!.difference(table.start!).inSeconds, amount: table.amount, workDate: workdayOpenedAt ?? table.end!);
    setState(() {
      history.add(entry);
      if (workdayActive) {
        workdayGenerated += table.amount;
        workdayGames += 1;
      }
      table.status = TableStatus.available;
      table.start = null;
      table.end = null;
      table.amount = 0;
    });
    await saveHistory();
    await saveTables();
    await saveWorkday();
  }'''
new_collect = '''  Future<void> collect(BillTable table) async {
    if (table.status != TableStatus.pending || table.start == null || table.end == null) return;
    final BillTable receiptTable = BillTable(table.number, table.rate)
      ..status = TableStatus.pending
      ..start = table.start
      ..end = table.end
      ..amount = table.amount;
    final double collectedAmount = table.amount;
    final DateTime collectedStart = table.start!;
    final DateTime collectedEnd = table.end!;
    final HistoryEntry entry = HistoryEntry(
      table: table.number,
      start: collectedStart,
      end: collectedEnd,
      seconds: collectedEnd.difference(collectedStart).inSeconds,
      amount: collectedAmount,
      workDate: workdayOpenedAt ?? collectedEnd,
    );
    setState(() {
      history.add(entry);
      if (workdayActive) {
        workdayGenerated += collectedAmount;
        workdayGames += 1;
      }
      table.status = TableStatus.available;
      table.start = null;
      table.end = null;
      table.amount = 0;
    });
    await saveHistory();
    await saveTables();
    await saveWorkday();
    await printReceipt(receiptTable);
  }'''
if old_collect in source:
    source = source.replace(old_collect, new_collect, 1)

old_grid = "mainAxisExtent: width >= 1100 ? 350 : width >= 650 ? 365 : 390"
new_grid = "mainAxisExtent: width >= 1100 ? 410 : width >= 650 ? 410 : 430"
if old_grid in source:
    source = source.replace(old_grid, new_grid, 1)

source = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.9+129';", source, count=1)

MAIN.write_text(source, encoding='utf-8')

# La validación de dependencias se ejecuta en el workflow después de flutter pub get.
# Este generador solo debe producir y formatear la fuente, no analizarla antes de
# que Flutter haya resuelto las dependencias del proyecto.
subprocess.run(['dart', 'format', 'lib/main.dart'], check=True)

subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
subprocess.run(['git', 'config', 'user.email', '41898282+anparamo25-sketch@users.noreply.github.com'], check=True)
subprocess.run(['git', 'add', 'lib/main.dart'], check=True)
if subprocess.run(['git', 'diff', '--cached', '--quiet']).returncode != 0:
    subprocess.run(['git', 'commit', '-m', 'fix: generar fuente TV válida para 1.2.9+129 [skip ci]'], check=True)
    subprocess.run(['git', 'push', 'origin', 'HEAD:main'], check=True)

print('OK: fuente TV generada con representación segura y válida para 1.2.9+129')
