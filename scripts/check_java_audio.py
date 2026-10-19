#!/usr/bin/env python3
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'build/host-java';out.mkdir(parents=True,exist_ok=True)
compiler=['javac'] if shutil.which('javac') else ['java','com.sun.tools.javac.Main']
source=ROOT/'mobile/android/app/src/main/java/dev/codexglasses/PcmWave.java'
subprocess.run([*compiler,'--release','8','-d',str(out),str(source),str(ROOT/'tests/PcmWaveCheck.java')],check=True)
result=subprocess.run(['java','-cp',str(out),'PcmWaveCheck'],capture_output=True,text=True,check=True)
print(result.stdout)
report={'evidence_level':2,'scope':'host JVM tests of the actual Android PcmWave implementation; not Android device tests','assertions':result.stdout.strip().splitlines(),'passed':True}
(ROOT/'docs/evidence/java-audio-tests.json').write_text(json.dumps(report,indent=2)+'\n')
