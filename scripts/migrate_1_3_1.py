from pathlib import Path
import re

MAIN = Path('lib/main.dart')
PUBSPEC = Path('pubspec.yaml')
UPDATE = Path('update.json')

TARGET_VERSION = '1.3.1+131'
OLD_VERSION = '1.3.0+130'

main = MAIN.read_text(encoding='utf-8')
pubspec = PUBSPEC.read_text(encoding='utf-8')
update = UPDATE.read_text(encoding='utf-8')

# The repository may already contain the final v1.3.1 thermal implementation.
# In that case this script validates it instead of trying to apply the same
# source transformation again.
if f"const String appVersion = '{OLD_VERSION}';" in main:
    main = main.replace(
        f"const String appVersion = '{OLD_VERSION}';",
        f"const String appVersion = '{TARGET_VERSION}';",
        1,
    )
elif f"const String appVersion = '{TARGET_VERSION}';" not in main:
    raise SystemExit('No se encontró una versión compatible en lib/main.dart.')


def compact_block(source: str, label: str) -> str:
    start_match = re.search(
        rf"Future<String\?> {re.escape(label)}\([^{{]*\)\s*\{{", source
    )
    if not start_match:
        raise SystemExit(f'{label}: no se encontró la función de impresión.')

    end_match = re.search(r"\n\s*Future<String\?>?\s+print|\n\s*Future<void>\s+collect\(", source[start_match.end():])
    if not end_match:
        raise SystemExit(f'{label}: no se encontró el final de la función.')

    end = start_match.end() + end_match.start()
    block = source[start_match.start():end]

    # Keep the existing 58mm roll. Its printable area is the compact receipt
    # width used by the target 48mm thermal printers.
    block = re.sub(
        r"Generator\(\s*PaperSize\.mm58\s*,\s*profile\s*\)",
        "Generator(PaperSize.mm58, profile, spaceBetweenRows: 0)",
        block,
    )
    if 'Generator(PaperSize.mm58, profile, spaceBetweenRows: 0)' not in block:
        raise SystemExit(f'{label}: no se encontró el Generator de 58mm.')

    marker = 'final List<int> bytes = <int>[];'
    if marker not in block:
        raise SystemExit(f'{label}: no se encontró el buffer de impresión.')
    if 'bytes.addAll(generator.setGlobalFont(PosFontType.fontB));' not in block:
        block = block.replace(
            marker,
            marker + '\n      bytes.addAll(generator.setGlobalFont(PosFontType.fontB));',
            1,
        )

    block = block.replace('height: PosTextSize.size2,', 'height: PosTextSize.size1,')
    block = block.replace('width: PosTextSize.size2,', 'width: PosTextSize.size1,')
    block = block.replace('generator.feed(3)', 'generator.feed(1)')

    if 'setGlobalFont(PosFontType.fontB)' not in block:
        raise SystemExit(f'{label}: falta la fuente compacta fontB.')
    if 'generator.feed(3)' in block:
        raise SystemExit(f'{label}: todavía usa feed(3).')
    if 'PosTextSize.size2' in block:
        raise SystemExit(f'{label}: todavía contiene texto size2.')

    return source[:start_match.start()] + block + source[end:]


main = compact_block(main, 'printReceipt')
main = compact_block(main, 'printWorkdaySummary')

# Version metadata is part of the release, not a temporary build workaround.
pubspec = pubspec.replace(f'version: {OLD_VERSION}', f'version: {TARGET_VERSION}', 1)
if f'version: {TARGET_VERSION}' not in pubspec:
    raise SystemExit('No se encontró una versión compatible en pubspec.yaml.')

update = update.replace(f'"version":"{OLD_VERSION}"', f'"version":"{TARGET_VERSION}"', 1)
if f'"version":"{TARGET_VERSION}"' not in update:
    raise SystemExit('No se encontró una versión compatible en update.json.')

MAIN.write_text(main, encoding='utf-8')
PUBSPEC.write_text(pubspec, encoding='utf-8')
UPDATE.write_text(update, encoding='utf-8')

print('THERMAL_48MM_COMPACT_LAYOUT=OK')
print(f'VERSION={TARGET_VERSION}')
