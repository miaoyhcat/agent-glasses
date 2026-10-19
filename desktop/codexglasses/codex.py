"""Official Codex App Server stdio client, with fail-closed approval handling.

No raw reasoning or raw stdout is exposed as wearable progress. A protocol fake
can be injected in tests; it is never silently substituted for an installed CLI.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
from pathlib import Path


class RpcError(RuntimeError):
    pass


class RpcTimeout(RpcError):
    def __init__(self,method):
        self.method=method
        super().__init__('app_server_timeout:'+method)


class AppServer:
    def __init__(self,command:list[str],notify,*,timeout=30,child_env=None,framed=False,model_proxy=None):
        if not command or any(not isinstance(x, str) for x in command):
            raise ValueError("invalid_fixed_command")
        self.command, self.notify, self.timeout = command, notify, timeout
        self.pending, self.serial = {}, 0
        self.process = self.reader = self.stderr = None
        self.lock = asyncio.Lock()
        self.child_env=child_env
        self.framed,self.model_proxy=framed,model_proxy
        self.model_tasks={};self.model_acks={}
        self.stderr_bytes=0
        self.diagnostic_signals=set()
        self.cleanup_confirmed=None
        self.container_name=None
        if self.command[:2]==['docker','run'] and '--name' in self.command:
            name=self.command[self.command.index('--name')+1]
            if not re.fullmatch(r'codexglasses-[0-9a-f]{32}',name):raise ValueError('invalid_owned_container_name')
            self.container_name=name

    def diagnostics(self):
        return {'stderr_bytes':self.stderr_bytes,'signals':sorted(self.diagnostic_signals),
                'exit_code':self.process.returncode if self.process else None,'container_cleanup_confirmed':self.cleanup_confirmed}

    async def start(self):
        # Never shell=True. Credentials remain in the user's Codex installation.
        self.process = await asyncio.create_subprocess_exec(*self.command,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, limit=4*1024*1024,
            env={**os.environ,**self.child_env} if self.child_env is not None else None)
        self.reader = asyncio.create_task(self._read())
        self.stderr = asyncio.create_task(self._drain_stderr())
        result = await self.call("initialize", {"clientInfo": {
            "name": "codexglasses", "title": "CodexGlasses personal bridge", "version": "0.2.0"}})
        await self.send({"method": "initialized", "params": {}})
        return result

    async def send(self, payload):
        await self.send_wire({'channel':'codex','payload':payload} if self.framed else payload)

    async def send_wire(self,payload):
        async with self.lock:
            if self.process is None or self.process.returncode is not None:
                raise RpcError("app_server_not_running")
            self.process.stdin.write((json.dumps(payload, separators=(",", ":"))+"\n").encode())
            await self.process.stdin.drain()

    async def _model_request(self,frame):
        request_id=frame['id'];sequence=0
        async def emit(value):
            nonlocal sequence
            if value.get('kind')!='chunk':await self.send_wire(value);return
            sequence+=1;value={**value,'seq':sequence};key=(request_id,sequence)
            future=asyncio.get_running_loop().create_future();self.model_acks[key]=future
            try:
                await self.send_wire(value);await asyncio.wait_for(future,15)
            finally:self.model_acks.pop(key,None)
        try:await self.model_proxy.stream(frame,emit)
        except (OSError,RpcError,asyncio.TimeoutError):
            await self.notify('bridge/modelTransportFailed',{})
        finally:self.model_tasks.pop(request_id,None)

    async def call(self, method, params):
        self.serial += 1
        request_id = self.serial
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.send({"id": request_id, "method": method, "params": params})
            try:
                return await asyncio.wait_for(future,self.timeout)
            except asyncio.TimeoutError as exc:
                raise RpcTimeout(method) from exc
        finally:
            self.pending.pop(request_id, None)

    async def _drain_stderr(self):
        tail=b''
        while chunk:=await self.process.stderr.read(4096):
            self.stderr_bytes+=len(chunk)
            value=(tail+chunk).lower();tail=value[-80:]
            # Only constant categories survive; never retain raw stderr or tokens.
            for term,signal in [(b'unauthorized','authentication_error'),(b'401','authentication_error'),
                                (b'permission denied','permission_denied'),(b'bwrap','sandbox_setup'),
                                (b'operation not permitted','operation_not_permitted'),(b'socket','socket_error'),
                                (b'no space left','disk_full'),(b'connection refused','connection_refused')]:
                if term in value:self.diagnostic_signals.add(signal)

    async def _read(self):
        error = "app_server_disconnected"
        try:
            while line := await self.process.stdout.readline():
                message = json.loads(line)
                if self.framed:
                    if message.get('channel')=='model':
                        kind=message.get('kind');request_id=message.get('id')
                        if kind=='ack':
                            future=self.model_acks.get((request_id,message.get('seq')))
                            if future and not future.done():future.set_result(True)
                        elif kind=='request':
                            if not self.model_proxy or not isinstance(request_id,str) or not re.fullmatch(r'[0-9a-f]{32}',request_id) or request_id in self.model_tasks or len(self.model_tasks)>=2:
                                raise RpcError('invalid_model_broker_request')
                            self.model_tasks[request_id]=asyncio.create_task(self._model_request(message))
                        else:raise RpcError('invalid_model_broker_frame')
                        continue
                    if message.get('channel')!='codex' or not isinstance(message.get('payload'),dict):raise RpcError('invalid_worker_frame')
                    message=message['payload']
                if "method" in message:
                    if "id" in message:
                        method = message["method"]
                        if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
                            await self.send({"id": message["id"], "result": {"decision": "decline"}})
                            await self.notify("bridge/approvalDenied", {"method": method})
                        elif method == "item/permissions/requestApproval":
                            await self.send({"id": message["id"], "result": {"permissions": {}, "scope": "turn"}})
                            await self.notify("bridge/approvalDenied", {"method": method})
                        else:
                            await self.send({"id": message["id"], "error": {"code": -32601, "message": "Unsupported request; refused"}})
                            await self.notify("bridge/unsupportedRequest", {"method": method})
                    else:
                        await self.notify(message["method"], message.get("params", {}))
                elif "id" in message:
                    future = self.pending.get(message["id"])
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(RpcError(str(message["error"].get("message", "rpc_error"))[:300]))
                        else:
                            future.set_result(message.get("result", {}))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error = f"app_server_protocol_error:{type(exc).__name__}"
        finally:
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(RpcError(error))
            await self.notify("bridge/disconnected", {"error": error})

    async def close(self):
        for model_task in list(self.model_tasks.values()):model_task.cancel()
        for model_task in list(self.model_tasks.values()):
            with contextlib.suppress(asyncio.CancelledError):await model_task
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        for task in [self.reader, self.stderr]:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        # Killing the Docker CLI alone does not prove its container stopped.
        # Only our fresh random, labelled worker name may be removed here.
        if self.container_name:
            self.cleanup_confirmed=await remove_owned_container(self.container_name)


async def remove_owned_container(name):
    if not re.fullmatch(r'codexglasses-[0-9a-f]{32}',name):raise ValueError('invalid_owned_container_name')
    process=None
    try:
        process=await asyncio.create_subprocess_exec('docker','rm','--force',name,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        _,error=await asyncio.wait_for(process.communicate(),8)
        return process.returncode==0 or b'No such container' in error
    except (OSError,asyncio.TimeoutError):
        if process and process.returncode is None:
            process.kill();await process.wait()
        return False


def sandbox(workspace: Path, writable: bool):
    if writable:
        return {"type": "workspaceWrite", "writableRoots": [str(workspace)],
                "excludeTmpdirEnvVar": True, "excludeSlashTmp": True, "networkAccess": False}
    return {"type": "readOnly", "networkAccess": False}


async def run_codex(task,store,command,workspace:Path,*,model=None,on_client=None,timeout=1800,resume_thread_id=None,rpc_timeout=30,child_env=None,framed=False,model_proxy=None):
    finished = asyncio.Event()
    terminal_received = False

    async def notify(method, params):
        nonlocal terminal_received
        task_id = task["id"]
        current = store.task(task_id)["status"]
        if current in {"completed", "failed", "cancelled", "unknown"}:
            return
        if method in {"item/started", "item/completed"}:
            item = params.get("item", {})
            kind = item.get("type")
            if kind in {"commandExecution", "fileChange", "agentMessage"}:
                # Structured metadata only. No command arguments, raw output or reasoning.
                data = {"type": kind, "id": item.get("id"), "lifecycle": method.split("/")[1]}
                if kind == "commandExecution" and method == "item/completed":
                    data.update(exit_code=item.get("exitCode"), execution_status=item.get("status"))
                store.event(task_id, "item", data)
                if kind == "agentMessage" and method == "item/completed" and isinstance(item.get("text"), str):
                    store.event(task_id, "summary", {"text": item["text"][:1600], "source": "agentMessage"})
        elif method == "turn/plan/updated":
            # Only the public plan, never the reasoning fields.
            plan = [{"step": str(p.get("step", ""))[:160], "status": p.get("status")}
                    for p in params.get("plan", [])[:8]]
            store.event(task_id, "plan", {"plan": plan})
        elif method == "turn/completed":
            turn = params.get("turn", {})
            status = {"completed": "completed", "interrupted": "cancelled", "failed": "failed"}.get(turn.get("status"), "unknown")
            terminal_received = True
            store.transition(task_id, status, source="turn/completed")
            finished.set()
        elif method.startswith("bridge/"):
            store.event(task_id, "bridge", {"event": method, **params})
            if method == "bridge/disconnected" and not terminal_received:
                store.transition(task_id, "unknown", source="transport_lost")
                finished.set()

    client=AppServer(command,notify,timeout=rpc_timeout,child_env=child_env,framed=framed,model_proxy=model_proxy)
    phase='initialize'
    if on_client:
        on_client(client)
    try:
        info = await client.start()
        store.event(task["id"], "bridge", {"event": "initialized", "platform": info.get("platformFamily", "unknown")})
        params = {"cwd": str(workspace), "approvalPolicy": "never", "sandbox": "read-only"}
        # sandbox preset strings are CLI kebab-case; SandboxPolicy above is tagged camelCase.
        if model:
            params["model"] = model
        if resume_thread_id:
            params["threadId"] = resume_thread_id
        phase='thread_resume' if resume_thread_id else 'thread_start'
        response = await client.call("thread/resume" if resume_thread_id else "thread/start", params)
        thread_id = response["thread"]["id"]
        store.attach(task["id"], thread_id=thread_id)
        if store.task(task["id"])["status"] == "cancel_requested":
            store.transition(task["id"], "cancelled", source="cancel_before_turn")
            return
        store.transition(task["id"], "running", stage="codex_turn_requested")
        intent = {"inspect": "Review this snapshot for bugs. Do not modify files.",
                  "fix": "Fix the requested issue in this disposable snapshot. Do not publish, send data or access the network.",
                  "test": "Run relevant existing tests in this disposable snapshot. Report exact test results."}[task["action"]]
        phase='turn_start'
        response = await client.call("turn/start", {
            "threadId": thread_id, "cwd": str(workspace), "approvalPolicy": "never",
            "sandboxPolicy": sandbox(workspace, task["action"] != "inspect"),
            "input": [{"type": "text", "text": intent+"\n\nUser request:\n"+task["prompt"]}]})
        store.attach(task["id"], turn_id=response["turn"]["id"])
        if store.task(task["id"])["status"] == "cancel_requested":
            await client.call("turn/interrupt", {"threadId": thread_id, "turnId": response["turn"]["id"]})
        phase='awaiting_turn_completion'
        await asyncio.wait_for(finished.wait(), timeout)
    except RpcTimeout:
        if store.task(task["id"])["status"] not in {"completed", "failed", "cancelled", "unknown"}:
            status='failed' if phase in {'initialize','thread_start','thread_resume'} else 'unknown'
            store.transition(task['id'],status,source='rpc_timeout',stage=phase)
    except asyncio.TimeoutError:
        if store.task(task["id"])["status"] not in {"completed", "failed", "cancelled", "unknown"}:
            store.transition(task["id"], "unknown", source="timeout_no_completion_evidence")
    except Exception as exc:
        if store.task(task["id"])["status"] not in {"completed", "failed", "cancelled", "unknown"}:
            status='unknown' if phase in {'turn_start','awaiting_turn_completion'} else 'failed'
            store.transition(task["id"],status,error=type(exc).__name__,stage=phase)
    finally:
        await client.close()
        store.event(task['id'],'bridge',{'event':'execution_diagnostic','stage':phase,**client.diagnostics()})
