#!/usr/bin/env python3
import base64,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'build/host-native';out.mkdir(parents=True,exist_ok=True)
subprocess.run(['c++','-std=c++11','-O2','-Wall','-Wextra','-Werror','-I',str(ROOT/'firmware/include'),str(ROOT/'tests/native_core_check.cpp'),'-o',str(out/'check')],check=True)
r=subprocess.run([str(out/'check')],capture_output=True,text=True,check=True)
lines=r.stdout.splitlines()
assert len(lines)==257
for n,actual in enumerate(lines[:256]):
 expected=base64.b32encode(bytes((n+i*17)%256 for i in range(16))).decode().lower().rstrip('=')
 assert actual==expected
 for ext in ['.jpg','.wav','.v','.p']:assert len('/'+actual+ext)+1<=32
report={'evidence_level':2,'passed':True,'id_vectors_compared_to_python_rfc4648':256,'id_bits':128,
        'all_paths_fit_spiffs_32_bytes_including_nul':True,'hud_checks':lines[-1],
        'scope':'actual firmware header functions on host CPU; not flash storage or optics tests'}
(ROOT/'docs/evidence/native-core-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
