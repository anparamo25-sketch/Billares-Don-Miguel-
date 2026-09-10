from pathlib import Path
import json
import re

TARGET = Path('lib/main.dart')
source = TARGET.read_text()

# Version and printer dependencies.
source = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.8+128';", source, count=1)
if "package:print_bluetooth_thermal_plus/print_bluetooth_thermal.dart" not in source:
    source = source.replace("import 'package:path_provider/path_provider.dart';", "import 'package:path_provider/path_provider.dart';\nimport 'package:print_bluetooth_thermal_plus/print_bluetooth_thermal.dart';\nimport 'package:esc_pos_utils_plus/esc_pos_utils_plus.dart';", 1)

# Build the TV HTML without nested triple-quoted Python strings.
html = r'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Billares Don Miguel - TV</title><style>*{box-sizing:border-box}body{margin:0;background:#05070b;color:#fff;font-family:Arial,sans-serif}header{padding:14px 18px;background:#fff;border-bottom:3px solid #1557c0;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;min-height:108px}.brandLogo{justify-self:start;display:flex;align-items:center;gap:8px;color:#1557c0;font-weight:900}.brandLogo .mark{width:54px;height:54px;border:3px solid #1557c0;border-radius:12px;display:grid;place-items:center;font-size:20px}.brandTitle{justify-self:center}.brandTitle h1{margin:0;font-size:clamp(28px,4vw,46px);color:#1557c0}.liveBox{justify-self:end;text-align:center;color:#1557c0}.clock{font-size:clamp(15px,1.8vw,23px);font-weight:800}.live{font-size:clamp(16px,1.9vw,24px);font-weight:900}.grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:18px;padding:22px}.card{border-radius:18px;padding:22px;border:3px solid #64748b;min-height:280px;display:flex;flex-direction:column}.green{background:#103b22;border-color:#22c55e}.red{background:#511b1b;border-color:#ef4444}.yellow{background:#56490a;border-color:#eab308}.name{font-size:clamp(22px,2.5vw,34px);font-weight:900}.status{font-size:clamp(17px,1.8vw,24px);font-weight:800}.line{margin:8px 0;font-size:clamp(18px,1.65vw,23px);font-weight:700}.rate{margin:7px 0;font-size:clamp(18px,1.7vw,24px);font-weight:900}.payLabel{margin-top:auto;font-size:clamp(16px,1.5vw,21px);font-weight:900;text-transform:uppercase}.money{font-size:clamp(28px,3vw,42px);font-weight:900}@media(max-width:1100px){.grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:700px){header{grid-template-columns:auto 1fr auto}.brandLogo .word{display:none}.brandLogo .mark{width:44px;height:44px}.grid{grid-template-columns:repeat(2,minmax(0,1fr));padding:12px;gap:10px}}@media(max-width:430px){.grid{grid-template-columns:1fr}}</style></head><body><header><div class="brandLogo"><div class="mark">BDM</div><div class="word">LOGO</div></div><div class="brandTitle"><h1>Billares Don Miguel</h1></div><div class="liveBox"><div id="clock" class="clock">--:-- PM</div><div class="live">🟢 EN VIVO</div></div></header><main id="grid" class="grid"></main><script>function money(n){return 'C&#36; '+Number(n||0).toFixed(2)}function safe(v){return v==null?'—':String(v)}async function tick(){try{var r=await fetch('/api/state?ts='+Date.now(),{cache:'no-store'});var d=await r.json();document.getElementById('clock').textContent=safe(d.time);document.getElementById('grid').innerHTML=(d.tables||[]).map(function(t){var c=t.status==='Disponible'?'green':t.status==='En juego'?'red':'yellow';return '<section class="card '+c+'"><div class="name">Mesa '+t.number+'</div><div class="status">'+safe(t.status)+'</div><div class="rate">Tarifa: '+money(t.rate)+' / hora</div><div class="line">Hora de inicio: '+safe(t.start)+'</div><div class="line">Tiempo jugado: '+safe(t.elapsed)+'</div><div class="line">Hora finalizada: '+safe(t.end)+'</div><div class="payLabel">MONTO A PAGAR</div><div class="money">'+money(t.amount)+'</div></section>'}).join('')}catch(e){}}tick();setInterval(tick,1000);</script></body></html>'''

tv_dart = '  String get tvHtml => ' + json.dumps(html, ensure_ascii=False) + ';'
pattern = r"  String get tvHtml => .*?;\n\nMap<String, dynamic> stateMap"
if not re.search(pattern, source, flags=re.S):
    raise SystemExit('1.2.8 FAILED: no se encontró tvHtml')
source = re.sub(pattern, tv_dart + "\n\nMap<String, dynamic> stateMap", source, count=1, flags=re.S)

# Real Bluetooth receipt printing from the central tablet.
if 'Future<void> printReceipt(BillTable table)' not in source:
    marker = "  Future<void> collect(BillTable table) async {"
    if marker not in source:
        raise SystemExit('1.2.8 FAILED: no se encontró collect()')
    printer_method = '''  Future<void> printReceipt(BillTable table) async {
    if (table.start == null || table.end == null) return;
    try {
      if (!await PrintBluetoothThermal.bluetoothEnabled) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Activa Bluetooth en la tablet para imprimir.')));
        return;
      }
      if (!await PrintBluetoothThermal.isPermissionBluetoothGranted) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Concede el permiso de Bluetooth y vuelve a intentar.')));
        return;
      }
      final List<BluetoothInfo> printers = await PrintBluetoothThermal.pairedBluetooths;
      if (printers.isEmpty) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No hay impresoras Bluetooth emparejadas.')));
        return;
      }
      if (!mounted) return;
      final BluetoothInfo? selected = await showDialog<BluetoothInfo>(
        context: context,
        builder: (BuildContext dialogContext) => AlertDialog(
          title: const Text('Seleccionar impresora térmica'),
          content: SizedBox(width: 420, child: ListView.builder(shrinkWrap: true, itemCount: printers.length, itemBuilder: (_, int index) {
            final BluetoothInfo printer = printers[index];
            return ListTile(leading: const Icon(Icons.print_outlined), title: Text(printer.name.isEmpty ? 'Impresora Bluetooth' : printer.name), subtitle: Text(printer.macAdress), onTap: () => Navigator.pop(dialogContext, printer));
          })),
          actions: <Widget>[TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cancelar'))],
        ),
      );
      if (selected == null) return;
      if (!await PrintBluetoothThermal.connect(macPrinterAddress: selected.macAdress)) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo conectar con la impresora.')));
        return;
      }
      final CapabilityProfile profile = await CapabilityProfile.load();
      final Generator generator = Generator(PaperSize.mm58, profile);
      final List<int> bytes = <int>[];
      bytes.addAll(generator.text('Billares Don Miguel', styles: const PosStyles(align: PosAlign.center, bold: true, height: PosTextSize.size2, width: PosTextSize.size2)));
      bytes.addAll(generator.text('Mesa ${table.number}', styles: const PosStyles(align: PosAlign.center, bold: true)));
      bytes.addAll(generator.hr());
      bytes.addAll(generator.text('Hora de inicio: ${clock(table.start!)}'));
      bytes.addAll(generator.text('Hora finalizada: ${clock(table.end!)}'));
      bytes.addAll(generator.text('Tiempo jugado: ${duration(table.end!.difference(table.start!).inSeconds)}'));
      bytes.addAll(generator.text('Tarifa: ${money(table.rate)} / hora'));
      bytes.addAll(generator.hr());
      bytes.addAll(generator.text('MONTO A PAGAR', styles: const PosStyles(align: PosAlign.center, bold: true)));
      bytes.addAll(generator.text(money(table.amount), styles: const PosStyles(align: PosAlign.center, bold: true, height: PosTextSize.size2, width: PosTextSize.size2)));
      bytes.addAll(generator.feed(3));
      bytes.addAll(generator.cut());
      final bool printed = await PrintBluetoothThermal.writeBytes(bytes);
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(printed ? 'Recibo enviado a la impresora.' : 'La impresora no aceptó el recibo.')));
      await PrintBluetoothThermal.disconnect;
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo imprimir el recibo.')));
    }
  }

'''
    source = source.replace(marker, printer_method + marker, 1)

# Automatically offer printing when a finished table is collected centrally.
collect_marker = "  Future<void> collect(BillTable table) async {\n"
collect_replacement = "  Future<void> collect(BillTable table) async {\n    if (table.start != null && table.end != null && table.amount > 0) {\n      await printReceipt(table);\n    }\n"
if collect_marker not in source:
    raise SystemExit('1.2.8 FAILED: collect() signature not found')
if collect_replacement not in source:
    source = source.replace(collect_marker, collect_replacement, 1)

# Required tariff markers and total marker.
for rate in ('120', '100', '70'):
    if rate not in source:
        raise SystemExit(f'1.2.8 FAILED: tarifa {rate} missing')
if 'MONTO A PAGAR' not in source:
    raise SystemExit('1.2.8 FAILED: total marker missing')

TARGET.write_text(source)
print('OK: 1.2.8 generado limpiamente desde la base 1.2.7; sin parche de tarjeta administrativa')
