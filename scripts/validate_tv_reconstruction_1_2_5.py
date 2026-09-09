from pathlib import Path
import re

s=Path('lib/main.dart').read_text()
# Validar la firma Dart directamente: no depende de indentacion ni de enmascarado.
matches=re.findall(r'(?m)^\s*Future\s*<\s*void\s*>\s+showTvConnection\s*\(\s*\)\s+async\s*\{',s)
if len(matches)!=1:
    raise SystemExit(f'VALIDACION TV FAILED: showTvConnection={len(matches)}')
if 'showDialog<void>' not in s:
    raise SystemExit('VALIDACION TV FAILED: dialogo TV ausente')
print('OK: showTvConnection reconocida estructuralmente')
