from pathlib import Path
import re

p = Path('lib/main.dart')
s = p.read_text(encoding='utf-8')
if "const String appVersion = '1.3.0+130';" in s:
    raise SystemExit(0)

s = s.replace(
    "import 'package:shared_preferences/shared_preferences.dart';",
    "import 'package:shared_preferences/shared_preferences.dart';\nimport 'package:share_plus/share_plus.dart';",
)
s = s.replace(
    "import 'receipt_preview_page.dart';",
    "import 'receipt_preview_page.dart';\nimport 'weekly_report.dart';",
)
s = s.replace("const String appVersion = '1.2.9+129';", "const String appVersion = '1.3.0+130';")
s = s.replace("const Duration(days: 7)", "const Duration(days: 30)")
s = s.replace("'Últimos 7 días'", "'Últimos 30 días'")
s = s.replace("No hay movimientos en los últimos 7 días.", "No hay movimientos en los últimos 30 días.")

old = """    await saveWorkday();\n  }\n\n  Future<void> saveTables() async {"""
new = """    await saveWorkday();\n    final String? printError = await printWorkdaySummary(\n      games: workdayGames,\n      generated: workdayGenerated,\n      cash: workdayCashClose,\n    );\n    if (printError != null && mounted) {\n      ScaffoldMessenger.of(context).showSnackBar(\n        SnackBar(content: Text(printError)),\n      );\n    }\n  }\n\n  Future<void> saveTables() async {"""
if old not in s:
    raise SystemExit('closeWorkday anchor missing')
s = s.replace(old, new, 1)

anchor = "  Future<void> collect(BillTable table) async {"
method = r'''  Future<String?> printWorkdaySummary({
    required int games,
    required double generated,
    required double cash,
  }) async {
    try {
      final List<BluetoothInfo> printers =
          await PrintBluetoothThermal.pairedBluetooths;
      if (printers.isEmpty) {
        return 'No hay impresora térmica emparejada para imprimir el cierre.';
      }
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      final String? savedMac = prefs.getString('thermal_printer_mac');
      if (savedMac == null || savedMac.isEmpty) {
        return 'Configura primero la impresora térmica para imprimir el cierre.';
      }
      BluetoothInfo? printer;
      for (final BluetoothInfo item in printers) {
        if (item.macAdress == savedMac) {
          printer = item;
          break;
        }
      }
      if (printer == null) {
        return 'La impresora guardada ya no está emparejada.';
      }
      final bool connected = await PrintBluetoothThermal.connect(
        macPrinterAddress: printer.macAdress,
      );
      if (!connected) return 'No se pudo conectar con la impresora para el cierre.';
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
        'CIERRE DE JORNADA',
        styles: const PosStyles(align: PosAlign.center, bold: true),
      ));
      bytes.addAll(generator.hr());
      bytes.addAll(generator.text('Fecha: ${date(DateTime.now())}'));
      bytes.addAll(generator.text('Hora: ${clock(DateTime.now())}'));
      bytes.addAll(generator.text('Partidas jugadas: $games'));
      bytes.addAll(generator.text('Total generado: ${totalMoney(generated)}'));
      bytes.addAll(generator.text('Efectivo físico: ${totalMoney(cash)}'));
      bytes.addAll(generator.hr());
      bytes.addAll(generator.feed(3));
      bytes.addAll(generator.cut());
      final bool printed = await PrintBluetoothThermal.writeBytes(bytes);
      return printed ? null : 'La impresora no aceptó el resumen de cierre.';
    } catch (_) {
      return 'No se pudo imprimir el resumen de cierre.';
    }
  }

'''
if anchor not in s:
    raise SystemExit('collect anchor missing')
s = s.replace(anchor, method + anchor, 1)

pattern = r"  Future<void> downloadAndInstall\(String url\) async \{.*?\n  \}\n\n  Future<void> changePassword\(\) async \{"
replacement = r'''  Future<void> downloadAndInstall(String url) async {
    HttpClient? client;
    try {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Descargando actualización...')),
      );
      final List<Directory>? caches = await getExternalCacheDirectories();
      final Directory cache =
          caches != null && caches.isNotEmpty
              ? caches.first
              : await getTemporaryDirectory();
      final String path = '${cache.path}/billares-don-miguel-update.apk';
      final File file = File(path);
      if (await file.exists()) await file.delete();
      client = HttpClient()..connectionTimeout = const Duration(seconds: 30);
      client.userAgent = 'Billares-Don-Miguel/1.3.0';
      final HttpClientRequest request = await client.getUrl(Uri.parse(url));
      request.headers.set(HttpHeaders.cacheControlHeader, 'no-cache');
      final HttpClientResponse response = await request.close();
      if (response.statusCode != HttpStatus.ok) {
        throw HttpException('HTTP ${response.statusCode}');
      }
      final IOSink sink = file.openWrite();
      await response.pipe(sink);
      await sink.flush();
      await sink.close();
      if (!await file.exists() || await file.length() < 1024 * 1024) {
        throw const HttpException('APK inválido o incompleto');
      }
      final bool installPermission =
          await ApkInstall().onCheckInstallApkPermission();
      if (!installPermission) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                'Android bloqueó la instalación. Activa "Instalar aplicaciones desconocidas" para Billares Don Miguel y vuelve a intentarlo.',
              ),
            ),
          );
        }
        return;
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Abriendo instalador de Android...')),
        );
      }
      final bool installStarted = await ApkInstall().onInstallApk(file.path);
      if (!installStarted && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Android no inició el instalador. Vuelve a pulsar Actualizar.',
            ),
          ),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'No se pudo descargar o iniciar la instalación de la actualización.',
            ),
          ),
        );
      }
    } finally {
      client?.close(force: true);
    }
  }

  Future<void> changePassword() async {'''
s, count = re.subn(pattern, replacement, s, flags=re.S)
if count != 1:
    raise SystemExit(f'installer replacement count {count}')

anchor = "  Widget historyPage() {"
method = r'''  Future<void> downloadWeeklyPdf() async {
    try {
      final DateTime now = DateTime.now();
      final DateTime weekStart = DateTime(
        now.year,
        now.month,
        now.day,
      ).subtract(Duration(days: now.weekday - 1));
      final DateTime weekEnd = weekStart.add(const Duration(days: 6));
      final List<WeeklyReportDay> days = <WeeklyReportDay>[];
      for (int i = 0; i < 7; i++) {
        final DateTime day = weekStart.add(Duration(days: i));
        final List<HistoryEntry> entries = history.where(
          (HistoryEntry e) =>
              e.workDate.year == day.year &&
              e.workDate.month == day.month &&
              e.workDate.day == day.day,
        ).toList();
        days.add(
          WeeklyReportDay(
            date: day,
            sessions: entries.length,
            amount: entries.fold<double>(
              0,
              (double total, HistoryEntry e) => total + e.amount,
            ),
          ),
        );
      }
      final Directory directory = await getApplicationDocumentsDirectory();
      final File file = await WeeklyReportBuilder.writePdf(
        path: '${directory.path}/Billares-Don-Miguel-reporte-semanal.pdf',
        start: weekStart,
        end: weekEnd,
        days: days,
      );
      await Share.shareXFiles(
        <XFile>[XFile(file.path)],
        subject: 'Billares Don Miguel - reporte semanal',
        text: 'Reporte semanal de Billares Don Miguel.',
        fileNameOverrides: <String>['Billares-Don-Miguel-reporte-semanal.pdf'],
      );
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No se pudo generar el PDF semanal.')),
        );
      }
    }
  }

'''
if anchor not in s:
    raise SystemExit('history anchor missing')
s = s.replace(anchor, method + anchor, 1)

old = """        ),\n        if (keys.isEmpty)"""
new = """        ),\n        const SizedBox(height: 10),\n        Align(\n          alignment: Alignment.centerLeft,\n          child: FilledButton.icon(\n            onPressed: downloadWeeklyPdf,\n            icon: const Icon(Icons.picture_as_pdf_outlined),\n            label: const Text('Descargar PDF semanal'),\n          ),\n        ),\n        if (keys.isEmpty)"""
if old not in s:
    raise SystemExit('history button anchor missing')
s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
