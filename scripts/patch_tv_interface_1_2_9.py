# Generación de fuente TV 1.2.9+129 y flujo de cobro con impresión obligatoria.
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

printer_methods = '''  Future<bool> configureThermalPrinter() async {
    final bool enabled = await PrintBluetoothThermal.bluetoothEnabled;
    if (!enabled) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Activa Bluetooth en la tablet para configurar la impresora.')),
        );
      }
      return false;
    }
    final bool permission =
        await PrintBluetoothThermal.isPermissionBluetoothGranted;
    if (!permission) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Concede el permiso de Bluetooth y vuelve a configurar la impresora.')),
        );
      }
      return false;
    }
    List<BluetoothInfo> printers =
        await PrintBluetoothThermal.pairedBluetooths;
    if (!mounted) return false;
    if (printers.isEmpty) {
      await showDialog<void>(
        context: context,
        builder: (BuildContext context) => AlertDialog(
          title: const Text('Impresora térmica'),
          content: const Text(
            'No hay impresoras Bluetooth emparejadas con esta tablet. Empareja primero la impresora desde Bluetooth de Android y vuelve aquí.',
          ),
          actions: <Widget>[
            FilledButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cerrar'),
            ),
          ],
        ),
      );
      return false;
    }

    final SharedPreferences prefs = await SharedPreferences.getInstance();
    String? savedMac = prefs.getString('thermal_printer_mac');
    String? savedName = prefs.getString('thermal_printer_name');
    BluetoothInfo? selected;
    for (final BluetoothInfo printer in printers) {
      if (printer.macAdress == savedMac) {
        selected = printer;
        break;
      }
    }

    final bool? configured = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => StatefulBuilder(
        builder: (BuildContext context, StateSetter setDialogState) {
          return AlertDialog(
            title: const Text('Impresora térmica'),
            content: SizedBox(
              width: 460,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    selected == null
                        ? 'Selecciona la impresora Bluetooth que usará la aplicación.'
                        : 'Impresora configurada: ${selected!.name}',
                  ),
                  const SizedBox(height: 12),
                  ...printers.map(
                    (BluetoothInfo printer) => RadioListTile<String>(
                      value: printer.macAdress,
                      groupValue: selected?.macAdress,
                      title: Text(printer.name.isEmpty ? 'Impresora Bluetooth' : printer.name),
                      subtitle: Text(printer.macAdress),
                      onChanged: (String? value) {
                        if (value == null) return;
                        setDialogState(() {
                          selected = printers.firstWhere(
                            (BluetoothInfo item) => item.macAdress == value,
                          );
                        });
                      },
                    ),
                  ),
                ],
              ),
            ),
            actions: <Widget>[
              TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: const Text('Cancelar'),
              ),
              FilledButton.icon(
                onPressed: selected == null
                    ? null
                    : () async {
                        final BluetoothInfo printer = selected!;
                        final bool connected =
                            await PrintBluetoothThermal.connect(
                          macPrinterAddress: printer.macAdress,
                        );
                        if (!connected) {
                          if (dialogContext.mounted) {
                            ScaffoldMessenger.of(dialogContext).showSnackBar(
                              const SnackBar(
                                content: Text('No se pudo conectar con la impresora seleccionada.'),
                              ),
                            );
                          }
                          return;
                        }
                        await prefs.setString(
                          'thermal_printer_mac',
                          printer.macAdress,
                        );
                        await prefs.setString(
                          'thermal_printer_name',
                          printer.name,
                        );
                        savedMac = printer.macAdress;
                        savedName = printer.name;
                        if (dialogContext.mounted) {
                          Navigator.pop(dialogContext, true);
                        }
                      },
                icon: const Icon(Icons.check),
                label: const Text('CONFIGURAR IMPRESORA'),
              ),
            ],
          );
        },
      ),
    );
    if (configured == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Impresora configurada: ${savedName?.isEmpty ?? true ? 'Bluetooth' : savedName}',
          ),
        ),
      );
      return true;
    }
    return false;
  }

'''
if 'Future<bool> configureThermalPrinter() async {' not in source:
    marker_print = '  Future<String?> printReceipt(BillTable table) async {'
    if marker_print not in source:
        raise SystemExit('ERROR: no se encontró printReceipt para insertar la configuración de impresora')
    source = source.replace(marker_print, printer_methods + marker_print, 1)

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
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      final String? savedMac = prefs.getString('thermal_printer_mac');
      if (savedMac == null || savedMac.isEmpty) {
        return 'Primero configura la impresora térmica en Configuración.';
      }
      final List<BluetoothInfo> printers =
          await PrintBluetoothThermal.pairedBluetooths;
      BluetoothInfo? printer;
      for (final BluetoothInfo item in printers) {
        if (item.macAdress == savedMac) {
          printer = item;
          break;
        }
      }
      if (printer == null) {
        return 'La impresora configurada ya no está emparejada con la tablet. Entra en Configuración y pulsa CAMBIAR IMPRESORA.';
      }
      final bool connected = await PrintBluetoothThermal.connect(
        macPrinterAddress: savedMac,
      );
      if (!connected) {
        return 'No se pudo conectar con la impresora configurada. Verifica que esté encendida y vuelve a intentar.';
      }

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
    r"  Future<String\?> printReceipt\(BillTable table\) async \{.*?\n  \}\n\n  Future<void> collect",
    new_print + '  Future<void> collect',
    source,
    count=1,
    flags=re.S,
)
if print_count != 1:
    raise SystemExit('ERROR: no se encontró exactamente la implementación de printReceipt')

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
    raise SystemExit('ERROR: no se encontró exactamente collect')

settings_insert = """                  const SizedBox(height: 16),\n                  Builder(\n                    builder: (BuildContext context) {\n                      return FutureBuilder<SharedPreferences>(\n                        future: SharedPreferences.getInstance(),\n                        builder: (BuildContext context, AsyncSnapshot<SharedPreferences> snapshot) {\n                          final String printerName =\n                              snapshot.data?.getString('thermal_printer_name') ?? '';\n                          return ListTile(\n                            contentPadding: EdgeInsets.zero,\n                            leading: const Icon(Icons.print_outlined),\n                            title: const Text('Impresora térmica'),\n                            subtitle: Text(\n                              printerName.isEmpty\n                                  ? 'No configurada'\n                                  : 'Configurada: $printerName',\n                            ),\n                            trailing: FilledButton(\n                              onPressed: configureThermalPrinter,\n                              child: Text(\n                                printerName.isEmpty\n                                    ? 'CONFIGURAR'\n                                    : 'CAMBIAR IMPRESORA',\n                              ),\n                            ),\n                          );\n                        },\n                      );\n                    },\n                  ),\n"""
anchor = "                  const Text(\n                    'La TV muestra únicamente la pantalla de mesas; el panel administrativo permanece en el celular.',\n                  ),\n"
if "'Impresora térmica'" not in source:
    if anchor not in source:
        raise SystemExit('ERROR: no se encontró el bloque de configuración para insertar impresora')
    source = source.replace(anchor, anchor + settings_insert, 1)

pub = PUBSPEC.read_text(encoding='utf-8')
if '  assets:\n    - assets/tv-logo.webp\n' not in pub:
    marker_pub = '  uses-material-design: true\n'
    if marker_pub not in pub:
        raise SystemExit('ERROR: no se encontró la sección flutter de pubspec.yaml')
    pub = pub.replace(marker_pub, marker_pub + '  assets:\n    - assets/tv-logo.webp\n', 1)
    PUBSPEC.write_text(pub, encoding='utf-8')

source = re.sub(
    r"const String appVersion = '[^']+';",
    "const String appVersion = '1.2.9+129';",
    source,
    count=1,
)
MAIN.write_text(source, encoding='utf-8')
subprocess.run(['dart', 'format', 'lib/main.dart', 'lib/receipt_preview_page.dart'], check=True)

print('OK: fuente TV 1.2.9+129 y configuración persistente de impresora Bluetooth preparados')
"