#!/usr/bin/env python3
"""Host JVM fault injection against actual Android shared reliability code."""
import json
from pathlib import Path
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'build/host-java-reliability';out.mkdir(parents=True,exist_ok=True)
compiler=['javac'] if shutil.which('javac') else ['java','com.sun.tools.javac.Main']
source=ROOT/'mobile/android/app/src/main/java/dev/agentglass'
subprocess.run([*compiler,'--release','8','-d',str(out),str(source/'DurableFiles.java'),str(source/'TaskDispatch.java'),str(ROOT/'tests/ReliabilityCheck.java')],check=True)
result=subprocess.run(['java','-cp',str(out),'ReliabilityCheck'],capture_output=True,text=True,check=True)
print(result.stdout)
report={'evidence_level':2,'scope':'host JVM, actual APK source classes; NOT an Android filesystem power-cut or BLE device test',
        'assertions':result.stdout.strip().splitlines(),'passed':True}
(ROOT/'docs/evidence/java-reliability-tests.json').write_text(json.dumps(report,indent=2)+'\n')
