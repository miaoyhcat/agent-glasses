"""Bounded model broker over worker stdio; no host listener or credential mount.

The official Responses API is called only by the desktop. The container has no
external network. Tests can explicitly inject a loopback upstream in Python.
"""
from __future__ import annotations
import base64,hashlib,hmac,json,os,secrets
from aiohttp import ClientSession,ClientTimeout,ClientError

class ModelProxy:
    def __init__(self,model,*,api_key=None,max_calls=8,max_body=256*1024,max_total=1024*1024,max_output=4096,_test_upstream=None):
        if not isinstance(model,str) or not 1<=len(model)<=100:raise ValueError('explicit_account_supported_model_required')
        self.key=api_key if api_key is not None else os.environ.get('OPENAI_API_KEY','')
        if not self.key:raise ValueError('model_api_key_not_configured')
        self.model=model;self.token=secrets.token_hex(32);self.calls=self.total=0
        self.max_calls,self.max_body,self.max_total,self.max_output=max_calls,max_body,max_total,max_output
        self.upstream=_test_upstream or 'https://api.openai.com/v1/responses'
        self.session=None;self.audit=[]
    async def __aenter__(self):
        self.session=ClientSession(timeout=ClientTimeout(total=None,sock_connect=10,sock_read=120),trust_env=False);return self
    async def __aexit__(self,*_):
        if self.session:await self.session.close()
        self.token='';self.key=''
    async def stream(self,frame,emit):
        request_id=frame['id'];started=False
        async def start(status,kind='application/json'):
            nonlocal started
            await emit({'channel':'model','kind':'start','id':request_id,'status':status,'content_type':kind});started=True
        async def chunk(data):
            # Small chunks with ACKs keep memory bounded and leave cancellation responsive.
            for offset in range(0,len(data),16384):
                await emit({'channel':'model','kind':'chunk','id':request_id,'data':base64.b64encode(data[offset:offset+16384]).decode()})
        async def error(code,status):
            await start(status);await chunk(json.dumps({'error':code}).encode())
        try:
            token=frame.get('token','')
            if not isinstance(token,str) or not hmac.compare_digest(token,self.token):await error('job_auth_required',401);return
            body=frame.get('body');raw=json.dumps(body,separators=(',',':')).encode()
            if len(raw)>self.max_body:await error('request_too_large',413);return
            if not isinstance(body,dict) or body.get('model')!=self.model:await error('model_not_authorized',403);return
            if any(body.get(k) is not None for k in ['conversation','prompt','previous_response_id']):
                await error('stateless_requests_only',403);return
            def text_input_only(value):
                if isinstance(value,list):return all(text_input_only(v) for v in value)
                if isinstance(value,dict):
                    if value.get('type') in {'input_image','input_file','input_audio','item_reference'}:return False
                    if any(k in value for k in ['file_id','file_url','image_url','audio_url']):return False
                    return all(text_input_only(v) for v in value.values())
                return True
            if not text_input_only(body.get('input')):await error('remote_input_reference_refused',403);return
            def allowed_tools(items,depth=0):
                if not isinstance(items,list) or len(items)>128 or depth>4:return False
                for tool in items:
                    if not isinstance(tool,dict):return False
                    if tool.get('type') in {'function','custom'}:continue
                    if tool.get('type')=='namespace' and allowed_tools(tool.get('tools'),depth+1):continue
                    return False
                return True
            if not allowed_tools(body.get('tools',[])):await error('hosted_tools_refused',403);return
            requested=body.get('max_output_tokens',self.max_output)
            if type(requested) is not int or requested<1:await error('invalid_output_limit',400);return
            if self.calls>=self.max_calls or self.total+len(raw)>self.max_total:await error('job_budget_exhausted',429);return
            # No await between check and reservation: concurrent requests share a hard cap.
            self.calls+=1;self.total+=len(raw)
            body=dict(body,max_output_tokens=min(requested,self.max_output),store=False,background=False,service_tier='default')
            self.audit.append({'call':self.calls,'input_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
            async with self.session.post(self.upstream,json=body,headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'},allow_redirects=False) as response:
                if response.status!=200:await error('provider_request_failed',502);return
                kind=response.headers.get('Content-Type','application/json').split(';')[0]
                if kind not in {'application/json','text/event-stream'}:await error('unexpected_provider_content_type',502);return
                await start(200,kind);response_bytes=0
                async for data in response.content.iter_any():
                    response_bytes+=len(data)
                    if response_bytes>1024*1024:
                        await emit({'channel':'model','kind':'abort','id':request_id});return
                    await chunk(data)
        except (TimeoutError,OSError,ClientError):
            if not started:await error('provider_transport_failed',502)
            else:await emit({'channel':'model','kind':'abort','id':request_id})
        finally:await emit({'channel':'model','kind':'end','id':request_id})
