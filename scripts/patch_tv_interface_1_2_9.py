from pathlib import Path
import base64
import re
import subprocess

ROOT = Path('.')
MAIN = ROOT / 'lib/main.dart'
TEMPLATE = ROOT / 'cloud-tv/public/index.html'
LOGO = ROOT / 'assets/tv-logo.webp'

html = TEMPLATE.read_text(encoding='utf-8')
logo64 = base64.b64encode(LOGO.read_bytes()).decode('ascii')
html = html.replace('src="/tv-logo.webp"', f'src="data:image/webp;base64,{logo64}"')
html64 = base64.b64encode(html.encode('utf-8')).decode('ascii')

source = MAIN.read_text(encoding='utf-8')
getter_pattern = r'String\s+get\s+tvHtml\s*=>.*?;\s*(?=Map\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap)'
replacement = "String get tvHtml => utf8.decode(base64Decode('" + html64 + "'));\n\n"
source, getter_count = re.subn(getter_pattern, replacement, source, count=1, flags=re.S)
if getter_count != 1:
    raise SystemExit('ERROR: no se pudo generar tvHtml correctamente para 1.2.9+129')

source = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.9+129';", source, count=1)
MAIN.write_text(source, encoding='utf-8')
subprocess.run(['dart', 'format', 'lib/main.dart'], check=True)
subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
subprocess.run(['git', 'config', 'user.email', '41898282+anparamo25-sketch@users.noreply.github.com'], check=True)
subprocess.run(['git', 'add', 'lib/main.dart'], check=True)
if subprocess.run(['git', 'diff', '--cached', '--quiet']).returncode != 0:
    subprocess.run(['git', 'commit', '-m', 'fix: sincronizar logo TV real en fuente 1.2.9+129 [skip ci]'], check=True)
    subprocess.run(['git', 'push', 'origin', 'HEAD:main'], check=True)

print('OK: fuente TV 1.2.9+129 generada con el logo real embebido y proporcional')
