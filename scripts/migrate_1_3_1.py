from pathlib import Path

main_path = Path('lib/main.dart')
pubspec_path = Path('pubspec.yaml')
update_path = Path('update.json')

s = main_path.read_text(encoding='utf-8')

if "const String appVersion = '1.3.0+130';" in s:
    s = s.replace(
        "const String appVersion = '1.3.0+130';",
        "const String appVersion = '1.3.1+131';",
        1,
    )
elif "const String appVersion = '1.3.1+131';" not in s:
    raise SystemExit('No se encontró la versión base 1.3.0+130 en lib/main.dart.')

start_marker = 'Future<String?> printReceipt(BillTable table) async {'
end_marker = 'Future<void> collect(BillTable table) async {'
if start_marker not in s or end_marker not in s:
    raise SystemExit('No se encontró el bloque de impresión de recibo.')
start = s.index(start_marker)
end = s.index(end_marker, start)
receipt = s[start:end]

summary_marker = 'Future<String?> printWorkdaySummary('
summary_end_marker = 'Future<void> collect(BillTable table) async {'
if summary_marker not in s:
    raise SystemExit('No se encontró el bloque de impresión del cierre.')
summary_start = s.index(summary_marker)
summary_end = s.index(summary_end_marker, summary_start)
summary = s[summary_start:summary_end]

def compact_print_block(block: str, label: str) -> str:
    if block.count('Generator(PaperSize.mm58, profile)') != 1:
        raise SystemExit(f'{label}: se esperaba exactamente un Generator(PaperSize.mm58, profile).')
    block = block.replace(
        'Generator(PaperSize.mm58, profile)',
        'Generator(PaperSize.mm58, profile, spaceBetweenRows: 0)',
        1,
    )
    marker = 'final List<int> bytes = <int>[];'
    if block.count(marker) != 1:
        raise SystemExit(f'{label}: no se encontró el buffer de impresión esperado.')
    block = block.replace(
        marker,
        marker + '\n      bytes.addAll(generator.setGlobalFont(PosFontType.fontB));',
        1,
    )
    block = block.replace('height: PosTextSize.size2,', 'height: PosTextSize.size1,')
    block = block.replace('width: PosTextSize.size2,', 'width: PosTextSize.size1,')
    block = block.replace('generator.feed(3)', 'generator.feed(1)')
    return block

receipt = compact_print_block(receipt, 'printReceipt')
summary = compact_print_block(summary, 'printWorkdaySummary')

s = s[:start] + receipt + s[end:]
summary_start = s.index(summary_marker)
summary_end = s.index(summary_end_marker, summary_start)
s = s[:summary_start] + summary + s[summary_end:]

main_path.write_text(s, encoding='utf-8')

pubspec = pubspec_path.read_text(encoding='utf-8')
if 'version: 1.3.0+130' in pubspec:
    pubspec = pubspec.replace('version: 1.3.0+130', 'version: 1.3.1+131', 1)
elif 'version: 1.3.1+131' not in pubspec:
    raise SystemExit('No se encontró la versión base 1.3.0+130 en pubspec.yaml.')
pubspec_path.write_text(pubspec, encoding='utf-8')

update = update_path.read_text(encoding='utf-8')
update = update.replace('"version":"1.3.0+130"', '"version":"1.3.1+131"', 1)
update_path.write_text(update, encoding='utf-8')

# Contract checks: only the thermal-print blocks were changed for layout.
for label, block in (('printReceipt', receipt), ('printWorkdaySummary', summary)):
    if 'spaceBetweenRows: 0' not in block:
        raise SystemExit(f'{label}: falta spaceBetweenRows: 0.')
    if 'setGlobalFont(PosFontType.fontB)' not in block:
        raise SystemExit(f'{label}: falta la fuente compacta fontB.')
    if 'generator.feed(3)' in block:
        raise SystemExit(f'{label}: todavía usa feed(3).')
    if 'PosTextSize.size2' in block:
        raise SystemExit(f'{label}: todavía contiene texto size2.')

print('THERMAL_48MM_COMPACT_LAYOUT=OK')
print('VERSION=1.3.1+131')
