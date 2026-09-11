# Corrección TV 1.2.9+129 y flujo de cobro con impresión obligatoria.
from pathlib import Path
import base64
import re
import subprocess

ROOT = Path('.')
MAIN = ROOT / 'lib/main.dart'
TEMPLATE = ROOT / 'cloud-tv/public/index.html'
LOGO = ROOT / 'assets/tv-logo.webp'
PUBSPEC = ROOT / 'pubspec.yaml'
PREVIEW = ROOT / 'lib/receipt_preview_page.dart'

if not MAIN.is_file() or not TEMPLATE.is_file() or not LOGO.is_file():
    raise SystemExit('ERROR: faltan archivos base de la interfaz TV o el logo real')

html = TEMPLATE.read_text(encoding='utf-8')
if 'src="/tv-logo.webp"' not in html:
    raise SystemExit('ERROR: cloud-tv/public/index.html no contiene /tv-logo.webp')
html64 = base64.b64encode(html.encode('utf-8')).decode('ascii')

source = MAIN.read_text(encoding='utf-8')
getter_pattern = r'String\s+get\s+tvHtml\s*=>.*?;\s*(?=Map\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap)'
replacement = "String get tvHtml => utf8.decode(base64Decode('" + html64 + "'));\n\n"
source, getter_count = re.subn(getter_pattern, replacement, source, count=1, flags=re.S)
if getter_count != 1:
    raise SystemExit('ERROR: no se pudo regenerar tvHtml correctamente para 1.2.9+129')

endpoint = '''    if (request.uri.path == '/tv-logo.webp') {
      try {
        final ByteData logo = await rootBundle.load('assets/tv-logo.webp');
        response.headers.contentType = ContentType('image', 'webp');
        response.headers.contentLength = logo.lengthInBytes;
        response.add(logo.buffer.asUint8List());
      } catch (_) {
        response.statusCode = HttpStatus.notFound;
      }
      await response.close();
      return;
    }
'''
marker = "    if (request.uri.path == '/health') {"
if "request.uri.path == '/tv-logo.webp'" not in source:
    if marker not in source:
        raise SystemExit('ERROR: no se encontró el punto de inserción del endpoint /tv-logo.webp')
    source = source.replace(marker, endpoint + marker, 1)

# Flujo de cobro: COBRAR abre una vista previa bloqueada y solo IMPRIMIR
# puede confirmar el cobro. La impresora térmica se usa a 58 mm.
if not PREVIEW.is_file():
    raise SystemExit('ERROR: falta lib/receipt_preview_page.dart para el flujo de cobro')

if "import 'receipt_preview_page.dart';" not in source:
    import_marker = "import 'cloud_tv_sync.dart';"
    if source.count(import_marker) != 1:
        raise SystemExit('ERROR: no se encontró exactamente el import de cloud_tv_sync.dart')
    source = source.replace(
        import_marker,
        import_marker + "\nimport 'receipt_preview_page.dart';",
        1,
    )

new_print = '''  Future<String?> printReceipt(BillTable table) async {
    if (table.start == null || table.end == null) {
      return 'La partida no tiene datos completos para imprimir.';
    }
    try {
      final bool enabled = await PrintBluetoothThermal.bluetoothEnabled;
      if (!enabled) return 'Activa Bluetooth en la tablet para imprimir.';
      final bool permission =
          await PrintBluetoothThermal.isPermissionBluetoothGranted;
      if (!permission) {
        return 'Concede el permiso de Bluetooth y vuelve a intentar.';
      }
      final List<BluetoothInfo> printers =
          await PrintBluetoothThermal.pairedBluetooths;
      if (printers.isEmpty) {
        return 'No hay impresoras Bluetooth emparejadas con la tablet.';
      }
      final BluetoothInfo printer = printers.first;
      final bool connected = await PrintBluetoothThermal.connect(
        macPrinterAddress: printer.macAdress,
      );
      if (!connected) return 'No se pudo conectar con la impresora.';

      final CapabilityProfile profile = await CapabilityProfile.load();
      final Generator generator = Generator(PaperSize.mm58, profile);
      final List<int> bytes = <int>[];
      bytes.addAll(
        generator.text(
          'Billares Don Miguel',
          styles: const PosStyles(
            align: PosAlign.center,
            bold: true,
            height: PosTextSize.size2,
            width: PosTextSize.size2,
          ),
        ),
      );
      bytes.addAll(
        generator.text(
          'Mesa ${table.number}',
          styles: const PosStyles(align: PosAlign.center, bold: true),
        ),
      );
      bytes.addAll(generator.hr());
      bytes.addAll(generator.text('Hora de inicio: ${clock(table.start!)}'));
      bytes.addAll(generator.text('Hora finalizada: ${clock(table.end!)}'));
      bytes.addAll(
        generator.text(
          'Tiempo jugado: ${duration(table.end!.difference(table.start!).inSeconds)}',
        ),
      );
      bytes.addAll(generator.text('Tarifa: ${money(table.rate)} / hora'));
      bytes.addAll(generator.hr());
      bytes.addAll(
        generator.text(
          'MONTO A PAGAR',
          styles: const PosStyles(align: PosAlign.center, bold: true),
        ),
      );
      bytes.addAll(
        generator.text(
          money(table.amount),
          styles: const PosStyles(
            align: PosAlign.center,
            bold: true,
            height: PosTextSize.size2,
            width: PosTextSize.size2,
          ),
        ),
      );
      bytes.addAll(generator.feed(3));
      bytes.addAll(generator.cut());
      final bool printed = await PrintBluetoothThermal.writeBytes(bytes);
      if (!printed) return 'La impresora no aceptó el recibo.';
      return null;
    } catch (_) {
      return 'No se pudo imprimir el recibo.';
    }
  }

'''
source, print_count = re.subn(
    r"  Future<void> printReceipt\(BillTable table\) async \{.*?\n  \}\n\n  Future<void> collect",
    new_print + '  Future<void> collect',
    source,
    count=1,
    flags=re.S,
)
if print_count != 1:
    raise SystemExit('ERROR: no se encontró exactamente la implementación actual de printReceipt')

new_collect = '''  Future<void> collect(BillTable table) async {
    if (table.status != TableStatus.pending ||
        table.start == null ||
        table.end == null ||
        !mounted) {
      return;
    }
    final bool? printed = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder:
            (_) => ReceiptPreviewPage(
              tableNumber: table.number,
              startText: clock(table.start!),
              endText: clock(table.end!),
              durationText: duration(
                table.end!.difference(table.start!).inSeconds,
              ),
              rateText: '${money(table.rate)} / hora',
              amountText: money(table.amount),
              onPrint: () async => printReceipt(table),
            ),
      ),
    );
    if (printed != true || !mounted) return;

    final HistoryEntry entry = HistoryEntry(
      table: table.number,
      start: table.start!,
      end: table.end!,
      seconds: table.end!.difference(table.start!).inSeconds,
      amount: table.amount,
      workDate: workdayOpenedAt ?? table.end!,
    );
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
  }

'''
source, collect_count = re.subn(
    r"  Future<void> collect\(BillTable table\) async \{.*?\n  \}\n\n  int buildNumber",
    new_collect + '  int buildNumber',
    source,
    count=1,
    flags=re.S,
)
if collect_count != 1:
    raise SystemExit('ERROR: no se encontró exactamente la implementación actual de collect')

source, button_count = re.subn(
    r"            if \(table\.status == TableStatus\.pending\) \.\.\.<Widget>\[.*?            \],\n",
    '',
    source,
    count=1,
    flags=re.S,
)
if button_count != 1:
    raise SystemExit('ERROR: no se encontró el botón independiente de imprimir recibo')

pub = PUBSPEC.read_text(encoding='utf-8')
if '  assets:\n    - assets/tv-logo.webp\n' not in pub:
    marker_pub = '  uses-material-design: true\n'
    if marker_pub not in pub:
        raise SystemExit('ERROR: no se encontró la sección flutter de pubspec.yaml')
    pub = pub.replace(
        marker_pub,
        marker_pub + '  assets:\n    - assets/tv-logo.webp\n',
        1,
    )
    PUBSPEC.write_text(pub, encoding='utf-8')

source = re.sub(
    r"const String appVersion = '[^']+';",
    "const String appVersion = '1.2.9+129';",
    source,
    count=1,
)
MAIN.write_text(source, encoding='utf-8')
subprocess.run(['dart', 'format', 'lib/main.dart', 'lib/receipt_preview_page.dart'], check=True)

subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
subprocess.run(
    ['git', 'config', 'user.email', '41898282+anparamo25-sketch@users.noreply.github.com'],
    check=True,
)
subprocess.run(
    ['git', 'add', 'lib/main.dart', 'lib/receipt_preview_page.dart', 'pubspec.yaml'],
    check=True,
)
if subprocess.run(['git', 'diff', '--cached', '--quiet']).returncode != 0:
    subprocess.run(
        ['git', 'commit', '-m', 'feat: cobro con vista previa e impresion obligatoria [skip ci]'],
        check=True,
    )
    subprocess.run(['git', 'push', 'origin', 'HEAD:main'], check=True)

print('OK: fuente TV 1.2.9+129 y flujo de cobro con vista previa e impresión obligatoria preparados')
