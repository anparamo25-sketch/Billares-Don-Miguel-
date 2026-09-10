from pathlib import Path
import json
import re

TARGET = Path('lib/main.dart')
source = TARGET.read_text()

# Version and printer dependencies.
source = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.8+128';", source, count=1)
if "package:print_bluetooth_thermal_plus/print_bluetooth_thermal.dart" not in source:
    source = source.replace(
        "import 'package:path_provider/path_provider.dart';",
        "import 'package:path_provider/path_provider.dart';\nimport 'package:print_bluetooth_thermal_plus/print_bluetooth_thermal.dart';\nimport 'package:esc_pos_utils_plus/esc_pos_utils_plus.dart';",
        1,
    )

# Build the approved TV HTML deterministically. This is the same visual language
# published under cloud-tv/public/index.html and is also served by the local
# central tablet at /tv. The five-card distribution, colors and logo are preserved.
html = r'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate, max-age=0"><meta http-equiv="Pragma" content="no-cache"><meta http-equiv="Expires" content="0"><title>Billares Don Miguel - TV</title><style>*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#05070b;color:#fff;font-family:Arial,sans-serif}.wrap{width:100%;height:100vh;padding:0 20px 16px;display:flex;flex-direction:column;overflow:hidden}header{height:112px;flex:0 0 112px;padding:12px 4px;background:#fff;border-bottom:3px solid #1557c0;display:grid;grid-template-columns:1fr auto 1fr;align-items:center}.brandLogo{justify-self:start;display:flex;align-items:center;gap:10px;color:#1557c0;font-weight:900}.logoSvg{width:68px;height:68px;display:block;flex:none}.word{font-size:18px;letter-spacing:.5px}.brandTitle{justify-self:center}.brandTitle h1{margin:0;font-size:clamp(32px,4.5vw,54px);line-height:1;color:#1557c0;text-align:center;text-shadow:0 2px 3px rgba(0,0,0,.18)}.liveBox{justify-self:end;text-align:center;color:#1557c0}.clock{font-size:clamp(18px,2vw,28px);font-weight:900;line-height:1.1}.live{font-size:clamp(16px,1.8vw,25px);font-weight:900;margin-top:5px}.grid{width:100%;flex:1;min-height:0;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:16px;padding:16px 0 0;overflow:hidden}.card{height:100%;min-height:0;border-radius:18px;padding:18px;border:3px solid #64748b;display:flex;flex-direction:column;box-shadow:0 8px 18px rgba(0,0,0,.25);overflow:hidden}.green{background:#103b22;border-color:#22c55e}.red{background:#511b1b;border-color:#ef4444}.yellow{background:#56490a;border-color:#eab308}.num{font-size:clamp(24px,2.7vw,38px);font-weight:900;line-height:1.05}.status{font-size:clamp(18px,2vw,27px);font-weight:900;margin:7px 0 12px;line-height:1.05}.green .status{color:#4ade80}.red .status{color:#f87171}.yellow .status{color:#fde047}.rate{font-size:clamp(17px,1.7vw,24px);font-weight:900;margin-bottom:8px;line-height:1.1}.line{font-size:clamp(18px,1.7vw,24px);font-weight:700;line-height:1.3;margin:5px 0}.pay{margin-top:auto;padding-top:11px;border-top:2px solid rgba(255,255,255,.25)}.payLabel{font-size:clamp(15px,1.5vw,21px);font-weight:900;letter-spacing:.5px}.money{font-size:clamp(30px,3.2vw,46px);font-weight:900;margin-top:3px;line-height:1.05}@media(max-height:700px){header{height:92px;flex-basis:92px}.wrap{padding:0 14px 10px}.grid{gap:10px;padding-top:10px}.card{padding:13px;border-radius:14px}.status{margin:5px 0 8px}.line{margin:3px 0;font-size:clamp(16px,1.6vw,22px)}.rate{margin-bottom:5px}.logoSvg{width:56px;height:56px}.word{font-size:15px}}@media(max-width:1200px) and (min-height:701px){.wrap{padding-left:14px;padding-right:14px}.grid{gap:10px}.card{padding:14px}.line{font-size:clamp(16px,1.6vw,22px)}}</style></head><body><main class="wrap"><header><div class="brandLogo"><svg class="logoSvg" viewBox="0 0 100 100" aria-label="Logo Billares Don Miguel" role="img"><circle cx="50" cy="50" r="45" fill="#1557c0"/><circle cx="50" cy="50" r="37" fill="#fff"/><path d="M29 66V34h15c10 0 16 5 16 12 0 4-2 7-5 9 5 2 8 5 8 10 0 9-7 15-19 15H29zm10-20h5c4 0 6-1 6-4 0-3-2-4-6-4h-5v8zm0 15h8c4 0 7-2 7-5s-3-5-7-5h-8v10z" fill="#1557c0" transform="translate(0,-5)"/><path d="M18 76h64" stroke="#1557c0" stroke-width="5" stroke-linecap="round"/><circle cx="24" cy="76" r="5" fill="#1557c0"/><circle cx="76" cy="76" r="5" fill="#1557c0"/></svg><div class="word">BILLARES</div></div><div class="brandTitle"><h1>Billares Don Miguel</h1></div><div class="liveBox"><div id="clock" class="clock">--:-- PM</div><div class="live">🟢 EN VIVO</div></div></header><section id="tables" class="grid"></section></main><script>const rates={1:120,2:120,3:100,4:100,5:70};function safe(v){return v==null||v===''?'—':String(v)}function money(v){return 'C$ '+Number(v||0).toFixed(2)}function clockValue(v){if(!v)return '—';var d=new Date(v);if(isNaN(d.getTime()))return String(v);return d.toLocaleTimeString('es-NI',{hour:'2-digit',minute:'2-digit',hour12:true})}function statusName(v){return v==='playing'?'En juego':v==='pending'?'Pendiente de cobro':v==='available'?'Disponible':safe(v)}function render(d){document.getElementById('clock').textContent=d.time||new Date().toLocaleTimeString('es-NI',{hour:'2-digit',minute:'2-digit',hour12:true});var tables=d.tables||[];document.getElementById('tables').innerHTML=[1,2,3,4,5].map(function(i){var t=tables.find(function(x){return Number(x.number)===i})||{number:i,status:'available',rate:rates[i],amount:0};var s=statusName(t.status);var c=s==='En juego'?'red':s==='Pendiente de cobro'?'yellow':'green';return '<article class="card '+c+'"><div class="num">Mesa '+i+'</div><div class="status">'+safe(s)+'</div><div class="rate">Tarifa por hora: '+money(t.rate??rates[i])+'</div><div class="line"><b>Hora de inicio:</b> '+(t.start&&t.start.indexOf('T')>0?clockValue(t.start):safe(t.start))+'</div><div class="line"><b>Tiempo jugado:</b> '+safe(t.elapsed||'00:00:00')+'</div><div class="line"><b>Hora finalizada:</b> '+(t.end&&t.end.indexOf('T')>0?clockValue(t.end):safe(t.end))+'</div><div class="pay"><div class="payLabel">MONTO A PAGAR</div><div class="money">'+money(t.amount)+'</div></div></article>'}).join('')}async function tick(){try{var r=await fetch('/api/state?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);render(await r.json())}catch(e){}}function updateClock(){var el=document.getElementById('clock');if(el)el.textContent=new Date().toLocaleTimeString('es-NI',{hour:'2-digit',minute:'2-digit',hour12:true})}render({tables:[]});updateClock();tick();setInterval(tick,1000);setInterval(updateClock,1000);</script></body></html>'''

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
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No se pudo imprimir el recibo.')));
    }
  }

'''
    source = source.replace(marker, printer_method + marker, 1)

collect_marker = "  Future<void> collect(BillTable table) async {\n"
collect_replacement = "  Future<void> collect(BillTable table) async {\n    if (table.start != null && table.end != null && table.amount > 0) {\n      await printReceipt(table);\n    }\n"
if collect_marker not in source:
    raise SystemExit('1.2.8 FAILED: collect() signature not found')
if collect_replacement not in source:
    source = source.replace(collect_marker, collect_replacement, 1)

for rate in ('120', '100', '70'):
    if rate not in source:
        raise SystemExit(f'1.2.8 FAILED: tarifa {rate} missing')
if 'MONTO A PAGAR' not in source:
    raise SystemExit('1.2.8 FAILED: total marker missing')

TARGET.write_text(source)
print('OK: 1.2.8 generado con la interfaz TV aprobada, conexión LAN /tv y actualización /api/state')
