"""Read-only readiness checks; no credential contents or model calls."""
from pathlib import Path
import os,re,shutil,subprocess

def readiness(config):
    checks=[]
    def check(name,passed,detail):checks.append({'check':name,'passed':bool(passed),'detail':detail})
    check('runtime_isolation',config.get('runtime_isolation')=='docker','Real HTTP jobs require Docker; simulation remains separate')
    check('owner_enabled_model_api',config.get('allow_model_api') is True,'Model API billing is disabled until the desktop owner enables it')
    check('desktop_model_key',bool(os.environ.get('OPENAI_API_KEY')),'Only environment variable presence is checked; the key is never printed or mounted')
    check('explicit_model',isinstance(config.get('codex_model'),str) and bool(config['codex_model']),'Choose an actual account-supported Codex model; no automatic paid probe')
    projects=config.get('projects',{})
    check('authorized_projects',bool(projects) and all(Path(v['path']).is_dir() for v in projects.values()),'Configured project directories must exist')
    docker=shutil.which('docker');check('docker_cli',docker is not None,'Docker CLI is installed' if docker else 'Docker CLI is missing')
    image=config.get('worker_image','agentglass-codex:0.162.1-broker1')
    valid_image=isinstance(image,str) and re.fullmatch(r'[a-zA-Z0-9_./:@-]{1,200}',image)
    check('worker_image_name',valid_image,'Only a local administrator configures this image')
    if docker:
        for name,args in [('docker_daemon',['info','--format','{{.ServerVersion}}']),('worker_image_local',['image','inspect','--format','{{.Id}}',image])]:
            if name=='worker_image_local' and not valid_image:continue
            try:
                result=subprocess.run([docker,*args],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=5,text=True)
                check(name,result.returncode==0,'Available locally' if result.returncode==0 else 'Unavailable; no image is pulled automatically')
            except (OSError,subprocess.TimeoutExpired):check(name,False,'Unavailable or timed out')
    return {'checks':checks,'launch_prerequisites_present':all(x['passed'] for x in checks),
            'model_inference_executed':False,'container_security_test_executed':False,
            'note':'Passing prerequisite checks is not proof of authentication, sandbox enforcement or a successful task.'}
