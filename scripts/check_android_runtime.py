#!/usr/bin/env python3
"""Optional real Android emulator runtime test; no BLE/optics/ASR is simulated as passed.

Needs official emulator, platform-tools and AOSP API35 x86_64 system image.
Metrics collection is explicitly disabled. Uses only a new isolated test AVD.
"""
import argparse,asyncio,datetime,hashlib,json,os,re,subprocess,sys,tempfile,threading,time,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop'))
from agentglass.server import Bridge
from agentglass.security import make_tls,tls_context
from aiohttp import web,ClientSession

def main():
 p=argparse.ArgumentParser();p.add_argument('--sdk',required=True,type=Path);p.add_argument('--boot-timeout',type=int,default=420);p.add_argument('--api',type=int,choices=[26,35],default=35);p.add_argument('--fresh-app',action='store_true',help='Remove only this disposable test AVD app and its test data before installation');a=p.parse_args()
 sdk=a.sdk.resolve();out=ROOT/'build/android-runtime';out.mkdir(parents=True,exist_ok=True)
 avds=out/'avd';avds.mkdir(exist_ok=True);avd=avds/('agentglass'+str(a.api)+'.avd');avd.mkdir(exist_ok=True)
 image=sdk/('system-images/android-'+str(a.api)+'/default/x86_64')
 (avds/('agentglass'+str(a.api)+'.ini')).write_text('avd.ini.encoding=UTF-8\npath='+str(avd)+'\ntarget=android-'+str(a.api)+'\n')
 (avd/'config.ini').write_text('\n'.join(['avd.ini.encoding=UTF-8','hw.cpu.arch=x86_64','hw.cpu.ncore=2','hw.ramSize=768','disk.dataPartition.size=1073741824','image.sysdir.1='+str(image)+'/','tag.id=default','abi.type=x86_64','hw.keyboard=yes','hw.lcd.width=480','hw.lcd.height=800','hw.lcd.density=160','hw.gpu.enabled=yes','hw.gpu.mode=swiftshader','vm.heapSize=192','PlayStore.enabled=false'])+'\n')
 env=os.environ.copy();env.update(ANDROID_AVD_HOME=str(avds),ANDROID_SDK_ROOT=str(sdk),ADB_SERVER_SOCKET='tcp:5037',ANDROID_I_WANT_MY_TCG='yes',HTTP_PROXY='http://127.0.0.1:1',HTTPS_PROXY='http://127.0.0.1:1',http_proxy='http://127.0.0.1:1',https_proxy='http://127.0.0.1:1')
 adb=sdk/'platform-tools/adb';emulator=sdk/'emulator/emulator';apk=ROOT/'build/android/agentglass-debug.apk'
 def call(args,timeout=30,check=True):
  r=subprocess.run([str(x) for x in args],env=env,capture_output=True,timeout=timeout)
  if check and r.returncode:raise RuntimeError(r.stderr.decode(errors='replace')[-500:])
  return r.stdout
 def device(*args,**kw):return call([adb,'-s','emulator-5554',*args],**kw)
 report={'evidence_level':2,'android_api':a.api,'physical_hardware_tests':0,'model_inference_executed':False,'apk_sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),'checks':{},'limitations':['No BLE peripheral','No real ASR/TTS engine acceptance','No optics/camera/battery/Windows tests'],'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 state=out/'desktop-state';state.mkdir(exist_ok=True)
 # Fresh private state for each run; generated credentials are never delivered.
 state=Path(tempfile.mkdtemp(prefix='state-',dir=state))
 fingerprint=make_tls(state,['127.0.0.1','10.0.2.2'])
 loop=asyncio.new_event_loop();ready=threading.Event();server_info={}
 def server_thread():
  asyncio.set_event_loop(loop)
  async def start():
   bridge=Bridge(state,{'computer_name':'Android Runtime PC','projects':{'demo':{'path':str(ROOT/'examples/demo-project'),'allow_write':True}}},simulate=True)
   operator,token=bridge.store.add_device('Runtime test operator','operator');code=bridge.store.pairing_code(ttl=600)
   runner=web.AppRunner(bridge.app());await runner.setup();await web.TCPSite(runner,'0.0.0.0',9443,ssl_context=tls_context(state)).start()
   server_info.update(runner=runner,token=token,code=code);ready.set()
  loop.run_until_complete(start());loop.run_forever()
 thread=threading.Thread(target=server_thread,daemon=True);thread.start();assert ready.wait(10)
 def desktop_request(method,path,body=None):
  async def run():
   import ssl
   trust=ssl.create_default_context(cafile=str(state/'server.pem'))
   async with ClientSession(headers={'Authorization':'Bearer '+server_info['token']}) as c:
    async with c.request(method,'https://127.0.0.1:9443'+path,json=body,ssl=trust) as r:
     j=await r.json()
     if r.status>=400:raise RuntimeError('desktop HTTP '+str(r.status))
     return j
  return asyncio.run_coroutine_threadsafe(run(),loop).result(20)
 log=(out/'emulator.log').open('wb');emu=None
 try:
  call([adb,'start-server'])
  command=[emulator,'-avd','agentglass'+str(a.api),'-port','5554','-no-window','-no-audio','-no-boot-anim','-no-snapshot','-accel','off','-gpu','swiftshader','-memory','768','-cores','2','-partition-size','1024','-no-metrics','-show-kernel']
  emu=subprocess.Popen([str(x) for x in command],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
  deadline=time.monotonic()+a.boot_timeout;last=0
  while time.monotonic()<deadline:
   if emu.poll() is not None:raise RuntimeError('emulator exited '+str(emu.returncode))
   if device('shell','getprop','sys.boot_completed',check=False,timeout=8).strip()==b'1':break
   if time.monotonic()-last>30:print('Waiting for Android boot',flush=True);last=time.monotonic()
   time.sleep(2)
  else:raise TimeoutError('Android boot timeout')
  report['checks']['android_booted']=True
  device('shell','input','keyevent','82');device('shell','wm','dismiss-keyguard',check=False)
  device('shell','settings','put','global','window_animation_scale','0');device('shell','settings','put','global','transition_animation_scale','0');device('shell','settings','put','global','animator_duration_scale','0')
  if a.fresh_app:device('uninstall','dev.agentglass',check=False)
  installed=device('install','-r',apk,timeout=60).decode();assert 'Success' in installed
  report['checks']['apk_installed']=True
  launch=device('shell','am','start','-W','-n','dev.agentglass/.MainActivity').decode();assert 'Error' not in launch
  report['checks']['activity_launched']=True;time.sleep(3)
  def hierarchy():
   device('shell','uiautomator','dump','/sdcard/agentglass-ui.xml',timeout=30)
   raw=device('exec-out','cat','/sdcard/agentglass-ui.xml').decode();(out/'ui.xml').write_text(raw);return ET.fromstring(raw)
  def tap(node):
   v=list(map(int,re.findall(r'\d+',node.attrib['bounds'])));device('shell','input','tap',str((v[0]+v[2])//2),str((v[1]+v[3])//2))
  def click(text):
   for n in hierarchy().iter('node'):
    if n.attrib.get('text')==text:tap(n);return
   raise RuntimeError('UI control not visible: '+text)
  def fill(index,value):
   nodes=[n for n in hierarchy().iter('node') if n.attrib.get('class')=='android.widget.EditText'];tap(nodes[index])
   device('shell','input','keyevent','123');device('shell','input','keyevent',*(['67']*100));device('shell','input','text',value.replace(' ','%s'));device('shell','input','keyevent','4')
  fill(0,'https://10.0.2.2:9443');fill(1,fingerprint);fill(2,server_info['code']);click('核对指纹并连接')
  deadline=time.monotonic()+45
  while time.monotonic()<deadline:
   xml=ET.tostring(hierarchy(),encoding='unicode')
   if 'demo' in xml:break
   time.sleep(1)
  else:raise TimeoutError('Android pinned TLS pairing not observed')
  report['checks']['android_tls_pair_and_projects']=True
  # Scroll to the command form. Read UI nodes on each swipe; never fixed labels.
  for _ in range(7):
   nodes=[n for n in hierarchy().iter('node') if n.attrib.get('class')=='android.widget.EditText']
   if any('说出或输入完整指令'==n.attrib.get('text') for n in nodes):
    node=next(n for n in nodes if n.attrib.get('text')=='说出或输入完整指令');tap(node);device('shell','input','text','Inspect%sthe%sdemo%sproject');device('shell','input','keyevent','4');break
   device('shell','input','swipe','240','700','240','260','250')
  for _ in range(5):
   xml=hierarchy();nodes=[n for n in xml.iter('node') if n.attrib.get('text')=='确认并发送任务']
   if nodes:tap(nodes[0]);break
   device('shell','input','swipe','240','700','240','300','250')
  click('发送');time.sleep(2)
  pending=desktop_request('GET','/v1/operator/pending')['tasks'];assert len(pending)==1
  task_id=pending[0]['id'];report['checks']['android_task_received_pending']=True
  desktop_request('POST','/v1/operator/tasks/'+task_id+'/decision',{'decision':'approve','acknowledge_snapshot_and_provider':True})
  time.sleep(5)
  xml=ET.tostring(hierarchy(),encoding='unicode');assert '任务完成' in xml
  report['checks']['android_displays_real_simulator_completion']=True
  (ROOT/'assets/android-runtime.png').write_bytes(device('exec-out','screencap','-p'))
  errors=device('logcat','-d','-v','brief','AndroidRuntime:E','*:S').decode(errors='replace');(out/'android-runtime-errors.txt').write_text(errors)
  assert 'FATAL EXCEPTION' not in errors
  report['checks']['no_app_fatal_exception']=True
  report['passed']=True
 except Exception as exc:
  report.update(passed=False,error=type(exc).__name__+': '+str(exc)[:500]);print(report['error'],flush=True)
 finally:
  if emu and emu.poll() is None:
   device('emu','kill',check=False,timeout=8)
   try:emu.wait(timeout=10)
   except subprocess.TimeoutExpired:emu.kill();emu.wait()
  call([adb,'kill-server'],check=False);log.close()
  if loop.is_running():
   asyncio.run_coroutine_threadsafe(server_info['runner'].cleanup(),loop).result(10);loop.call_soon_threadsafe(loop.stop);thread.join(5)
  (ROOT/'docs/evidence/android-runtime.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2));return 0 if report.get('passed') else 1
if __name__=='__main__':raise SystemExit(main())
