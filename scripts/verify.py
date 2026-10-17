#!/usr/bin/env python3
"""Run repeatable host checks and preserve actual exit codes and logs.

Does not invoke paid APIs, an actual Codex task, or any attached hardware.
Optional firmware/Android/CAD/KiCad checks have their own documented commands.
"""
import datetime
import importlib.metadata
import json
import platform
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=ROOT/'docs/evidence';out.mkdir(exist_ok=True)
    cases=[('unit-tests',[sys.executable,'-m','unittest','discover','-s','tests','-v']),
           ('https-demo',[sys.executable,'simulator/demo.py']),
           ('engineering-calculations',[sys.executable,'scripts/engineering.py']),
           ('java-audio',[sys.executable,'scripts/check_java_audio.py']),
           ('java-reliability',[sys.executable,'scripts/check_java_reliability.py']),
           ('native-firmware-core',[sys.executable,'scripts/check_native_core.py'])]
    checks=[]
    for name,command in cases:
        environment={**os.environ,'PYTHONPATH':str(ROOT/'desktop')+(os.pathsep+os.environ['PYTHONPATH'] if os.environ.get('PYTHONPATH') else '')}
        result=subprocess.run(command,cwd=ROOT,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        logfile=out/(name+'.txt');logfile.write_text(result.stdout)
        entry={'name':name,'exit_code':result.returncode,'passed':result.returncode==0,'command':[Path(c).name if c==sys.executable else c for c in command],'log':str(logfile.relative_to(ROOT))}
        if name=='unit-tests':
            match=re.search(r'Ran (\d+) tests',result.stdout);entry['test_count']=int(match.group(1)) if match else None
        checks.append(entry);print(name+': '+('PASS' if result.returncode==0 else 'FAIL'))
    report={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'evidence_level':2,
            'python':platform.python_version(),'platform':platform.platform(),
            'dependencies':{p:importlib.metadata.version(p) for p in ['aiohttp','cryptography']},
            'checks':checks,'physical_hardware_tests':0,'model_inference_executed':False,
            'all_passed':all(x['passed'] for x in checks)}
    (out/'software-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if report['all_passed'] else 1)


if __name__=='__main__':main()
