from pathlib import Path
import base64
import json
import re
import subprocess

ROOT = Path('.')
MAIN = ROOT / 'lib/main.dart'
TEMPLATE = ROOT / 'cloud-tv/public/index.html'
LOGO = ROOT / 'assets/tv-logo.webp'

html = TEMPLATE.read_text(encoding='utf-8')
logo64 = base64.b64encode(LOGO.read_bytes()).decode('ascii')
html = html.replace('src="/tv-logo.webp"', f'src="data:image/webp;base64,{logo64}"')
html = html.replace('C$', r'C\$')
dart_html = json.dumps(html, ensure_ascii=False, separators=(',', ':'))
source = MAIN.read_text(encoding='utf-8')

# Reemplaza de forma robusta el getter completo, aunque Dart haya insertado
# saltos de línea o espacios distintos al formato esperado originalmente.
getter_pattern = r'String\s+get\s+tvHtml\s*=>.*?;\s*(?=Map\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap)'
replacement = 'String get tvHtml => ' + dart_html + ';\n\n'
source, getter_count = re.subn(getter_pattern, replacement, source, count=1, flags=re.S)
if getter_count != 1:
    raise SystemExit('ERROR: no se pudo reemplazar tvHtml en la versión 1.2.9+129')

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
    // El cobro queda guardado antes de intentar imprimir.
    await printReceipt(receiptTable);
  }'''
if old_collect in source:
    source = source.replace(old_collect, new_collect, 1)

old_grid = "mainAxisExtent: width >= 1100 ? 350 : width >= 650 ? 365 : 390"
new_grid = "mainAxisExtent: width >= 1100 ? 410 : width >= 650 ? 410 : 430"
if old_grid in source:
    source = source.replace(old_grid, new_grid, 1)

# La fuente final debe seguir identificando explícitamente la versión 1.2.9/129.
source = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.9+129';", source, count=1)

MAIN.write_text(source, encoding='utf-8')

# Validate the modified Dart source before the release build.
subprocess.run(['dart', 'format', 'lib/main.dart'], check=True)
subprocess.run(['dart', 'analyze', 'lib/main.dart'], check=True)

# Persist the generated source so the repository matches the APK that was built.
subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
subprocess.run(['git', 'config', 'user.email', '41898282+anparamo25-sketch@users.noreply.github.com'], check=True)
subprocess.run(['git', 'add', 'lib/main.dart'], check=True)
if subprocess.run(['git', 'diff', '--cached', '--quiet']).returncode != 0:
    subprocess.run(['git', 'commit', '-m', 'feat: actualizar interfaz TV y cobro para 1.2.9+129 [skip ci]'], check=True)
    subprocess.run(['git', 'push', 'origin', 'HEAD:main'], check=True)

print('OK: interfaz TV, logo, tarjetas, Cobrar e impresión automática preparados para 1.2.9+129')
