#!/usr/bin/env python3
"""One-command real HTTPS workflow, with an explicitly simulated agent backend."""
import asyncio
import hashlib
import json
import ssl
import tempfile
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop'))
from aiohttp import ClientSession, web
from agentglass.security import make_tls,tls_context
from agentglass.server import Bridge


async def main():
    with tempfile.TemporaryDirectory(prefix='agentglass-demo-') as td:
        base=Path(td);source=base/'project';source.mkdir();(source/'example.py').write_text('print("demo")\n')
        state=base/'state';state.mkdir();make_tls(state,[])
        bridge=Bridge(state,{'projects':{'demo':{'path':str(source),'allow_write':True}}},simulate=True)
        _,operator=bridge.store.add_device('local demo operator','operator')
        code=bridge.store.pairing_code()
        runner=web.AppRunner(bridge.app());await runner.setup()
        site=web.TCPSite(runner,'127.0.0.1',0,ssl_context=tls_context(state));await site.start()
        port=site._server.sockets[0].getsockname()[1];url=f'https://127.0.0.1:{port}'
        trust=ssl.create_default_context(cafile=str(state/'server.pem'))
        start=time.perf_counter();facts={}
        try:
            async with ClientSession() as client:
                async def call(method,path,payload=None,token=None):
                    async with client.request(method,url+path,json=payload,headers={'Authorization':'Bearer '+token} if token else {},ssl=trust) as response:
                        result=await response.json();return response.status,result
                status,_=await call('GET','/v1/tasks');facts['unauthorized_request_blocked']=status==401
                status,paired=await call('POST','/v1/pair',{'code':code,'name':'Simulated mobile'})
                token=paired['token'];facts['pair_success']=status==201
                request={'v':1,'request_id':'https_demo_request_001','project':'demo','action':'inspect','prompt':'检查项目是否有可复现的问题。'}
                status,task=await call('POST','/v1/tasks',request,token)
                facts['task_pending_local_approval']=status==201 and task['status']=='pending'
                _,repeated=await call('POST','/v1/tasks',request,token);facts['idempotency']=task['id']==repeated['id']
                status,_=await call('POST','/v1/operator/tasks/'+task['id']+'/decision',{'decision':'approve','acknowledge_snapshot_and_provider':True},token)
                facts['mobile_cannot_approve']=status==403
                status,_=await call('POST','/v1/operator/tasks/'+task['id']+'/decision',{'decision':'approve','acknowledge_snapshot_and_provider':True},operator)
                facts['local_operator_approval']=status==200
                for _ in range(100):
                    _,state_data=await call('GET','/v1/tasks/'+task['id'],token=token)
                    if state_data['status']=='completed':break
                    await asyncio.sleep(.02)
                facts['simulated_task_completed']=state_data['status']=='completed'
                _,events=await call('GET','/v1/events?after=0',token=token)
                cursor=events['cursor'];_,resumed=await call('GET','/v1/events?after='+str(cursor),token=token)
                facts['event_cursor_resume']=len(resumed['events'])==0
                content=b'AgentGlass simulated camera data; not an actual image.'
                status,media=await call('POST','/v1/media',{'size':len(content),'sha256':hashlib.sha256(content).hexdigest(),'mime':'image/jpeg'},token)
                async with client.put(url+'/v1/media/'+media['id']+'/chunks?offset=0',data=content,headers={'Authorization':'Bearer '+token},ssl=trust) as r:await r.read()
                _,committed=await call('POST','/v1/media/'+media['id']+'/commit',{},token)
                facts['media_sha256_commit']=committed['complete']==1
                facts['audit_chain_valid']=bridge.store.verify_audit()
                facts['original_project_unchanged']=(source/'example.py').read_text()=='print("demo")\n'
                facts['pass']=all(facts.values())
                report={'evidence_level':2,'agent_backend':'explicit simulator; not Codex/model inference','transport':'real loopback HTTPS with generated local certificate',
                        'assertions':facts,'events':[{k:e[k] for k in ['seq','kind','data']} for e in events['events']],
                        'duration_seconds':round(time.perf_counter()-start,4),'hardware_test':False}
                out=ROOT/'docs/evidence/https-demo.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
                print(json.dumps(report,ensure_ascii=False,indent=2))
                if not facts['pass']:raise RuntimeError('HTTPS demo failed')
        finally:await runner.cleanup()


if __name__=='__main__':asyncio.run(main())
