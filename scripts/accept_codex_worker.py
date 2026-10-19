#!/usr/bin/env python3
"""Opt-in target-computer acceptance. Full mode uses a real, potentially paid model."""
import argparse,ast,asyncio,datetime,hashlib,json,shutil,ssl,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'desktop'))
from codexglasses.cli import initialize
from codexglasses.doctor import readiness
from codexglasses.codex import remove_owned_container
from codexglasses.server import Bridge
from codexglasses.security import tls_context
from aiohttp import web,ClientSession
sys.path.insert(0,str(ROOT/'scripts'))
from fixture_mcp import FixtureTools,canonical_ast

def hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}

def stage_acceptance_fixture(workspace, original, destination):
    """Stage ONLY a guarded model module and byte-identical trusted tests.

    Never import unittest or stale bytecode from the model-controlled snapshot.
    This is acceptance of the public arithmetic fixture, not a general verifier.
    """
    workspace=Path(workspace).resolve(strict=True);original=Path(original).resolve(strict=True)
    source=workspace/'discount.py';test=workspace/'test_discount.py'
    for path in [source,test]:
        if path.is_symlink() or not path.is_file() or path.resolve().parent!=workspace:
            raise RuntimeError('acceptance_source_or_test_is_not_regular')
    if source.stat().st_size>8192 or test.read_bytes()!=(original/'test_discount.py').read_bytes():
        raise RuntimeError('acceptance_source_too_large_or_tests_modified')
    expected=ast.parse((original/'discount.py').read_text())
    changes=0
    for node in ast.walk(expected):
        if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):node.op=ast.Sub();changes+=1
    if changes!=1 or canonical_ast(source.read_text())!=canonical_ast(expected):
        raise RuntimeError('public_fixture_arithmetic_patch_guard_failed')
    destination=Path(destination);destination.mkdir(exist_ok=False)
    shutil.copyfile(source,destination/'discount.py')
    shutil.copyfile(original/'test_discount.py',destination/'test_discount.py')
    FixtureTools(destination).guard()
    return destination


async def full(args,out,report):
    source=out/'original-fixture';shutil.copytree(ROOT/'examples/demo-project',source)
    before=hashes(source);state=out/'state';initialize(state,['127.0.0.1'],'Live acceptance PC')
    config=json.loads((state/'config.json').read_text())
    config.update(runtime_isolation='docker',worker_image=args.image,codex_model=args.model,
                  allow_model_api=True,projects={'demo':{'path':str(source),'allow_write':True}})
    (state/'config.json').write_text(json.dumps(config,indent=2))
    bridge=Bridge(state,config);code=bridge.store.pairing_code();operator=(state/'operator.token').read_text().strip()
    runner=web.AppRunner(bridge.app());await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0,ssl_context=tls_context(state));await site.start()
    port=site._server.sockets[0].getsockname()[1];base=f'https://127.0.0.1:{port}'
    trust=ssl.create_default_context(cafile=str(state/'server.pem'))
    try:
        async with ClientSession() as client:
            async def request(method,path,body=None,token=None):
                headers={'Authorization':'Bearer '+token} if token else {}
                async with client.request(method,base+path,json=body,ssl=trust,headers=headers) as r:
                    payload=await r.json()
                    if r.status>=400:raise RuntimeError(f'HTTP {r.status}: '+str(payload.get('error')))
                    return payload
            token=(await request('POST','/v1/pair',{'code':code,'name':'Acceptance device'}))['token']
            parent=None;tasks=[];report['tasks']=tasks
            steps=[('inspect','Identify the discount error; do not modify files.'),
                   ('fix','Fix the discount error without changing tests.'),
                   ('test','Run existing Python unittest tests and report exact results.')]
            for action,prompt in steps:
                body={'v':1,'request_id':str(uuid.uuid4()),'project':'demo','action':action,'prompt':prompt}
                if parent:body['parent_task_id']=parent['id']
                task=await request('POST','/v1/tasks',body,token)
                await request('POST','/v1/operator/tasks/'+task['id']+'/decision',
                              {'decision':'approve','acknowledge_snapshot_and_provider':True},operator)
                deadline=time.monotonic()+args.timeout
                while time.monotonic()<deadline:
                    task=await request('GET','/v1/tasks/'+task['id'],token=token)
                    if task['status'] in {'completed','failed','unknown','cancelled','rejected'}:break
                    await asyncio.sleep(.5)
                tasks.append(task)
                if task['status']!='completed':raise RuntimeError(action+' did not complete: '+task['status'])
                if task.get('worker_cleanup_confirmed') is not True:raise RuntimeError('worker cleanup unconfirmed')
                if parent and task['thread_id']!=parent['thread_id']:raise RuntimeError('thread continuity failed')
                parent=task
            workspace=Path(bridge.store.task(parent['id'])['workspace'])
            if hashes(source)!=before:raise RuntimeError('original project changed')
            for name,digest in before.items():
                if Path(name).name.startswith('test_') and hashlib.sha256((workspace/name).read_bytes()).hexdigest()!=digest:
                    raise RuntimeError('acceptance tests were modified')
            clean=stage_acceptance_fixture(workspace,source,out/'independent-fixture')
            independent_name='codexglasses-'+uuid.uuid4().hex
            command=['docker','run','--rm','--name',independent_name,'--label','dev.codexglasses.temporary-worker=true','--pull=never','--network=none','--read-only','--cap-drop=ALL',
                     '--security-opt=no-new-privileges','--user=10001:10001','--memory=512m','--cpus=1','--pids-limit=64',
                     '--tmpfs=/tmp:rw,nosuid,nodev,size=64m','--mount',
                     f'type=bind,source={clean},target=/acceptance,readonly','--workdir=/tmp',
                     '--entrypoint=python3',args.image,'-I','-B','-X','pycache_prefix=/tmp/codexglasses-acceptance-cache',
                     '-m','unittest','discover','-s','/acceptance','-v']
            try:
                result=await asyncio.to_thread(subprocess.run,command,capture_output=True,text=True,timeout=90)
            finally:
                report['independent_container_cleanup_confirmed']=await remove_owned_container(independent_name)
            if report['independent_container_cleanup_confirmed'] is not True:
                raise RuntimeError('independent container cleanup unconfirmed')
            (out/'independent-tests.txt').write_text(result.stdout+result.stderr)
            report['independent_test_exit']=result.returncode
            report['independent_fixture_guard_passed']=True
            report['independent_runner_ignores_snapshot_bytecode_and_shadow_modules']=True
            if result.returncode:raise RuntimeError('independent fixture tests failed')
            events=bridge.store.events();report['public_event_count']=len(events)
            if any(e['data'].get('simulated') for e in events):raise RuntimeError('simulated event in live run')
            report.update(passed=True,original_unchanged=True,model_inference_executed=True)
    finally:await runner.cleanup()

def main():
    p=argparse.ArgumentParser();p.add_argument('--model');p.add_argument('--image',default='codexglasses-codex:0.162.1-broker1')
    p.add_argument('--output',type=Path,default=ROOT/'build/live-codex');p.add_argument('--timeout',type=int,default=900)
    p.add_argument('--run',action='store_true');p.add_argument('--acknowledge-model-cost',action='store_true');a=p.parse_args()
    config={'runtime_isolation':'docker','worker_image':a.image,'codex_model':a.model,
            'allow_model_api':a.run and a.acknowledge_model_cost,
            'projects':{'demo':{'path':str(ROOT/'examples/demo-project')}}}
    report={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'evidence_level':2,
            'physical_hardware_tests':0,'model_inference_executed':False,
            'preflight':readiness(config),'full_test_requested':a.run}
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if a.run and (not a.acknowledge_model_cost or not report['preflight']['launch_prerequisites_present']):
        report.update(passed=False,error='Cost acknowledgment and all prerequisites are required')
    elif a.run:
        if (out/'state').exists() or (out/'original-fixture').exists():p.error('Use a fresh output directory')
        try:asyncio.run(full(a,out,report))
        except Exception as exc:report.update(passed=False,error=type(exc).__name__+': '+str(exc)[:300])
    else:report.update(passed=False,note='Preflight only; no successful live acceptance is claimed')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return 0 if report.get('passed') else 1
if __name__=='__main__':raise SystemExit(main())
