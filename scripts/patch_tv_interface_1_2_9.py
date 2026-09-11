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
if not PREVIEW.is_file():
    raise SystemExit('ERROR: falta lib/receipt_preview_page.dart para el flujo de cobro')

html = TEMPLATE.read_text(encoding='utf-8')
if 'src="/tv-logo.webp"' not in html:
    raise SystemExit('ERROR: cloud-tv/public/index.html no contiene /tv-logo.webp')
html64 = base64.b64encode(html.encode('utf-8')).decode('ascii')
source = MAIN.read_text(encoding='utf-8')

getter_pattern = r'String\s+get\s+tvHtml\s*=>.*?;\s*(?=Map\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap)'
replacement = "String get tvHtml => utf8.decode(base64Decode('" + html64 + "'));\n\n"
source, count = re.subn(getter_pattern, lambda _: replacement, source, count=1, flags=re.S)
if count != 1:
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

if "import 'receipt_preview_page.dart';" not in source:
    import_marker = "import 'cloud_tv_sync.dart';"
    if source.count(import_marker) != 1:
        raise SystemExit('ERROR: no se encontró exactamente el import de cloud_tv_sync.dart')
    source = source.replace(import_marker, import_marker + "\nimport 'receipt_preview_page.dart';", 1)

printer_methods = '''  Future<List<BluetoothInfo>> _pairedThermalPrinters() async {
    final bool enabled = await PrintBluetoothThermal.bluetoothEnabled;
    if (!enabled) {
      throw StateError('Activa Bluetooth en la tablet para configurar la impresora.');
    }
    final bool permission = await PrintBluetoothThermal.isPermissionBluetoothGranted;
    if (!permission) {
      throw StateError('Concede el permiso de Bluetooth en Android y vuelve a pulsar Impresora térmica.');
    }
    return PrintBluetoothThermal.pairedBluetooths;
  }

  Future<bool> configureThermalPrinter() async {
    if (!mounted) return false;
    try {
      final List<BluetoothInfo> printers = await _pairedThermalPrinters();
      if (!mounted) return false;
      if (printers.isEmpty) {
        await showDialog<void>(
          context: context,
          builder: (BuildContext dialogContext) => AlertDialog(
            title: const Text('Impresora térmica'),
            content: const Text(
              'No hay impresoras Bluetooth emparejadas con esta tablet. Empareja primero la impresora desde Bluetooth de Android y vuelve aquí.',
            ),
            actions: <Widget>[
              FilledButton(
                onPressed: () => Navigator.pop(dialogContext),
                child: const Text('Cerrar'),
              ),
            ],
          ),
        );
        return false;
      }

      final SharedPreferences prefs = await SharedPreferences.getInstance();
      final String? savedMac = prefs.getString('thermal_printer_mac');
      BluetoothInfo? selected;
      for (final BluetoothInfo printer in printers) {
        if (printer.macAdress == savedMac) {
          selected = printer;
          break;
        }
      }

      final BluetoothInfo? chosen = await showDialog<BluetoothInfo>(
        context: context,
        builder: (BuildContext dialogContext) => StatefulBuilder(
          builder: (BuildContext context, StateSetter setDialogState) {
            return AlertDialog(
              title: const Text('Impresora térmica'),
              content: SizedBox(
                width: 460,
                child: SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        selected == null
                            ? 'Selecciona la impresora Bluetooth que usará la aplicación.'
                            : 'Configurada: ${selected!.name}',
                      ),
                      const SizedBox(height: 12),
                      ...printers.map(
                        (BluetoothInfo printer) => RadioListTile<String>(
                          value: printer.macAdress,
                          groupValue: selected?.macAdress,
                          title: Text(
                            printer.name.isEmpty ? 'Impresora Bluetooth' : printer.name,
                          ),
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
              ),
              actions: <Widget>[
                TextButton(
                  onPressed: () => Navigator.pop(dialogContext),
                  child: const Text('Cancelar'),
                ),
                FilledButton.icon(
                  onPressed: selected == null
                      ? null
                      : () => Navigator.pop(dialogContext, selected),
                  icon: const Icon(Icons.check),
                  label: const Text('CONFIGURAR IMPRESORA'),
                ),
              ],
            );
          },
        ),
      );

      if (chosen == null) return false;
      final bool connected = await PrintBluetoothThermal.connect(
        macPrinterAddress: chosen.macAdress,
      );
      if (!connected) {
        if (mounted) {
          await showDialog<void>(
            context: context,
            builder: (BuildContext dialogContext) => AlertDialog(
              title: const Text('Impresora térmica'),
              content: const Text(
                'La impresora está emparejada, pero la aplicación no pudo conectarse. Verifica que esté encendida y vuelve a intentarlo.',
              ),
              actions: <Widget>[
                FilledButton(
                  onPressed: () => Navigator.pop(dialogContext),
                  child: const Text('Cerrar'),
                ),
              ],
            ),
          );
        }
        return false;
      }
      await prefs.setString('thermal_printer_mac', chosen.macAdress);
      await prefs.setString('thermal_printer_name', chosen.name);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Impresora configurada: ${chosen.name.isEmpty ? 'Bluetooth' : chosen.name}',
            ),
          ),
        );
      }
      return true;
    } catch (error) {
      if (mounted) {
        await showDialog<void>(
          context: context,
          builder: (BuildContext dialogContext) => AlertDialog(
            title: const Text('Configuración de impresora'),
            content: Text(error.toString().replaceFirst('Bad state: ', '')),
            actions: <Widget>[
              FilledButton(
                onPressed: () => Navigator.pop(dialogContext),
                child: const Text('Cerrar'),
              ),
            ],
          ),
        );
      }
      return false;
    }
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
      final bool permission = await PrintBluetoothThermal.isPermissionBluetoothGranted;
      if (!permission) return 'Concede el permiso de Bluetooth y vuelve a intentar.';
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      final String? savedMac = prefs.getString('thermal_printer_mac');
      if (savedMac == null || savedMac.isEmpty) {
        return 'Primero configura la impresora térmica en Configuración.';
      }
      final List<BluetoothInfo> printers = await PrintBluetoothThermal.pairedBluetooths;
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
      bytes.addAll(generator.text(
        'Billares Don Miguel',
        styles: const PosStyles(
          align: PosAlign.center,
          bold: true,
          height: PosTextSize.size2,
          width: PosTextSize.size2,
        ),
      ));
      bytes.addAll(generator.text(
        'Mesa ${table.number}',
        styles: const PosStyles(align: PosAlign.center, bold: true),
      ));
      bytes.addAll(generator.hr());
      bytes.addAll(generator.text('Hora de inicio: ${clock(table.start!)}'));
      bytes.addAll(generator.text('Hora finalizada: ${clock(table.end!)}'));
      bytes.addAll(generator.text(
        'Tiempo jugado: ${duration(table.end!.difference(table.start!).inSeconds)}',
      ));
      bytes.addAll(generator.text('Tarifa: ${money(table.rate)} / hora'));
      bytes.addAll(generator.hr());
      bytes.addAll(generator.text(
        'MONTO A PAGAR',
        styles: const PosStyles(align: PosAlign.center, bold: true),
      ));
      bytes.addAll(generator.text(
        money(table.amount),
        styles: const PosStyles(
          align: PosAlign.center,
          bold: true,
          height: PosTextSize.size2,
          width: PosTextSize.size2,
        ),
      ));
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
source, count = re.subn(
    r'  Future<String\?> printReceipt\(BillTable table\) async \{.*?\n  \}\n\n  Future<void> collect',
    lambda _: new_print + '  Future<void> collect',
    source,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit('ERROR: no se encontró exactamente la implementación de printReceipt')

if 'onPrint: () async => printReceipt(table)' not in source:
    raise SystemExit('ERROR: el flujo collect ya no está enlazado a la vista previa de recibo')

printer_button = '''                FilledButton.icon(
                  onPressed: () => configureThermalPrinter(),
                  icon: const Icon(Icons.print_outlined),
                  label: const Text('Impresora térmica'),
                ),
'''
button_marker = "label: const Text('Impresora térmica')"
if button_marker not in source:
    anchor = '''                FilledButton.icon(
                  onPressed: showTvConnection,
                  icon: const Icon(Icons.tv),
                  label: const Text('Mostrar en TV'),
                ),
'''
    if anchor not in source:
        raise SystemExit('ERROR: no se encontró el bloque de acciones del panel central')
    source = source.replace(anchor, anchor + printer_button, 1)
else:
    source = re.sub(
        r"FilledButton\.icon\(\s*onPressed:\s*[^,]+,\s*icon:\s*const Icon\(Icons\.print_outlined\),\s*label:\s*const Text\('Impresora térmica'\),\s*\)",
        printer_button.rstrip(),
        source,
        count=1,
        flags=re.S,
    )

pub = PUBSPEC.read_text(encoding='utf-8')
asset_block = '  assets:\n    - assets/tv-logo.webp\n'
if asset_block not in pub:
    marker_pub = '  uses-material-design: true\n'
    if marker_pub not in pub:
        raise SystemExit('ERROR: no se encontró la sección flutter de pubspec.yaml')
    pub = pub.replace(marker_pub, marker_pub + asset_block, 1)
    PUBSPEC.write_text(pub, encoding='utf-8')

source = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.9+129';", source, count=1)
MAIN.write_text(source, encoding='utf-8')
subprocess.run(['dart', 'format', 'lib/main.dart', 'lib/receipt_preview_page.dart'], check=True)
print('OK: fuente TV 1.2.9+129 y configuración persistente de impresora Bluetooth preparados')
