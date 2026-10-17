"""Authenticated HTTPS companion API. A loopback operator controls every launch."""
from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from aiohttp import web

from .codex import run_codex
from .media import MediaStore
from .protocol import task_request
from .security import snapshot_project,prepare_worker_tree
from .store import Store, TERMINAL
from .cloud import CloudAI
from .isolation import container_command
from .model_proxy import ModelProxy

WEB = Path(__file__).with_name("web")
DEVICE_KEY = web.RequestKey("agentglass.device", dict)


class Bridge:
    def __init__(self, directory: Path, config, *, simulate=False, fixed_command=None):
        self.directory, self.config, self.simulate = directory, config, simulate
        self.store = Store(directory/"state.db")
        self.media = MediaStore(directory/"media", self.store)
        self.store.recover()
        self.media.recover()
        self.runners, self.clients = {}, {}
        self.rate = defaultdict(deque)
        self.command = fixed_command or config.get("codex_command", ["codex", "app-server"])
        self.fixed_test_command = fixed_command
        self.ai = CloudAI(config)

    def throttle(self, key, count, seconds):
        now = time.monotonic()
        q = self.rate[key]
        while q and q[0] < now-seconds:
            q.popleft()
        if len(q) >= count:
            raise web.HTTPTooManyRequests(text='{"error":"rate_limited"}', content_type="application/json")
        q.append(now)

    def operator(self, request):
        peer = request.transport.get_extra_info("peername")
        try:
            local = peer and ipaddress.ip_address(peer[0]).is_loopback
        except ValueError:
            local = False
        if request[DEVICE_KEY]["role"] != "operator" or not local:
            raise web.HTTPForbidden(text='{"error":"local_operator_required"}', content_type="application/json")

    async def pair(self, request):
        self.throttle(("pair", request.remote), 5, 60)
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("code"), str) or len(body["code"]) > 100:
            raise ValueError("invalid_pairing")
        if not isinstance(body.get("name"), str) or not 1 <= len(body["name"]) <= 80:
            raise ValueError("invalid_device_name")
        device, token = self.store.pair(body["code"], body["name"])
        return web.json_response({"v": 1, "device_id": device, "token": token}, status=201)

    async def projects(self, request):
        return web.json_response({"v": 1, "projects": [
            {"id": key, "write_enabled": bool(value.get("allow_write", False))}
            for key, value in self.config.get("projects", {}).items()]})

    async def create_task(self, request):
        device = request[DEVICE_KEY]
        self.throttle(("task", device["id"]), 10, 60)
        body = task_request(await request.json())
        project = self.config.get("projects", {}).get(body["project"])
        if not project:
            raise ValueError("project_not_authorized")
        if body["action"] != "inspect" and not project.get("allow_write", False):
            raise web.HTTPForbidden(text='{"error":"snapshot_writes_not_authorized"}', content_type="application/json")
        task, created = self.store.create_task(device["id"], body["request_id"], body["project"], body["action"], body["prompt"], body.get("parent_task_id"))
        return web.json_response(self.public_task(task), status=201 if created else 200)

    def public_task(self, task):
        result = {key: task[key] for key in ["id", "project", "action", "status", "thread_id", "turn_id", "created", "parent_task_id"]}
        row = self.store.db.execute("SELECT data FROM events WHERE task_id=? AND kind='summary' ORDER BY seq DESC LIMIT 1", (task["id"],)).fetchone()
        result["last_summary"] = json.loads(row[0]).get("text", "") if row else ""
        row = self.store.db.execute("SELECT seq,kind,data FROM events WHERE task_id=? AND kind IN ('plan','item','status') ORDER BY seq DESC LIMIT 1", (task["id"],)).fetchone()
        result["progress_event_seq"] = row["seq"] if row else None
        result["progress_text"] = ""
        if row:
            data = json.loads(row["data"])
            if row["kind"] == "plan":
                plan = data.get("plan", [])
                step = next((p for p in plan if p.get("status") in {"inProgress", "in_progress"}), plan[-1] if plan else {})
                result["progress_text"] = str(step.get("step", ""))[:160]
            elif row["kind"] == "item":
                result["progress_text"] = str(data.get("type", ""))+" / "+str(data.get("lifecycle", ""))
                if data.get("exit_code") is not None:
                    result["progress_text"] += " / exit="+str(data["exit_code"])
            else:
                result["progress_text"] = str(data.get("error") or data.get("stage") or data.get("source") or data.get("status", ""))[:160]
        cleanup=self.store.db.execute("SELECT data FROM events WHERE task_id=? AND kind='bridge' AND json_extract(data,'$.event')='execution_diagnostic' ORDER BY seq DESC LIMIT 1",(task['id'],)).fetchone()
        result['worker_cleanup_confirmed']=json.loads(cleanup[0]).get('container_cleanup_confirmed') if cleanup else None
        if result['worker_cleanup_confirmed'] is False:result['progress_text']='worker cleanup unconfirmed'
        verification=self.store.db.execute("SELECT data FROM events WHERE task_id=? AND kind='verification' ORDER BY seq DESC LIMIT 1",(task['id'],)).fetchone()
        result['verification_status']=json.loads(verification[0]).get('status','not_verified') if verification else 'not_verified'
        return result

    async def tasks(self, request):
        rows = self.store.db.execute("SELECT * FROM tasks ORDER BY created DESC LIMIT 100").fetchall()
        return web.json_response({"v": 1, "tasks": [self.public_task(dict(t)) for t in rows]})

    async def task(self, request):
        return web.json_response(self.public_task(self.store.task(request.match_info["id"])))

    async def events(self, request):
        cursor = int(request.query.get("after", "0"))
        if cursor < 0:
            raise ValueError("invalid_cursor")
        task_id = request.query.get("task_id")
        data = self.store.events(cursor, task_id=task_id)
        return web.json_response({"v": 1, "events": data, "cursor": data[-1]["seq"] if data else cursor})

    async def pending(self, request):
        self.operator(request)
        rows = self.store.db.execute("SELECT * FROM tasks WHERE status='pending' ORDER BY created").fetchall()
        return web.json_response({"tasks": [dict(row) for row in rows]})

    async def decide(self, request):
        self.operator(request)
        body = await request.json()
        # No await between reading pending state and reserving preparing state.
        # Two local approvals must not launch the same task twice.
        task = self.store.task(request.match_info["id"])
        if task["status"] != "pending":
            raise ValueError("task_not_pending")
        if body.get("decision") not in {"approve", "reject"}:
            raise ValueError("invalid_decision")
        if body["decision"] == "reject":
            self.store.transition(task["id"], "rejected")
        else:
            if len(self.runners) >= 2:
                raise ValueError("concurrency_limit")
            if body.get("acknowledge_snapshot_and_provider") is not True:
                raise ValueError("operator_must_acknowledge_data_and_snapshot")
            if task["workspace"] and any(self.store.task(active)["workspace"]==task["workspace"] for active in self.runners):
                raise ValueError("workspace_busy_until_worker_stops")
            if task.get("parent_task_id") and not self.simulate and not self.fixed_test_command:
                if self.public_task(self.store.task(task["parent_task_id"])).get("worker_cleanup_confirmed") is not True:
                    raise ValueError("parent_worker_cleanup_unconfirmed")
            if task["workspace"] and self.store.db.execute("SELECT 1 FROM tasks WHERE workspace=? AND status IN ('running','preparing','cancel_requested')", (task["workspace"],)).fetchone():
                raise ValueError("workspace_busy")
            self.store.transition(task["id"], "preparing")
            runner = asyncio.create_task(self.run(task))
            self.runners[task["id"]] = runner
            runner.add_done_callback(lambda _: self.runners.pop(task["id"], None))
        return web.json_response(self.public_task(self.store.task(task["id"])))

    async def run(self, task):
        task_id = task["id"]
        try:
            root = Path(self.config["projects"][task["project"]]["path"])
            parent = self.store.task(task["parent_task_id"]) if task.get("parent_task_id") else None
            workspace = Path(parent["workspace"]) if parent else self.directory/"workspaces"/task_id
            # Local source must be quiescent; see SECURITY.md for the local attacker boundary.
            counts = {"reused_parent_workspace": True} if parent else snapshot_project(root, workspace)
            self.store.attach(task_id, workspace=str(workspace))
            self.store.event(task_id, "snapshot", counts)
            if self.store.task(task_id)["status"] == "cancel_requested":
                self.store.transition(task_id, "cancelled", source="cancel_before_agent_start")
                return
            if self.simulate:
                self.store.transition(task_id, "running", stage="SIMULATOR_NO_CODEX")
                for event in [{"type": "commandExecution", "lifecycle": "started"},
                              {"type": "commandExecution", "lifecycle": "completed", "exit_code": 0, "execution_status": "completed"}]:
                    await asyncio.sleep(0.02)
                    if self.store.task(task_id)["status"] == "cancel_requested":
                        self.store.transition(task_id, "cancelled", source="simulator")
                        return
                    self.store.event(task_id, "item", {**event, "simulated": True})
                self.store.event(task_id, "summary", {"text": "模拟任务完成；未调用模型或执行项目代码。", "simulated": True})
                self.store.transition(task_id, "completed", source="simulator")
            else:
                session_directory = self.directory/"worker_sessions_broker1"/workspace.name
                command = self.fixed_test_command or container_command(self.config, workspace, writable=task["action"]!="inspect", session_directory=session_directory)
                if not self.fixed_test_command:
                    # Validate model-created files before any permission operation.
                    # Parent worker cleanup is mandatory before reusing this tree.
                    prepare_worker_tree(workspace,writable=task["action"]!="inspect")
                    if os.name!="nt":
                        fd=os.open(session_directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                        try:os.fchmod(fd,0o777)
                        finally:os.close(fd)
                runtime_workspace = workspace if self.fixed_test_command else Path("/workspace")
                arguments={'model':self.config.get('codex_model'),'on_client':lambda c:self.clients.__setitem__(task_id,c),'resume_thread_id':parent['thread_id'] if parent else None}
                if self.fixed_test_command:
                    await run_codex(task,self.store,command,runtime_workspace,**arguments)
                else:
                    if self.config.get('allow_model_api') is not True:raise ValueError('model_api_disabled_by_desktop_owner')
                    async with ModelProxy(self.config.get('codex_model')) as proxy:
                        await run_codex(task,self.store,command,runtime_workspace,framed=True,model_proxy=proxy,
                                        child_env={'AGENTGLASS_PROXY_TOKEN':proxy.token},**arguments)
                        self.store.event(task_id,'bridge',{'event':'model_budget','calls':proxy.calls,'input_bytes':proxy.total})
        except Exception as exc:
            if self.store.task(task_id)["status"] not in TERMINAL:
                known={'real_codex_requires_docker_isolation','explicit_account_supported_model_required','model_api_key_not_configured','model_api_disabled_by_desktop_owner','legacy_auth_file_in_worker_session_refused'}
                code=str(exc) if isinstance(exc,ValueError) and str(exc) in known else type(exc).__name__
                self.store.transition(task_id,'failed',error=code)
        finally:
            self.clients.pop(task_id, None)

    async def cancel(self, request):
        task = self.store.task(request.match_info["id"])
        if task["status"] == "pending":
            self.store.transition(task["id"], "cancelled", source="before_launch")
        elif task["status"] not in TERMINAL and task["status"] != "cancel_requested":
            self.store.transition(task["id"], "cancel_requested")
            client = self.clients.get(task["id"])
            if client and task["turn_id"]:
                try:
                    await client.call("turn/interrupt", {"threadId": task["thread_id"], "turnId": task["turn_id"]})
                except Exception:
                    self.store.event(task["id"], "bridge", {"event": "cancel_delivery_uncertain"})
        return web.json_response(self.public_task(self.store.task(task["id"])))

    async def media_create(self, request):
        body = await request.json()
        media_id = self.media.create(request[DEVICE_KEY]["id"], size=body.get("size"), sha256=body.get("sha256"), mime=body.get("mime"), request_id=body.get("request_id"))
        info=self.media.info(request[DEVICE_KEY]["id"],media_id)
        return web.json_response({"id":media_id,"offset":info['received'],"complete":bool(info['complete'])}, status=201)

    async def media_info(self, request):
        return web.json_response(self.media.info(request[DEVICE_KEY]["id"], request.match_info["id"]))

    async def media_chunk(self, request):
        offset = int(request.query.get("offset", "-1"))
        data = await request.read()
        received = self.media.append(request[DEVICE_KEY]["id"], request.match_info["id"], offset, data)
        return web.json_response({"offset": received})

    async def media_commit(self, request):
        return web.json_response(self.media.commit(request[DEVICE_KEY]["id"], request.match_info["id"]))

    async def analyze(self, request):
        if self.config.get("allow_paid_cloud") is not True:
            raise web.HTTPForbidden(text='{"error":"cloud_disabled_by_desktop_owner"}', content_type="application/json")
        body = await request.json()
        if body.get("consent_upload_and_cost") is not True or body.get("kind") not in {"vision", "transcribe"}:
            raise ValueError("explicit_cloud_consent_required")
        question = body.get("question", "Describe the image briefly.")
        if not isinstance(question, str) or not 1 <= len(question) <= 1000:
            raise ValueError("invalid_question")
        self.throttle(("ai", request[DEVICE_KEY]["id"]), 3, 60)
        count = self.store.db.execute("SELECT COUNT(*) FROM audit WHERE json_extract(body,'$.kind')='cloud.requested' AND json_extract(body,'$.time')>?", (time.time()-86400,)).fetchone()[0]
        if count >= self.config.get("max_cloud_calls_per_day", 20):
            raise ValueError("daily_cloud_call_budget_exhausted")
        media_id = body.get("media_id")
        info = self.media.info(request[DEVICE_KEY]["id"], media_id)
        if not info["complete"] or info["size"] > 5*1024*1024:
            raise ValueError("completed_short_media_required")
        with self.store.db:
            self.store.audit("cloud.requested", {"kind": body["kind"], "media_id": media_id, "device": request[DEVICE_KEY]["id"]})
        content = (self.directory/"media"/(info["id"]+".bin")).read_bytes()
        text = await self.ai.analyze(body["kind"], content, info["mime"], question)
        return web.json_response({"v": 1, "text": text, "source": "OpenAI API", "kind": body["kind"]})

    async def index(self, request):
        return web.FileResponse(WEB/"index.html")

    async def health(self, request):
        return web.json_response({"v": 1, "service": "agentglass", "computer_name": str(self.config.get("computer_name","AgentGlass PC"))[:64], "mode": "SIMULATOR" if self.simulate else "codex"})

    async def close(self, app):
        for task in list(self.runners.values()):
            task.cancel()
        await asyncio.gather(*list(self.runners.values()), return_exceptions=True)
        self.store.close()

    def app(self, *, test_insecure=False):
        @web.middleware
        async def boundary(request, handler):
            try:
                if not request.secure and not test_insecure:
                    raise web.HTTPForbidden(text='{"error":"tls_required"}', content_type="application/json")
                # No wildcard CORS, no credentials in query strings, no browser cross-origin calls.
                if request.headers.get("Origin"):
                    expected = f"https://{request.host}"
                    if request.headers["Origin"] != expected:
                        raise web.HTTPForbidden()
                if request.path not in {"/", "/health", "/v1/pair"}:
                    value = request.headers.get("Authorization", "")
                    device = self.store.authenticate(value[7:]) if value.startswith("Bearer ") else None
                    if not device:
                        raise web.HTTPUnauthorized(text='{"error":"authentication_required"}', content_type="application/json")
                    request[DEVICE_KEY] = device
                if request.method == "POST":
                    if not isinstance(await request.json(), dict):
                        raise ValueError("object_required")
                response = await handler(request)
            except KeyError:
                response = web.json_response({"error": "not_found"}, status=404)
            except (ValueError, TypeError, json.JSONDecodeError):
                response = web.json_response({"error": "invalid_request_or_state"}, status=400)
            except web.HTTPException as exc:
                response = web.Response(status=exc.status, body=exc.body, headers=exc.headers)
            response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
                "Referrer-Policy": "no-referrer", "Strict-Transport-Security": "max-age=31536000"})
            return response

        app = web.Application(middlewares=[boundary], client_max_size=300*1024)
        app.add_routes([
            web.get("/", self.index), web.get("/health", self.health), web.post("/v1/pair", self.pair),
            web.get("/v1/projects", self.projects), web.get("/v1/tasks", self.tasks), web.post("/v1/tasks", self.create_task),
            web.get("/v1/tasks/{id}", self.task), web.post("/v1/tasks/{id}/cancel", self.cancel), web.get("/v1/events", self.events),
            web.get("/v1/operator/pending", self.pending), web.post("/v1/operator/tasks/{id}/decision", self.decide),
            web.post("/v1/media", self.media_create), web.get("/v1/media/{id}", self.media_info),
            web.put("/v1/media/{id}/chunks", self.media_chunk), web.post("/v1/media/{id}/commit", self.media_commit)])
        app.router.add_post("/v1/ai", self.analyze)
        app.on_cleanup.append(self.close)
        return app
