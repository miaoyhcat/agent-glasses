import asyncio,base64,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,AsyncMock
from aiohttp import web
from aiohttp.test_utils import TestServer
from codexglasses.model_proxy import ModelProxy
from codexglasses.codex import run_codex,remove_owned_container
from codexglasses.store import Store
ROOT=Path(__file__).resolve().parents[1]

class BrokerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls=[];self.leaks=0
        async def response(request):
            body=await request.json();self.calls.append((body,request.headers.get('Authorization')))
            await asyncio.sleep(.01)
            return web.Response(body=b'data: {"fixture_payload":true}\n\n',content_type='text/event-stream')
        async def redirect(request):return web.Response(status=302,headers={'Location':'/leak'})
        async def leak(request):self.leaks+=1;return web.json_response({})
        app=web.Application();app.router.add_post('/responses',response);app.router.add_post('/redirect',redirect);app.router.add_route('*','/leak',leak)
        self.server=TestServer(app);await self.server.start_server()
    async def asyncTearDown(self):await self.server.close()
    def broker(self,**options):return ModelProxy('fixture-model',api_key='HOST_ONLY_DUMMY_CREDENTIAL',_test_upstream=str(self.server.make_url('/responses')),**options)
    async def invoke(self,broker,**updates):
        frames=[]
        async def emit(value):frames.append(value)
        await broker.stream({'id':'a'*32,'token':broker.token,'body':{'model':'fixture-model','input':'test'},**updates},emit)
        return frames
    async def test_host_key_stays_upstream_and_output_is_bounded(self):
        async with self.broker() as b:
            original={'model':'fixture-model','input':'test','max_output_tokens':99999,'store':True}
            frames=await self.invoke(b,body=original)
            self.assertEqual(self.calls[0][1],'Bearer HOST_ONLY_DUMMY_CREDENTIAL')
            self.assertEqual(self.calls[0][0]['max_output_tokens'],4096);self.assertIs(self.calls[0][0]['store'],False)
            self.assertNotIn('HOST_ONLY_DUMMY_CREDENTIAL',json.dumps(frames));self.assertEqual(original['max_output_tokens'],99999)
            content=b''.join(base64.b64decode(x['data']) for x in frames if x['kind']=='chunk')
            self.assertIn(b'fixture_payload',content)
    async def test_auth_model_and_request_size_fail_before_upstream(self):
        async with self.broker(max_body=100) as b:
            for updates,status in [({'token':'wrong'},401),({'body':{'model':'different'}},403),({'body':{'model':'fixture-model','input':'x'*200}},413)]:
                frames=await self.invoke(b,**updates);self.assertEqual(frames[0]['status'],status)
            self.assertEqual(len(self.calls),0);self.assertEqual(b.calls,0)
    async def test_budget_is_atomic_under_concurrent_requests(self):
        async with self.broker(max_calls=2) as b:
            results=await asyncio.gather(*(self.invoke(b,id=str(i)*32) for i in range(4)))
            self.assertEqual(sorted(r[0]['status'] for r in results),[200,200,429,429]);self.assertEqual(len(self.calls),2)
    async def test_redirect_cannot_forward_host_credential(self):
        async with ModelProxy('fixture-model',api_key='HOST_ONLY_DUMMY_CREDENTIAL',_test_upstream=str(self.server.make_url('/redirect'))) as b:
            frames=await self.invoke(b);self.assertEqual(frames[0]['status'],502);self.assertEqual(self.leaks,0)
    async def test_hosted_tools_and_foreign_server_state_are_refused(self):
        async with self.broker() as b:
            for extra in [{'tools':[{'type':'web_search'}]},{'conversation':'foreign'},{'previous_response_id':'foreign'},{'prompt':{'id':'foreign'}}]:
                frames=await self.invoke(b,body={'model':'fixture-model','input':'test',**extra});self.assertEqual(frames[0]['status'],403)
            self.assertEqual(len(self.calls),0)
    async def test_remote_images_and_private_file_references_are_refused(self):
        async with self.broker() as b:
            for value in [[{'type':'input_file','file_id':'other-file'}],[{'role':'user','content':[{'type':'input_image','image_url':'https://example.invalid/exfil'}]}]]:
                frames=await self.invoke(b,body={'model':'fixture-model','input':value});self.assertEqual(frames[0]['status'],403)
            self.assertEqual(b.calls,0)
    async def test_full_worker_stdio_and_http_stream_with_ack(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);store=Store(root/'state.db');device,_=store.add_device('fixture')
            task=store.create_task(device,'broker_protocol_123','demo','inspect','test broker')[0];store.transition(task['id'],'preparing')
            script="import sys;sys.path.insert(0,"+repr(str(ROOT/'agent-integration/codex'))+");from worker_entry import Worker;raise SystemExit(Worker().run([sys.executable,"+repr(str(ROOT/'tests/fake_codex.py'))+",'--model-proxy']))"
            async with self.broker() as b:
                await run_codex(task,store,[sys.executable,'-c',script],root,framed=True,model_proxy=b,child_env={'CODEXGLASSES_PROXY_TOKEN':b.token},timeout=10)
                self.assertEqual(store.task(task['id'])['status'],'completed');self.assertEqual(b.calls,1)
                self.assertNotIn('HOST_ONLY_DUMMY_CREDENTIAL',json.dumps(store.events()))
            store.close()
    async def test_only_exact_owned_container_names_can_be_removed(self):
        with self.assertRaises(ValueError):await remove_owned_container('unrelated-container')
        process=AsyncMock();process.returncode=0;process.communicate.return_value=(b'',b'')
        with patch('codexglasses.codex.asyncio.create_subprocess_exec',return_value=process) as launch:
            self.assertTrue(await remove_owned_container('codexglasses-'+'a'*32))
            self.assertEqual(launch.call_args.args[:4],('docker','rm','--force','codexglasses-'+'a'*32))
