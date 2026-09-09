from pathlib import Path
import re
TARGET=Path('lib/main.dart'); source=TARGET.read_text(); normalized=re.sub(r'\s+',' ',source)
if 'http://billaresdonmiguel.local/tv' not in source: raise SystemExit('TV HOSTNAME FAILED: receptor TV canónico ausente')
if not re.search(r'\bFuture\s*<\s*void\s*>\s+startLanServer\s*\(\s*\)\s+async\s*\{',source): raise SystemExit('TV HOSTNAME FAILED: servidor LAN canónico ausente')
if 'HttpServer.bind(InternetAddress.anyIPv4, 80' not in normalized: raise SystemExit('TV HOSTNAME FAILED: servidor LAN no usa puerto 80')
print('OK: hostname y servidor LAN validados; sin modificaciones')
