from pathlib import Path
import re
import json

TARGET = Path('lib/main.dart')


def find_matching_brace(source: str, open_pos: int) -> int:
    depth = 0
    i = open_pos
    quote = None
    triple = False
    while i < len(source):
        if quote:
            token = quote * 3 if triple else quote
            if source.startswith(token, i):
                i += len(token)
                quote = None
                triple = False
                continue
            if source[i] == '\\' and not triple:
                i += 2
                continue
            i += 1
            continue
        if source.startswith("'''", i):
            quote, triple = "'", True
            i += 3
            continue
        if source.startswith('"""', i):
            quote, triple = '"', True
            i += 3
            continue
        if source[i] in ("'", '"'):
            quote = source[i]
            triple = False
            i += 1
            continue
        if source.startswith('//', i):
            end = source.find('\n', i + 2)
            i = len(source) if end < 0 else end + 1
            continue
        if source.startswith('/*', i):
            end = source.find('*/', i + 2)
            i = len(source) if end < 0 else end + 2
            continue
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise SystemExit('TV REPAIR FAILED: llaves sin cerrar')


def remove_function_definitions(source: str, names: tuple[str, ...]) -> str:
    """Remove complete Dart async function bodies by structure, not indentation."""
    pattern = re.compile(r'\bFuture\s*<\s*void\s*>\s+(' + '|'.join(map(re.escape, names)) + r')\s*\(\s*\)\s+async\s*\{')
    while True:
        match = pattern.search(source)
        if not match:
            return source
        open_pos = source.find('{', match.start(), match.end())
        end_pos = find_matching_brace(source, open_pos)
        source = source[:match.start()] + source[end_pos:]


def remove_tv_getters(source: str) -> str:
    """Remove every tvHtml getter, including legacy variants, structurally."""
    arrow = re.compile(r'(?m)^\s*String\s+get\s+tvHtml(?:Legacy\d+)?\s*=>[^;]*;\s*')
    source = arrow.sub('', source)
    block = re.compile(r'\bString\s+get\s+tvHtml(?:Legacy\d+)?\s*\{')
    while True:
        match = block.search(source)
        if not match:
            return source
        open_pos = source.find('{', match.start(), match.end())
        end_pos = find_matching_brace(source, open_pos)
        source = source[:match.start()] + source[end_pos:]


def insert_before(source: str, marker: str, text: str) -> str:
    pos = source.find(marker)
    if pos < 0:
        raise SystemExit(f'TV REPAIR FAILED: no se encontró marcador {marker}')
    return source[:pos] + text + source[pos:]


s = TARGET.read_text()
s = remove_function_definitions(s, ('showTvConnection', 'showTvConnectionLegacy1', 'showTvConnectionLegacy2', 'showTvConnectionLegacy3'))
s = remove_tv_getters(s)

show_tv = '''  Future<void> showTvConnection() async {
    const String url = 'http://billaresdonmiguel.local/tv';
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: const Text('Receptor exclusivo para TV'),
        content: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
            const Text('La TV mostrará solamente las mesas. El celular seguirá funcionando como administrador.'),
            const SizedBox(height: 14),
            const Text('Dirección:', style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            const SelectableText(url, style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            FilledButton.icon(onPressed: () async {
              await Clipboard.setData(const ClipboardData(text: url));
              if (dialogContext.mounted) ScaffoldMessenger.of(dialogContext).showSnackBar(const SnackBar(content: Text('Dirección copiada')));
            }, icon: const Icon(Icons.copy), label: const Text('Copiar dirección')),
            const SizedBox(height: 8),
            const Text('En la TV abre el navegador, escribe la dirección y presiona Enter. No uses Duplicar pantalla/Miracast.', style: TextStyle(fontSize: 12)),
          ]),
        ),
        actions: <Widget>[TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cerrar'))],
      ),
    );
  }
'''

html = '''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Billares Don Miguel - TV</title><style>*{box-sizing:border-box}body{margin:0;background:#05070b;color:#fff;font-family:Arial,sans-serif}header{padding:18px;text-align:center;background:#fff;border-bottom:3px solid #1557c0}h1{margin:0;font-size:clamp(28px,4vw,46px);color:#1557c0;text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff}.clock{margin-top:6px;font-size:clamp(18px,2vw,26px);font-weight:700;color:#123f91}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px;padding:22px;max-width:1800px;margin:auto}.card{border-radius:18px;padding:22px;background:#111827;border:3px solid #64748b;min-height:205px}.green{background:#103b22;border-color:#22c55e}.red{background:#511b1b;border-color:#ef4444}.yellow{background:#56490a;border-color:#eab308}.name{font-size:clamp(25px,3vw,38px);font-weight:900}.status{margin:10px 0;font-size:clamp(18px,2vw,25px);font-weight:800}.line{margin:8px 0;font-size:clamp(15px,1.6vw,20px)}.money{margin-top:14px;font-size:clamp(25px,2.7vw,36px);font-weight:900}.offline{position:fixed;right:12px;bottom:10px;background:#7f1d1d;padding:7px 12px;border-radius:10px;display:none}</style></head><body><header><h1>Billares Don Miguel</h1><div id="clock" class="clock">Conectando...</div></header><main id="grid" class="grid"></main><div id="offline" class="offline">Sin conexión con CENTRAL</div><script>function money(n){return 'C&#36; '+Number(n||0).toFixed(2)}function render(d){document.getElementById('clock').textContent=d.time||'--:--:--';document.getElementById('grid').innerHTML=(d.tables||[]).map(function(t){var c=t.status==='Disponible'?'green':t.status==='En juego'?'red':'yellow';return '<section class="card '+c+'"><div class="name">Mesa '+t.number+'</div><div class="status">'+t.status+'</div><div class="line">Inicio: '+(t.start||'—')+'</div><div class="line">Finalización: '+(t.end||'—')+'</div><div class="line">Tiempo jugado: '+(t.elapsed||'00:00:00')+'</div><div class="money">'+money(t.amount)+'</div></section>'}).join('')}async function tick(){try{var r=await fetch('/api/state?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error();render(await r.json());document.getElementById('offline').style.display='none'}catch(e){document.getElementById('offline').style.display='block'}}tick();setInterval(tick,1000);</script></body></html>'''

tv = '  String get tvHtml => ' + json.dumps(html, ensure_ascii=False) + ';\n'
s = insert_before(s, '  Map<String, dynamic> stateMap()', show_tv + '\n' + tv + '\n')

if len(re.findall(r'\bFuture\s*<\s*void\s*>\s+showTvConnection\s*\(\s*\)\s+async\b', s)) != 1:
    raise SystemExit('TV REPAIR FAILED: showTvConnection no quedó exactamente una vez')
if len(re.findall(r'(?m)^\s*String\s+get\s+tvHtml\s*=>', s)) != 1:
    raise SystemExit('TV REPAIR FAILED: tvHtml no quedó exactamente una vez')
if re.search(r'\b(?:showTvConnectionLegacy\d+|tvHtmlLegacy\d+)\b', s):
    raise SystemExit('TV REPAIR FAILED: quedaron definiciones heredadas')

TARGET.write_text(s)
print('OK: receptor TV reconstruido estructuralmente; una sola conexión y un solo getter')
