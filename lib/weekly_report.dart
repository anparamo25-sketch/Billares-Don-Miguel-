import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

class WeeklyReportDay {
  const WeeklyReportDay({
    required this.date,
    required this.sessions,
    required this.amount,
  });

  final DateTime date;
  final int sessions;
  final double amount;
}

class WeeklyReportBuilder {
  static Future<File> writePdf({
    required String path,
    required DateTime start,
    required DateTime end,
    required List<WeeklyReportDay> days,
  }) async {
    final List<String> lines = <String>[
      'Billares Don Miguel',
      'Reporte semanal',
      'Semana: ${_date(start)} - ${_date(end)}',
      '',
      'Fecha        Sesiones        Generado',
      '----------------------------------------',
      ...days.map(
        (WeeklyReportDay day) =>
            '${_date(day.date).padRight(12)} ${day.sessions.toString().padLeft(8)}        C\$${day.amount.round()}',
      ),
      '----------------------------------------',
      'Total sesiones: ${days.fold<int>(0, (int n, WeeklyReportDay d) => n + d.sessions)}',
      'Total generado: C\$${days.fold<double>(0, (double n, WeeklyReportDay d) => n + d.amount).round()}',
    ];

    final Uint8List bytes = _buildPdf(lines);
    final File file = File(path);
    await file.parent.create(recursive: true);
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  static String _date(DateTime value) =>
      '${value.day.toString().padLeft(2, '0')}/${value.month.toString().padLeft(2, '0')}/${value.year}';

  static Uint8List _buildPdf(List<String> lines) {
    final List<int> content = <int>[];
    void addText(String value) => content.addAll(utf8.encode(value));
    addText('BT\n/F1 11 Tf\n50 790 Td\n');
    for (int i = 0; i < lines.length; i++) {
      if (i > 0) addText('0 -16 Td\n');
      addText('(${_escape(lines[i])}) Tj\n');
    }
    addText('ET\n');

    final List<List<int>> objects = <List<int>>[
      utf8.encode('<< /Type /Catalog /Pages 2 0 R >>'),
      utf8.encode('<< /Type /Pages /Kids [3 0 R] /Count 1 >>'),
      utf8.encode('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>'),
      utf8.encode('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'),
      utf8.encode('<< /Length ${content.length} >>\nstream\n${utf8.decode(content)}endstream'),
    ];

    final List<int> pdf = <int>[];
    pdf.addAll(utf8.encode('%PDF-1.4\n%\xE2\xE3\xCF\xD3\n'));
    final List<int> offsets = <int>[0];
    for (int i = 0; i < objects.length; i++) {
      offsets.add(pdf.length);
      pdf.addAll(utf8.encode('${i + 1} 0 obj\n'));
      pdf.addAll(objects[i]);
      pdf.addAll(utf8.encode('\nendobj\n'));
    }
    final int xref = pdf.length;
    pdf.addAll(utf8.encode('xref\n0 ${objects.length + 1}\n'));
    pdf.addAll(utf8.encode('0000000000 65535 f \n'));
    for (int i = 1; i < offsets.length; i++) {
      pdf.addAll(utf8.encode('${offsets[i].toString().padLeft(10, '0')} 00000 n \n'));
    }
    pdf.addAll(utf8.encode('trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n$xref\n%%EOF\n'));
    return Uint8List.fromList(pdf);
  }

  static String _escape(String value) =>
      value.replaceAll('\\', '\\\\').replaceAll('(', '\\(').replaceAll(')', '\\)');
}
