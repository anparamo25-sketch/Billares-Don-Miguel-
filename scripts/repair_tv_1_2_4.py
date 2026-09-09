from pathlib import Path
import py_compile
import subprocess
PRODUCER=Path('scripts/rebuild_tv_1_2_5.py')
py_compile.compile(str(PRODUCER),doraise=True)
subprocess.check_call(['python3',str(PRODUCER)])
print('OK: productor canónico TV/LAN/mDNS ejecutado una sola vez')
