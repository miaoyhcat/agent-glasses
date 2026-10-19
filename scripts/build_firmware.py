#!/usr/bin/env python3
"""Build pinned firmware with opt-out checked BEFORE invoking PlatformIO.

Records actual return codes and final SUCCESS markers; a shell tail cannot mask
compiler/OOM errors. Binary hashes are evidence only, not distributed firmware.
"""
import argparse,datetime,hashlib,json,os,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--env',action='append',choices=['codexglasses_d0','codexglasses_tglass_v2']);a=p.parse_args()
 os.environ['PLATFORMIO_SETTING_ENABLE_TELEMETRY']='no'
 from platformio import app
 if app.get_setting('enable_telemetry') is not False:raise RuntimeError('telemetry_opt_out_not_applied')
 report={'evidence_level':2,'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'platformio_telemetry_enabled':False,'physical_hardware_tests':0,'targets':{}}
 for name in a.env or ['codexglasses_d0','codexglasses_tglass_v2']:
  logfile=ROOT/'docs/evidence'/('firmware-build.txt' if name=='codexglasses_d0' else 'tglass-v2-build.txt')
  command=[sys.executable,'-u','-m','platformio','run','-d','firmware','-e',name,'-j','2']
  result=subprocess.run(command,cwd=ROOT,env=os.environ.copy(),capture_output=True,text=True)
  logfile.write_text(result.stdout+result.stderr)
  binary=ROOT/'firmware/.pio/build'/name/'firmware.bin'
  passed=result.returncode==0 and '[SUCCESS]' in result.stdout and binary.is_file()
  fields={'exit_code':result.returncode,'passed':passed,'log':str(logfile.relative_to(ROOT))}
  for key,pattern in [('ram_bytes',r'RAM:.*?used (\d+) bytes'),('program_bytes',r'Flash:.*?used (\d+) bytes')]:
   match=re.search(pattern,result.stdout);fields[key]=int(match[1]) if match else None
  if passed:fields.update(binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),binary_bytes=binary.stat().st_size)
  report['targets'][name]=fields;print(name,'PASS' if passed else 'FAIL',fields,flush=True)
 report['all_passed']=all(x['passed'] for x in report['targets'].values())
 (ROOT/'docs/evidence/firmware-validation.json').write_text(json.dumps(report,indent=2)+'\n')
 raise SystemExit(0 if report['all_passed'] else 1)
if __name__=='__main__':main()
