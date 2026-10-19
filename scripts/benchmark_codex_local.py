#!/usr/bin/env python3
"""Opt-in real CLI/local-model benchmark, restricted to the bundled public fixture.

This diagnostic is NOT the production Docker runner. Use a disposable machine
without private files. No model weights/toolchains are included or downloaded.
"""
import argparse
import ast
import asyncio
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop'));sys.path.insert(0,str(ROOT/'scripts'))
from codexglasses.codex import AppServer,run_codex
from codexglasses.model_proxy import ModelProxy
from codexglasses.store import Store
from fixture_mcp import FixtureTools,canonical_ast


def toml(value):
    if isinstance(value,dict):return '{'+','.join(k+'='+toml(v) for k,v in value.items())+'}'
    return json.dumps(value)


async def exercise(args,out,version):
    fixture=out/'public-fixture';fixture.mkdir()
    for name in ['discount.py','test_discount.py']:shutil.copyfile(ROOT/'examples/demo-project'/name,fixture/name)
    instructions=out/'instructions.txt'
    instructions.write_text('Use only the fixture MCP tools read_fixture, write_fixture and test_fixture. Read the original source; run failing tests; write the full corrected source preserving imports and the function; run tests again. Do not use shell or change tests. A function name in prose does not run it. Respond briefly. /no_think\n')
    # Original local-model settings, no hosted-model plan/upgrade metadata.
    catalog=out/'catalog.json'
    catalog.write_text(json.dumps({'models':[{'slug':args.model,'display_name':'Local public-fixture model','description':'Local diagnostic model, not OpenAI hosted',
        'context_window':8192,'max_context_window':8192,'input_modalities':['text'],'shell_type':'shell_command',
        'supports_parallel_tool_calls':False,'supports_reasoning_summaries':False,'supports_reasoning_summary_parameter':False,
        'default_reasoning_summary':'none','base_instructions':instructions.read_text()}]}))
    audit=out/'tool-audit.jsonl'
    settings={'model_provider':'codexglasses_proxy','model_providers.codexglasses_proxy':{'name':'Local public-fixture broker','base_url':'http://127.0.0.1:9041/v1','env_key':'CODEXGLASSES_PROXY_TOKEN','wire_api':'responses','requires_openai_auth':False},
        'model':args.model,'model_catalog_json':str(catalog),'model_instructions_file':str(instructions),
        'analytics.enabled':False,'feedback.enabled':False,'otel.exporter':'none','otel.metrics_exporter':'none','otel.trace_exporter':'none',
        'features.api_key_model_discovery':False,'features.plugins':False,'features.remote_plugin':False,'features.apps':False,
        'features.unified_exec':False,'features.shell_snapshot':False,'features.code_mode_host':False,'web_search':'disabled',
        'shell_environment_policy.inherit':'none','mcp_servers.cua_repl.enabled':False,
        'mcp_servers.fixture':{'command':sys.executable,'args':[str(ROOT/'scripts/fixture_mcp.py'),'--fixture-directory',str(fixture),'--audit',str(audit)],'startup_timeout_sec':15,'tool_timeout_sec':20}}
    command=[str(args.codex)]
    for key,value in settings.items():command+=['-c',key+'='+toml(value)]
    command+=['app-server']
    # Refuse inherited external MCPs before starting a thread or model request.
    async def ignore(method,params):pass
    check=AppServer(command,ignore,timeout=20)
    try:
        await check.start();config=(await check.call('config/read',{'includeLayers':False}))['config']
        unexpected=[n for n,s in config.get('mcp_servers',{}).items() if n!='fixture' and s.get('enabled',True)]
        if unexpected:raise RuntimeError('Inherited external MCP servers must be disabled for this disposable benchmark')
    finally:await check.close()
    bootstrap='import sys;sys.path.insert(0,'+repr(str(ROOT/'agent-integration/codex'))+');from worker_entry import Worker;raise SystemExit(Worker().run('+repr(command)+'))'
    class LocalProxy(ModelProxy):
        async def stream(self,frame,emit):
            frame.setdefault('body',{})['reasoning']={'effort':'none'}
            await super().stream(frame,emit)
    store=Store(out/'state.db');device,_=store.add_device('public local benchmark')
    task=store.create_task(device,'public_fixture_1','demo','fix','Use only the fixture MCP tools. Read discount.py, run failing tests, correct its discount arithmetic with write_fixture, then run test_fixture again. Do not use shell or change tests.')[0]
    store.transition(task['id'],'preparing')
    try:
        async with LocalProxy(args.model,api_key='LOCAL_MODEL_DUMMY_ONLY',_test_upstream='http://127.0.0.1:11434/v1/responses',max_output=768) as proxy:
            await run_codex(task,store,[sys.executable,'-c',bootstrap],fixture,model=args.model,framed=True,model_proxy=proxy,
                child_env={'CODEXGLASSES_PROXY_TOKEN':proxy.token,'OPENAI_API_KEY':'','CODEX_API_KEY':''},rpc_timeout=45,timeout=360)
            expected=ast.parse((ROOT/'examples/demo-project/discount.py').read_text())
            for node in ast.walk(expected):
                if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):node.op=ast.Sub()
            safe=canonical_ast((fixture/'discount.py').read_text())==canonical_ast(expected)
            result=FixtureTools(fixture).invoke('test_fixture',{}) if safe else {'exit_code':None,'output':'Patch guard failed; no model code executed independently.'}
            (out/'independent-tests.txt').write_text(result['output'])
            calls=[json.loads(line) for line in audit.read_text().splitlines()] if audit.exists() else []
            report={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'evidence_level':2,'physical_hardware_tests':0,
                'cli_version':version,'model':args.model,'model_requests':proxy.calls,'model_inference_executed':proxy.calls>0,
                'task_status':store.task(task['id'])['status'],'container_executed':False,'capability_limited_public_fixture_only':True,
                'minimal_patch_security_guard':safe,'independent_test_exit':result['exit_code'],'mcp_tool_audit':calls,'events':store.events(),
                'model_patch_sha256':hashlib.sha256((fixture/'discount.py').read_bytes()).hexdigest()}
            report['passed']=report['task_status']=='completed' and safe and result['exit_code']==0 and any(c.get('written') for c in calls) and any(c.get('exit_code')==0 for c in calls)
            (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps({k:v for k,v in report.items() if k not in {'events','mcp_tool_audit'}},indent=2),flush=True)
            return report['passed']
    finally:store.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--codex',type=Path,required=True);p.add_argument('--ollama',type=Path,required=True)
    p.add_argument('--models',type=Path,required=True);p.add_argument('--model',default='qwen3:4b-instruct');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--public-disposable-environment',action='store_true');a=p.parse_args()
    if not a.public_disposable_environment:p.error('This diagnostic requires a disposable environment without private files; use the production Docker path for real projects')
    for name in ['codex','ollama','models']:setattr(a,name,getattr(a,name).resolve(strict=True))
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False,mode=0o700)
    version=subprocess.run([str(a.codex),'--version'],capture_output=True,text=True,check=True).stdout.strip()
    env=os.environ.copy();env.update(OLLAMA_MODELS=str(a.models),OLLAMA_HOST='127.0.0.1:11434',OLLAMA_CONTEXT_LENGTH='8192',OLLAMA_NO_CLOUD='true',OLLAMA_NUM_PARALLEL='1')
    with (out/'ollama.log').open('w') as log:
        server=subprocess.Popen([str(a.ollama),'serve'],env=env,stdout=log,stderr=log)
        try:
            for attempt in range(80):
                if server.poll() is not None:raise RuntimeError('Local Ollama server exited; use a fresh environment/free loopback port')
                try:urllib.request.urlopen('http://127.0.0.1:11434/api/version',timeout=.5).read();break
                except OSError:
                    if attempt==79:raise
                    time.sleep(.25)
            # No hosted model/telemetry fallback. No credentials are downloaded.
            for key in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']:os.environ[key]='http://127.0.0.1:1'
            os.environ['NO_PROXY']=os.environ['no_proxy']='127.0.0.1,localhost'
            return 0 if asyncio.run(exercise(a,out,version)) else 1
        finally:
            server.terminate()
            try:server.wait(4)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':raise SystemExit(main())
