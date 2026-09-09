from pathlib import Path
import re, subprocess, py_compile

TARGET=Path('lib/main.dart')
STABLE='5e5ec88e7f6c12f5c1dae006ad95da4b903f950d'
SCRIPTS=('scripts/prepare_1_2_4.py','scripts/repair_1_2_4_generated.py','scripts/repair_tv_1_2_4.py','scripts/repair_tv_hostname_1_2_5.py','scripts/ensure_mdns_1_2_5.py','scripts/repair_tv_final_safety.py')
for p in SCRIPTS: py_compile.compile(p,doraise=True)

def span(src,name):
    m=re.search(rf'\bclass\s+{re.escape(name)}\b[^{{]*\{{',src)
    if not m: raise SystemExit(f'No se encontró la clase {name}')
    a=m.start(); i=src.find('{',m.start()); d=0; q=None; t=False
    while i<len(src):
        if q:
            tok=q*3 if t else q
            if src.startswith(tok,i): i+=len(tok); q=None; t=False; continue
            if src[i]=='\\' and not t: i+=2; continue
            i+=1; continue
        if src.startswith("'''",i): q,t="'",True; i+=3; continue
        if src.startswith('"""',i): q,t='"',True; i+=3; continue
        if src[i] in "'\"": q,t=src[i],False; i+=1; continue
        if src.startswith('//',i):
            e=src.find('\n',i+2); i=len(src) if e<0 else e+1; continue
        if src.startswith('/*',i):
            e=src.find('*/',i+2); i=len(src) if e<0 else e+2; continue
        if src[i]=='{': d+=1
        elif src[i]=='}':
            d-=1
            if d==0:return a,i+1
        i+=1
    raise SystemExit(f'Llaves sin cerrar en {name}')

def extract(src,name): a,b=span(src,name); return src[a:b]
def replace(src,name,new): a,b=span(src,name); return src[:a]+new+src[b:]

def mask(src):
    out=list(src); i=0; n=len(src); q=None; t=False
    while i<n:
        if q:
            tok=q*3 if t else q
            if src.startswith(tok,i):
                for j in range(i,min(i+len(tok),n)): out[j]=' '
                i+=len(tok); q=None; t=False; continue
            out[i]='\n' if src[i]=='\n' else ' '
            if src[i]=='\\' and not t and i+1<n: out[i+1]=' '; i+=2
            else:i+=1
            continue
        if src.startswith('//',i):
            out[i]=out[i+1]=' '; i+=2
            while i<n and src[i]!='\n': out[i]=' '; i+=1
            continue
        if src.startswith('/*',i):
            out[i]=out[i+1]=' '; i+=2
            while i<n and not src.startswith('*/',i): out[i]='\n' if src[i]=='\n' else ' '; i+=1
            if i<n: out[i]=out[i+1]=' '; i+=2
            continue
        if src.startswith("'''",i): q,t="'",True; out[i:i+3]=[' ']*3; i+=3; continue
        if src.startswith('"""',i): q,t='"',True; out[i:i+3]=[' ']*3; i+=3; continue
        if src[i] in "'\"": q,t=src[i],False; out[i]=' '; i+=1; continue
        i+=1
    return ''.join(out)

s=TARGET.read_text()
base=subprocess.check_output(['git','show',f'{STABLE}:lib/main.dart'],text=True)
s=replace(s,'_LoginPageState',extract(base,'_LoginPageState'))
s=re.sub(r"const String appVersion = '[^']+';","const String appVersion = '1.2.5+125';",s,count=1)
s=re.sub(r"const String updateManifestUrl = '[^']+';","const String updateManifestUrl = 'https://github.com/anparamo25-sketch/Billares-Don-Miguel-/raw/refs/heads/main/update.json';",s,count=1)
lines=s.splitlines(); seen=set(); clean=[]
for line in lines:
    if line.startswith('import '):
        if line in seen: continue
        seen.add(line)
    clean.append(line)
s='\n'.join(clean)+'\n'
login=extract(s,'_LoginPageState')
for bad in ('checkingUpdate','showSettings','logout','dashboard()','historyPage()'):
    if bad in login: raise SystemExit(f'REPAIR PREFLIGHT FAILED: {bad} dentro de _LoginPageState')
if not re.search(r'\bMap<String,\s*dynamic>\s+stateMap\s*\(\)',s): raise SystemExit('REPAIR PREFLIGHT FAILED: stateMap ausente')
TARGET.write_text(s)
subprocess.check_call(['python3','scripts/repair_tv_1_2_4.py'])
subprocess.check_call(['python3','scripts/repair_tv_hostname_1_2_5.py'])
subprocess.check_call(['python3','scripts/ensure_mdns_1_2_5.py'])
s=TARGET.read_text(); s=re.sub(r"const String appVersion = '[^']+';","const String appVersion = '1.2.5+125';",s,count=1)
n=re.sub(r'\s+',' ',s)
for marker,msg in {'String get tvHtml =>':'tvHtml ausente','Billares Don Miguel - TV':'título TV ausente',"fetch('/api/state?ts='+Date.now()":'actualización TV ausente','RawDatagramSocket? _billaresMdnsSocket;':'mDNS ausente','Future<void> _startBillaresMdns() async':'método mDNS ausente','await _startBillaresMdns();':'arranque mDNS ausente',"function money(n){return 'C&#36; ":'formato monetario ausente'}.items():
    if marker not in n: raise SystemExit(f'REPAIR TV FAILED: {msg}')
binds=re.findall(r'HttpServer\.bind\s*\(\s*InternetAddress\.anyIPv4\s*,\s*([^,\)]+)',n)
if not any(x.strip()=='80' for x in binds): raise SystemExit(f'REPAIR TV FAILED: puerto 80 no reconocido: {binds}')
if 'billaresdonmiguel.local' not in n: raise SystemExit('REPAIR TV FAILED: hostname TV ausente')
# showTvConnection: validar la firma real en la fuente, sin enmascarado global.
show=re.findall(r'(?m)^\s*Future\s*<\s*void\s*>\s+showTvConnection\s*\(\s*\)\s+async\s*\{',s)
if len(show)!=1: raise SystemExit(f'REPAIR TV FAILED: reconstrucción showTvConnection detectada {len(show)} veces')
pos=s.find('Future<void> showTvConnection() async')
if pos<0 or 'showDialog<void>' not in s[pos:pos+2500]: raise SystemExit('REPAIR TV FAILED: cuerpo de showTvConnection inválido')
# tvHtml sí se valida sobre código enmascarado porque su contenido es un literal Dart.
c=mask(s)
getters=list(re.finditer(r'(?m)^\s*String\s+get\s+tvHtml\s*=>\s*',c))
if len(getters)!=1: raise SystemExit(f'REPAIR TV FAILED: tvHtml quedó {len(getters)} veces')
st=getters[0].start(); en=s.find('\n',st); en=len(s) if en<0 else en
g=s[st:en]
if not g.rstrip().endswith(';'): raise SystemExit('REPAIR TV FAILED: getter tvHtml inválido')
if '<!doctype html>' not in g.lower() or '/api/state?ts=' not in g or 'C&#36;' not in g: raise SystemExit('REPAIR TV FAILED: contenido TV incompleto')
if 'return r"""' in s or "return r'''" in s or 'String get tvHtml {' in s: raise SystemExit('REPAIR TV FAILED: TV heredada detectada')
for line in c.splitlines():
    if '===' in line: raise SystemExit('REPAIR TV FAILED: JavaScript fuera del getter TV')
TARGET.write_text(s)
print('OK: fuente 1.2.5; reconstrucción TV y mDNS reconocidas estructuralmente')
