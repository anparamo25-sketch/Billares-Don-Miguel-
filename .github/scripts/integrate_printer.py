from pathlib import Path

path = Path('lib/main.dart')
source = path.read_text(encoding='utf-8')
anchor = '  Future<String?> printReceipt(BillTable table) async {'

if 'Future<bool> configureThermalPrinter() async' not in source:
    if anchor not in source:
        raise SystemExit('No se encontró printReceipt.')
    function = '''  Future<bool> configureThermalPrinter() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    if (!mounted) return false;
    try {
      if (!await PrintBluetoothThermal.bluetoothEnabled) return false;
      if (!await PrintBluetoothThermal.isPermissionBluetoothGranted) return false;
      final List<BluetoothInfo> printers = await PrintBluetoothThermal.pairedBluetooths;
      if (printers.isEmpty) return false;
      final String? savedMac = prefs.getString('thermal_printer_mac');
      final String? selectedMac = await showDialog<String>(
        context: context,
        builder: (BuildContext dialogContext) => AlertDialog(
          title: const Text('Impresora térmica'),
          content: SizedBox(
            width: double.maxFinite,
            child: ListView(
              shrinkWrap: true,
              children: printers.map((BluetoothInfo printer) {
                final bool selected = printer.macAdress == savedMac;
                return ListTile(
                  leading: Icon(selected ? Icons.check_circle : Icons.print_outlined),
                  title: Text(printer.name.isEmpty ? 'Impresora térmica' : printer.name),
                  subtitle: Text(printer.macAdress),
                  onTap: () => Navigator.pop(dialogContext, printer.macAdress),
                );
              }).toList(),
            ),
          ),
          actions: <Widget>[
            if (savedMac != null)
              TextButton(
                onPressed: () async {
                  await prefs.remove('thermal_printer_mac');
                  await prefs.remove('thermal_printer_name');
                  if (dialogContext.mounted) Navigator.pop(dialogContext, '');
                },
                child: const Text('Quitar impresora'),
              ),
            FilledButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cerrar')),
          ],
        ),
      );
      if (selectedMac == null) return savedMac != null;
      if (selectedMac.isEmpty) return false;
      final BluetoothInfo selected = printers.firstWhere((BluetoothInfo p) => p.macAdress == selectedMac);
      await prefs.setString('thermal_printer_mac', selected.macAdress);
      await prefs.setString('thermal_printer_name', selected.name);
      return true;
    } catch (_) {
      return false;
    }
  }

'''
    source = source.replace(anchor, function + anchor, 1)

old = '''      final BluetoothInfo printer = printers.first;
      final bool connected = await PrintBluetoothThermal.connect(
        macPrinterAddress: printer.macAdress,
      );'''
new = '''      final SharedPreferences prefs = await SharedPreferences.getInstance();
      final String? savedMac = prefs.getString('thermal_printer_mac');
      if (savedMac == null || savedMac.isEmpty) return 'Configura primero la impresora térmica desde Configuración.';
      BluetoothInfo? printer;
      for (final BluetoothInfo item in printers) {
        if (item.macAdress == savedMac) { printer = item; break; }
      }
      if (printer == null) return 'La impresora guardada ya no está emparejada. Ve a Configuración → Impresora térmica.';
      final bool connected = await PrintBluetoothThermal.connect(macPrinterAddress: printer.macAdress);'''
if old not in source:
    raise SystemExit('No se encontró selección automática de impresora.')
source = source.replace(old, new, 1)

settings_anchor = "              const Text(\n                'Las tarifas no pueden modificarse desde el administrador.',\n              ),"
if settings_anchor not in source:
    raise SystemExit('No se encontró configuración de tarifas.')
source = source.replace(settings_anchor, settings_anchor + '''
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: () async {
                  Navigator.pop(context);
                  await configureThermalPrinter();
                },
                icon: const Icon(Icons.print_outlined),
                label: const Text('Impresora térmica'),
              ),''', 1)

path.write_text(source, encoding='utf-8')
print('SOURCE_INTEGRATION_WRITTEN=OK')
