import contextlib
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from codexglasses.codex import AppServer, run_codex
from codexglasses.media import MediaStore
from codexglasses.protocol import ble_packet, ble_verify, task_request
from codexglasses.security import snapshot_project, make_tls
from codexglasses.server import Bridge
from codexglasses.store import Store
from codexglasses.isolation import container_command


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = Store(self.path/"state.db")
        self.device, self.token = self.store.add_device("phone")

    def tearDown(self):
        self.store.close(); self.temp.cleanup()

    def new_task(self):
        return self.store.create_task(self.device, "request_0001", "demo", "inspect", "find bugs")[0]

    def test_token_revocation(self):
        self.assertEqual(self.store.authenticate(self.token)["id"], self.device)
        self.assertIsNone(self.store.authenticate("bad"))
        self.store.revoke(self.device)
        self.assertIsNone(self.store.authenticate(self.token))

    def test_pairing_single_use(self):
        code = self.store.pairing_code()
        device, token = self.store.pair(code, "new")
        self.assertTrue(self.store.authenticate(token))
        with self.assertRaises(ValueError): self.store.pair(code, "replay")

    def test_pairing_expiry(self):
        code = self.store.pairing_code(ttl=-1)
        with self.assertRaises(ValueError): self.store.pair(code, "late")

    def test_idempotent_request(self):
        a = self.new_task()
        b, created = self.store.create_task(self.device, "request_0001", "demo", "inspect", "find bugs")
        self.assertFalse(created); self.assertEqual(a["id"], b["id"])
        with self.assertRaises(ValueError): self.store.create_task(self.device, "request_0001", "demo", "fix", "different")

    def test_event_cursor(self):
        task = self.new_task()
        first = self.store.events()
        self.store.event(task["id"], "plan", {"step": "testing"})
        rest = self.store.events(after=first[-1]["seq"])
        self.assertEqual(len(rest), 1); self.assertEqual(rest[0]["kind"], "plan")

    def test_state_machine_rejects_forged_completion(self):
        task = self.new_task()
        with self.assertRaises(ValueError): self.store.transition(task["id"], "completed")

    def test_restart_marks_unknown_not_success(self):
        task = self.new_task()
        self.store.transition(task["id"], "preparing")
        self.store.transition(task["id"], "running")
        self.store.recover()
        self.assertEqual(self.store.task(task["id"])["status"], "unknown")

    def test_cancel_is_not_completion(self):
        task = self.new_task(); self.store.transition(task["id"], "preparing")
        self.store.transition(task["id"], "running"); self.store.transition(task["id"], "cancel_requested")
        self.assertEqual(self.store.task(task["id"])["status"], "cancel_requested")

    def test_audit_tampering_detected(self):
        self.new_task(); self.assertTrue(self.store.verify_audit())
        self.store.db.execute("UPDATE audit SET body='changed' WHERE seq=1")
        self.assertFalse(self.store.verify_audit())

    def test_media_resume_retry_hash_and_owner(self):
        media = MediaStore(self.path/"media", self.store)
        payload = os.urandom(700)
        item = media.create(self.device, size=len(payload), sha256=hashlib.sha256(payload).hexdigest(), mime="image/jpeg")
        self.assertEqual(media.append(self.device, item, 0, payload[:300]), 300)
        self.assertEqual(media.append(self.device, item, 0, payload[:300]), 300)
        with self.assertRaises(ValueError): media.append(self.device, item, 0, b"bad")
        with self.assertRaises(ValueError): media.commit(self.device, item)
        with self.assertRaises(KeyError): media.info("other", item)
        media.append(self.device, item, 300, payload[300:])
        self.assertEqual(media.commit(self.device, item)["complete"], 1)
        self.assertEqual(media.commit(self.device, item)["complete"], 1)

    def test_media_hash_mismatch_rejected(self):
        media = MediaStore(self.path/"media", self.store)
        item = media.create(self.device, size=3, sha256="0"*64, mime="image/jpeg")
        media.append(self.device, item, 0, b"abc")
        with self.assertRaises(ValueError): media.commit(self.device, item)

    def test_media_lost_create_response_does_not_reserve_again(self):
        media=MediaStore(self.path/'media',self.store,quota=6)
        metadata=dict(size=6,sha256=hashlib.sha256(b'abcdef').hexdigest(),mime='image/jpeg',request_id='capture_request_1')
        item=media.create(self.device,**metadata)
        media.append(self.device,item,0,b'abc')
        for _ in range(100):self.assertEqual(media.create(self.device,**metadata),item)
        self.assertEqual(media.info(self.device,item)['received'],3)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM media').fetchone()[0],1)
        with self.assertRaisesRegex(ValueError,'idempotency_conflict'):media.create(self.device,**{**metadata,'sha256':'0'*64})
        media.append(self.device,item,3,b'def');media.commit(self.device,item)
        self.assertEqual(media.create(self.device,**metadata),item)

    def test_media_request_is_owner_scoped_and_validated(self):
        media=MediaStore(self.path/'media',self.store)
        args=dict(size=3,sha256=hashlib.sha256(b'abc').hexdigest(),mime='image/jpeg',request_id='capture_request_2')
        a=media.create(self.device,**args);b=media.create('another-device',**args)
        self.assertNotEqual(a,b)
        for value in ['../invalid','short',123,'x'*129]:
            with self.assertRaises(ValueError):media.create(self.device,**{**args,'request_id':value})

    def test_media_commit_rename_crash_is_recovered(self):
        media=MediaStore(self.path/'media',self.store)
        item=media.create(self.device,size=3,sha256=hashlib.sha256(b'abc').hexdigest(),mime='image/jpeg',request_id='capture_request_3')
        media.append(self.device,item,0,b'abc')
        (self.path/'media'/(item+'.part')).rename(self.path/'media'/(item+'.bin'))
        media.recover()
        self.assertTrue(media.info(self.device,item)['complete'])
        self.assertEqual(media.commit(self.device,item)['received'],3)

    def test_media_disk_length_recovery(self):
        media = MediaStore(self.path/"media", self.store)
        item = media.create(self.device, size=6, sha256=hashlib.sha256(b"abcdef").hexdigest(), mime="image/jpeg")
        (self.path/"media"/(item+".part")).write_bytes(b"abc")
        media.recover()
        self.assertEqual(media.info(self.device, item)["received"], 3)

    def test_media_quota_and_traversal(self):
        media = MediaStore(self.path/"media", self.store, quota=5)
        with self.assertRaises(ValueError): media.create(self.device, size=10, sha256="0"*64, mime="image/jpeg")
        with self.assertRaises(KeyError): media.info(self.device, "../../secret")

    def test_followup_requires_completed_same_project_and_reuses_workspace(self):
        task=self.new_task()
        with self.assertRaises(ValueError):self.store.create_task(self.device,'follow_001','demo','inspect','continue',task['id'])
        self.store.transition(task['id'],'preparing');self.store.attach(task['id'],workspace=str(self.path/'work'),thread_id='original_thread')
        self.store.transition(task['id'],'running');self.store.transition(task['id'],'completed')
        child,_=self.store.create_task(self.device,'follow_002','demo','inspect','continue',task['id'])
        self.assertEqual(child['workspace'],str(self.path/'work'));self.assertEqual(child['parent_task_id'],task['id'])
        with self.assertRaises(ValueError):self.store.create_task(self.device,'follow_003','other','inspect','continue',task['id'])


class BoundaryTests(unittest.TestCase):
    def test_protocol_validation(self):
        b = {"v": 1, "request_id": "test_123456", "project": "demo", "action": "inspect", "prompt": "find bugs"}
        self.assertEqual(task_request(b), b)
        for update in [{"v": 2}, {"project": "../../"}, {"action": "shell"}, {"prompt": ""}, {"cwd": "/"}]:
            with self.assertRaises(ValueError): task_request({**b, **update})

    def test_ble_auth_replay_and_session(self):
        key = bytes(range(32)); session = "a"*32
        packet = ble_packet(key, session, 1, "status")
        self.assertEqual(ble_verify(key, session, 0, packet), (1, {"op": "status"}))
        for sid,last,p in [(session,1,packet),("b"*32,0,packet),(session,0,packet.replace("status","photo"))]:
            with self.assertRaises(ValueError): ble_verify(key, sid, last, p)

    def test_snapshot_excludes_secrets_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); root = base/"project"; root.mkdir()
            (root/"app.py").write_text("original")
            (root/".env").write_text("SECRET"); (root/".git").mkdir(); (root/".git/config").write_text("token")
            (root/'.codex').mkdir();(root/'.codex/auth.json').write_text('HOST_CREDENTIAL_FIXTURE');(root/'.codex/config.toml').write_text('[mcp_servers.hidden]\ncommand="danger"')
            counts = snapshot_project(root, base/"copy")
            self.assertEqual(counts["files"],1)
            (base/"copy/app.py").write_text("changed")
            self.assertEqual((root/"app.py").read_text(),"original")

    def test_snapshot_rejects_symlink_and_nested_destination(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/"project"; root.mkdir()
            with self.assertRaises(ValueError): snapshot_project(root,root/"copy")
            (base/"outside").write_text("secret"); (root/"escape").symlink_to(base/"outside")
            with self.assertRaises(ValueError): snapshot_project(root,base/"copy")

    def test_tls_certificate_is_created_with_private_key_mode(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            fingerprint = make_tls(directory,["192.168.1.2"])
            self.assertEqual(len(fingerprint),64)
            if os.name != "nt":self.assertEqual((directory/"server.key").stat().st_mode & 0o777,0o600)

    def test_no_real_agent_on_unisolated_host(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);auth=root/'auth.json';auth.write_text('{}')
            with self.assertRaises(ValueError):container_command({},root)
            command=container_command({'runtime_isolation':'docker','worker_auth_file':str(auth)},root)
            self.assertIn('--read-only',command)
            self.assertIn('--cap-drop=ALL',command)
            self.assertIn('--network=none',command)
            self.assertFalse(any('auth.json' in a for a in command))
            self.assertIn('CODEXGLASSES_PROXY_TOKEN',command)
            self.assertTrue(any('target=/workspace,readonly' in a for a in command))
            self.assertFalse(any('docker.sock' in a for a in command))


class HttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=Path(self.temp.name)
        self.project=self.path/"project"; self.project.mkdir(); (self.project/"hello.py").write_text("print('hi')")
        self.bridge=Bridge(self.path/"state",{"projects":{"demo":{"path":str(self.project),"allow_write":False}}},simulate=True)
        self.device,self.token=self.bridge.store.add_device("phone")
        _,self.operator=self.bridge.store.add_device("desktop","operator")
        self.client=TestClient(TestServer(self.bridge.app(test_insecure=True)));await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close();self.temp.cleanup()

    def headers(self,operator=False):return {"Authorization":"Bearer "+(self.operator if operator else self.token)}
    def body(self,**kw):return {"v":1,"request_id":"test_request_123","project":"demo","action":"inspect","prompt":"check code",**kw}
    async def create(self):
        r=await self.client.post('/v1/tasks',json=self.body(),headers=self.headers());self.assertEqual(r.status,201);return await r.json()

    async def test_anonymous_and_wrong_token(self):
        self.assertEqual((await self.client.get('/v1/tasks')).status,401)
        self.assertEqual((await self.client.get('/v1/tasks',headers={"Authorization":"Bearer bad"})).status,401)

    async def test_origin_blocked(self):
        self.assertEqual((await self.client.get('/v1/tasks',headers={**self.headers(),"Origin":"https://evil.invalid"})).status,403)

    async def test_phone_cannot_approve_or_write(self):
        task=await self.create()
        r=await self.client.post('/v1/operator/tasks/'+task['id']+'/decision',json={"decision":"approve"},headers=self.headers())
        self.assertEqual(r.status,403)
        r=await self.client.post('/v1/tasks',json=self.body(action='fix'),headers=self.headers());self.assertEqual(r.status,403)

    async def test_concurrent_local_approvals_launch_once(self):
        task=await self.create();path='/v1/operator/tasks/'+task['id']+'/decision'
        responses=await asyncio.gather(*[self.client.post(path,json={'decision':'approve','acknowledge_snapshot_and_provider':True},headers=self.headers(True)) for _ in range(2)])
        self.assertEqual(sorted(r.status for r in responses),[200,400])
        await asyncio.sleep(.08)
        events=self.bridge.store.events(task_id=task['id'])
        self.assertEqual(sum(e['kind']=='snapshot' for e in events),1)

    async def test_unknown_project_and_extra_command_rejected(self):
        for body in [self.body(project='other'),self.body(command='rm -rf /')]:
            r=await self.client.post('/v1/tasks',json=body,headers=self.headers());self.assertEqual(r.status,400)

    async def test_pair_code_not_reusable_and_rate_limited(self):
        code=self.bridge.store.pairing_code()
        r=await self.client.post('/v1/pair',json={"code":code,"name":"new"});self.assertEqual(r.status,201)
        for i in range(4):
            r=await self.client.post('/v1/pair',json={"code":code,"name":"replay"});self.assertEqual(r.status,400)
        r=await self.client.post('/v1/pair',json={"code":code,"name":"flood"});self.assertEqual(r.status,429)

    async def test_e2e_simulator_requires_approval_and_has_real_cursor(self):
        task=await self.create();self.assertEqual(task['status'],'pending')
        r=await self.client.post('/v1/operator/tasks/'+task['id']+'/decision',json={"decision":"approve","acknowledge_snapshot_and_provider":True},headers=self.headers(True));self.assertEqual(r.status,200)
        for _ in range(50):
            r=await self.client.get('/v1/tasks/'+task['id'],headers=self.headers());current=await r.json()
            if current['status']=='completed':break
            await asyncio.sleep(.02)
        self.assertEqual(current['status'],'completed')
        self.assertEqual(self.bridge.public_task(current)['verification_status'],'not_verified')
        r=await self.client.get('/v1/events',headers=self.headers());events=await r.json()
        self.assertGreater(events['cursor'],1)
        self.assertTrue(any(e['data'].get('simulated') for e in events['events']))
        self.assertEqual((self.project/'hello.py').read_text(),"print('hi')")

    async def test_cancel_before_launch(self):
        task=await self.create()
        r=await self.client.post('/v1/tasks/'+task['id']+'/cancel',json={},headers=self.headers())
        self.assertEqual((await r.json())['status'],'cancelled')

    async def test_hud_progress_persists_from_real_event_not_poll_time(self):
        self.bridge.config['computer_name']='Verified Lab PC'
        health=await self.client.get('/health')
        self.assertEqual((await health.json())['computer_name'],'Verified Lab PC')
        task=await self.create()
        self.bridge.store.event(task['id'],'plan',{'plan':[{'step':'Run focused tests','status':'inProgress'}]})
        self.bridge.store.event(task['id'],'summary',{'text':'Visible result'})
        for _ in range(2):
            r=await self.client.get('/v1/tasks/'+task['id'],headers=self.headers())
            current=await r.json()
            self.assertEqual(current['progress_text'],'Run focused tests')
            self.assertGreater(current['progress_event_seq'],0)
            self.assertEqual(current['last_summary'],'Visible result')

    async def test_paid_cloud_disabled_and_nonobject_json_rejected(self):
        r=await self.client.post('/v1/ai',headers=self.headers(),json={'consent_upload_and_cost':True,'kind':'vision'})
        self.assertEqual(r.status,403)
        r=await self.client.post('/v1/tasks',headers=self.headers(),json=[])
        self.assertEqual(r.status,400)

    async def test_http_media_integrity(self):
        payload=b'example-media'
        r=await self.client.post('/v1/media',headers=self.headers(),json={"size":len(payload),"sha256":hashlib.sha256(payload).hexdigest(),"mime":"image/jpeg"})
        self.assertEqual(r.status,201);media_id=(await r.json())['id']
        r=await self.client.put('/v1/media/'+media_id+'/chunks?offset=0',headers=self.headers(),data=payload);self.assertEqual(r.status,200)
        r=await self.client.post('/v1/media/'+media_id+'/commit',headers=self.headers(),json={});self.assertEqual((await r.json())['complete'],1)

    async def test_http_media_lost_initiation_reply_and_completed_retry(self):
        payload=b'upload-response-lost'
        body={'size':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'mime':'image/jpeg','request_id':'stable_media_request_1'}
        first=await self.client.post('/v1/media',headers=self.headers(),json=body);item=(await first.json())['id']
        await self.client.put('/v1/media/'+item+'/chunks?offset=0',headers=self.headers(),data=payload)
        retry=await self.client.post('/v1/media',headers=self.headers(),json=body)
        self.assertEqual((await retry.json())['offset'],len(payload))
        await self.client.post('/v1/media/'+item+'/commit',headers=self.headers(),json={})
        retry=await self.client.post('/v1/media',headers=self.headers(),json=body);result=await retry.json()
        self.assertEqual(result['id'],item);self.assertIs(result['complete'],True)

    async def test_followup_waits_for_completed_worker_process(self):
        task=await self.create();store=self.bridge.store
        store.attach(task['id'],workspace=str(self.path/'snapshot'))
        for status in ['preparing','running','completed']:store.transition(task['id'],status)
        response=await self.client.post('/v1/tasks',json=self.body(request_id='busy_followup_123',parent_task_id=task['id']),headers=self.headers())
        child=await response.json()
        sleeper=asyncio.create_task(asyncio.Event().wait());self.bridge.runners[task['id']]=sleeper
        try:
            response=await self.client.post('/v1/operator/tasks/'+child['id']+'/decision',json={'decision':'approve','acknowledge_snapshot_and_provider':True},headers=self.headers(True))
            self.assertEqual(response.status,400);self.assertEqual(store.task(child['id'])['status'],'pending')
        finally:
            self.bridge.runners.pop(task['id']);sleeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):await sleeper

    async def test_real_followup_requires_cleanup_evidence(self):
        task=await self.create();store=self.bridge.store
        store.attach(task['id'],workspace=str(self.path/'snapshot'))
        for status in ['preparing','running','completed']:store.transition(task['id'],status)
        response=await self.client.post('/v1/tasks',json=self.body(request_id='cleanup_followup_123',parent_task_id=task['id']),headers=self.headers());child=await response.json()
        self.bridge.simulate=False
        response=await self.client.post('/v1/operator/tasks/'+child['id']+'/decision',json={'decision':'approve','acknowledge_snapshot_and_provider':True},headers=self.headers(True))
        self.assertEqual(response.status,400);self.assertEqual(store.task(child['id'])['status'],'pending')
        self.assertEqual((await response.json())['error'],'invalid_request_or_state')
        self.assertNotIn(child['id'],self.bridge.runners)

    async def test_http_followup_workspace_retained(self):
        task=await self.create()
        async def approve(task_id):
            r=await self.client.post('/v1/operator/tasks/'+task_id+'/decision',json={'decision':'approve','acknowledge_snapshot_and_provider':True},headers=self.headers(True));self.assertEqual(r.status,200)
            for _ in range(80):
                state=self.bridge.store.task(task_id)
                if state['status']=='completed':return state
                await asyncio.sleep(.01)
            self.fail('simulation timed out')
        parent=await approve(task['id'])
        r=await self.client.post('/v1/tasks',json=self.body(request_id='followup_http_123',parent_task_id=task['id']),headers=self.headers());self.assertEqual(r.status,201)
        child=await r.json();done=await approve(child['id'])
        self.assertEqual(done['workspace'],parent['workspace'])


class CodexProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_before_turn_is_failed_without_relaying_stderr(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);store=Store(root/'state.db');device,_=store.add_device('test')
            task=store.create_task(device,'timeout_thread_123','demo','inspect','Check')[0];store.transition(task['id'],'preparing')
            await run_codex(task,store,[sys.executable,str(Path(__file__).with_name('fake_codex.py')),'--stall-thread'],root,rpc_timeout=.3)
            self.assertEqual(store.task(task['id'])['status'],'failed')
            events=store.events();encoded=json.dumps(events);self.assertNotIn('CREDENTIAL_SENTINEL',encoded)
            diagnostic=next(e['data'] for e in events if e['data'].get('event')=='execution_diagnostic')
            self.assertEqual(diagnostic['stage'],'thread_start');self.assertIn('permission_denied',diagnostic['signals']);store.close()

    async def test_turn_start_timeout_is_unknown_not_a_claimed_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);store=Store(root/'state.db');device,_=store.add_device('test')
            task=store.create_task(device,'timeout_turn_123','demo','fix','Fix')[0];store.transition(task['id'],'preparing')
            await run_codex(task,store,[sys.executable,str(Path(__file__).with_name('fake_codex.py')),'--stall-turn'],root,rpc_timeout=.3)
            self.assertEqual(store.task(task['id'])['status'],'unknown');store.close()

    async def test_followup_uses_official_thread_resume_request(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);store=Store(root/'state.db');device,_=store.add_device('test')
            task=store.create_task(device,'resume_123','demo','test','Run tests')[0];store.transition(task['id'],'preparing')
            fixture=Path(__file__).with_name('fake_codex.py')
            await run_codex(task,store,[sys.executable,str(fixture),'--require-resume'],root,timeout=5,resume_thread_id='fixture_thread')
            self.assertEqual(store.task(task['id'])['status'],'completed')
            self.assertEqual(store.task(task['id'])['thread_id'],'fixture_thread');store.close()

    async def test_stdio_fixture_approvals_and_reasoning_filter(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);store=Store(root/'state.db');device,_=store.add_device('test')
            task=store.create_task(device,'protocol_123','demo','inspect','Check snapshot')[0]
            store.transition(task['id'],'preparing');workspace=root/'work';workspace.mkdir()
            fixture=Path(__file__).with_name('fake_codex.py')
            await run_codex(task,store,[sys.executable,str(fixture)],workspace,timeout=5)
            self.assertEqual(store.task(task['id'])['status'],'completed')
            events=store.events();encoded=json.dumps(events)
            for secret in ['DO_NOT_EXPOSE_SECRET_REASONING','secret command','secret output']:
                self.assertNotIn(secret,encoded)
            self.assertTrue(any(e['data'].get('event')=='bridge/approvalDenied' for e in events))
            self.assertEqual(store.task(task['id'])['thread_id'],'fixture_thread')
            store.close()

    async def test_missing_executable_does_not_become_simulated_success(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);store=Store(root/'state.db');device,_=store.add_device('test')
            task=store.create_task(device,'missing_123','demo','inspect','Check')[0];store.transition(task['id'],'preparing')
            await run_codex(task,store,['/nonexistent-codexglasses-codex'],root)
            self.assertEqual(store.task(task['id'])['status'],'failed');store.close()


if __name__ == '__main__':unittest.main()
