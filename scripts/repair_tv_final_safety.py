from pathlib import Path
import json

TARGET = Path('lib/main.dart')
s = TARGET.read_text()

# Final deterministic TV cleanup. The receiver is ALWAYS one physical Dart line
# containing a JSON-escaped HTML string. Never use regex over the HTML itself:
# the HTML contains JavaScript semicolons and those previously caused corruption.
html = '''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Billares Don Miguel - TV</title><style>*{box-sizing:border-box}body{margin:0;background:#05070b;color:#fff;font-family:Arial,sans-serif}header{padding:18px;text-align:center;background:#fff;border-bottom:3px solid #1557c0}h1{margin:0;font-size:clamp(28px,4vw,46px);color:#1557c0;text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff}.clock{margin-top:6px;font-size:clamp(18px,2vw,26px);font-weight:700;color:#123f91}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px;padding:22px;max-width:1800px;margin:auto}.card{border-radius:18px;padding:22px;background:#111827;border:3px solid #64748b;min-height:205px}.green{background:#103b22;border-color:#22c55e}.red{background:#511b1b;border-color:#ef4444}.yellow{background:#56490a;border-color:#eab308}.name{font-size:clamp(25px,3vw,38px);font-weight:900}.status{margin:10px 0;font-size:clamp(18px,2vw,25px);font-weight:800}.line{margin:8px 0;font-size:clamp(15px,1.6vw,20px)}.money{margin-top:14px;font-size:clamp(25px,2.7vw,36px);font-weight:900}.offline{position:fixed;right:12px;bottom:10px;background:#7f1d1d;padding:7px 12px;border-radius:10px;display:none}</style></head><body><header><h1>Billares Don Miguel</h1><div id="clock" class="clock">Conectando...</div></header><main id="grid" class="grid"></main><div id="offline" class="offline">Sin conexión con CENTRAL</div><script>function money(n){return 'C&#36; '+Number(n||0).toFixed(2)}function render(d){document.getElementById('clock').textContent=d.time||'--:--:--';document.getElementById('grid').innerHTML=(d.tables||[]).map(function(t){var c=t.status==='Disponible'?'green':t.status==='En juego'?'red':'yellow';return '<section class="card '+c+'"><div class="name">Mesa '+t.number+'</div><div class="status">'+t.status+'</div><div class="line">Inicio: '+(t.start||'—')+'</div><div class="line">Finalización: '+(t.end||'—')+'</div><div class="line">Tiempo jugado: '+(t.elapsed||'00:00:00')+'</div><div class="money">'+money(t.amount)+'</div></section>'}).join('')}async function tick(){try{var r=await fetch('/api/state?ts='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error();render(await r.json());document.getElementById('offline').style.display='none'}catch(e){document.getElementById('offline').style.display='block'}}tick();setInterval(tick,1000);</script></body></html>'''

getter = '  String get tvHtml => ' + json.dumps(html, ensure_ascii=False) + ';'
needle = '  String get tvHtml => '
positions = []
pos = 0
while True:
    p = s.find(needle, pos)
    if p < 0:
        break
    positions.append(p)
    pos = p + len(needle)

if len(positions) == 0:
    raise SystemExit('TV FINAL FAILED: no se encontró getter tvHtml')

# Remove every complete getter line, then insert exactly one at the first location.
lines = s.splitlines()
out = []
inserted = False
for line in lines:
    if line.startswith(needle):
        if not inserted:
            out.append(getter)
            inserted = True
        continue
s = '\n'.join(out) + '\n'

if s.count(needle) != 1:
    raise SystemExit(f'TV FINAL FAILED: quedaron {s.count(needle)} getters tvHtml')
if 'return r"""' in s or "return r'''" in s:
    raise SystemExit('TV FINAL FAILED: todavía existe un return con triple comillas')
if 'String get tvHtml {' in s:
    raise SystemExit('TV FINAL FAILED: quedó getter tvHtml con bloque Dart antiguo')

TARGET.write_text(s)
print('OK: receptor TV reconstruido en una sola línea Dart JSON-escapada')
