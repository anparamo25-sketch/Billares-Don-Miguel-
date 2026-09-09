from pathlib import Path
import re
import json

TARGET = Path('lib/main.dart')
s = TARGET.read_text()

# The historical preparation can reintroduce its old triple-quoted TV getter.
# Convert that getter one last time, after ALL other repair scripts have run.
pattern = re.compile(r'(?ms)^  String\s+get\s+tvHtml\s*\{(?P<body>.*?)^  \}\s*$')
matches = list(pattern.finditer(s))
old = [m for m in matches if 'return r"""' in m.group('body') or "return r'''" in m.group('body')]
if old:
    if len(old) != 1:
        raise SystemExit(f'TV FINAL FAILED: hay {len(old)} getters TV heredados')
    m = old[0]
    body = m.group('body')
    q = '"""' if 'return r"""' in body else "'''"
    start = body.find(q) + len(q)
    end = body.rfind(q)
    if start < len(q) or end < start:
        raise SystemExit('TV FINAL FAILED: no se pudo extraer HTML heredado')
    html = body[start:end]
    replacement = '  String get tvHtml => ' + json.dumps(html, ensure_ascii=False) + ';\n'
    s = s[:m.start()] + replacement + s[m.end():]

# Remove any duplicate expression getters, keeping the first one.
def strip_expression_duplicates(source: str) -> str:
    rx = re.compile(r'(?m)^  String\s+get\s+tvHtml\s*=>[^;]*;\s*\n?')
    found = list(rx.finditer(source))
    if len(found) <= 1:
        return source
    keep = found[0]
    out = source[:keep.end()]
    cursor = keep.end()
    for m in found[1:]:
        out += source[cursor:m.start()]
        cursor = m.end()
    out += source[cursor:]
    return out

s = strip_expression_duplicates(s)

if len(re.findall(r'(?m)^  String\s+get\s+tvHtml\s*=>', s)) != 1:
    raise SystemExit('TV FINAL FAILED: tvHtml no quedó exactamente una vez')
if 'return r"""' in s or "return r'''" in s:
    raise SystemExit('TV FINAL FAILED: todavía existe TV con triple comillas')

TARGET.write_text(s)
print('OK: seguridad final TV aplicada; getter único y sin triple comillas')
