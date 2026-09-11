from pathlib import Path
import base64
import re
import subprocess

ROOT = Path('.')
MAIN = ROOT / 'lib/main.dart'
TEMPLATE = ROOT / 'cloud-tv/public/index.html'
LOGO = ROOT / 'assets/tv-logo.webp'
PUBSPEC = ROOT / 'pubspec.yaml'

if not MAIN.is_file() or not TEMPLATE.is_file() or not LOGO.is_file():
    raise SystemExit('ERROR: faltan archivos base de la interfaz TV o el logo real')

# Mantener el logo real sin deformarlo ni convertirlo en un data URI.
# La TV lo recibirá desde el mismo servidor LAN del CENTRAL como archivo WebP.
html = TEMPLATE.read_text(encoding='utf-8')
if 'src="/tv-logo.webp"' not in html:
    raise SystemExit('ERROR: cloud-tv/public/index.html no contiene /tv-logo.webp')
html64 = base64.b64encode(html.encode('utf-8')).decode('ascii')

source = MAIN.read_text(encoding='utf-8')
getter_pattern = r'String\s+get\s+tvHtml\s*=>.*?;\s*(?=Map\s*<\s*String\s*,\s*dynamic\s*>\s+stateMap)'
replacement = "String get tvHtml => utf8.decode(base64Decode('" + html64 + "'));\n\n"
source, getter_count = re.subn(getter_pattern, replacement, source, count=1, flags=re.S)
if getter_count != 1:
    raise SystemExit('ERROR: no se pudo regenerar tvHtml correctamente para 1.2.9+129')

# Servir el archivo físico desde el CENTRAL. Esto evita depender de data:image/webp;base64 en la TV.
endpoint = '''    if (request.uri.path == '/tv-logo.webp') {
      try {
        final ByteData logo = await rootBundle.load('assets/tv-logo.webp');
        response.headers.contentType = ContentType('image', 'webp');
        response.headers.contentLength = logo.lengthInBytes;
        response.add(logo.buffer.asUint8List());
      } catch (_) {
        response.statusCode = HttpStatus.notFound;
      }
      await response.close();
      return;
    }
'''
marker = "    if (request.uri.path == '/health') {"
if "request.uri.path == '/tv-logo.webp'" not in source:
    if marker not in source:
        raise SystemExit('ERROR: no se encontró el punto de inserción del endpoint /tv-logo.webp')
    source = source.replace(marker, endpoint + marker, 1)

# Asegurar que Flutter empaquete el logo real dentro del APK.
pub = PUBSPEC.read_text(encoding='utf-8')
if '  assets:\n    - assets/tv-logo.webp\n' not in pub:
    marker_pub = '  uses-material-design: true\n'
    if marker_pub not in pub:
        raise SystemExit('ERROR: no se encontró la sección flutter de pubspec.yaml')
    pub = pub.replace(marker_pub, marker_pub + '  assets:\n    - assets/tv-logo.webp\n', 1)
    PUBSPEC.write_text(pub, encoding='utf-8')

source = re.sub(r"const String appVersion = '[^']+';", "const String appVersion = '1.2.9+129';", source, count=1)
MAIN.write_text(source, encoding='utf-8')
subprocess.run(['dart', 'format', 'lib/main.dart'], check=True)

subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
subprocess.run(['git', 'config', 'user.email', '41898282+anparamo25-sketch@users.noreply.github.com'], check=True)
subprocess.run(['git', 'add', 'lib/main.dart', 'pubspec.yaml'], check=True)
if subprocess.run(['git', 'diff', '--cached', '--quiet']).returncode != 0:
    subprocess.run(['git', 'commit', '-m', 'fix: servir logo TV real desde el servidor LAN [skip ci]'], check=True)
    subprocess.run(['git', 'push', 'origin', 'HEAD:main'], check=True)

print('OK: fuente TV 1.2.9+129 corregida; logo real servido como /tv-logo.webp y empaquetado en el APK')
