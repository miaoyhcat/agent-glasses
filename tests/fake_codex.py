"""Deliberate protocol fixture, not an AI model or a Codex replacement."""
import json
import sys

def send(value):
    print(json.dumps(value), flush=True)

thread = "fixture_thread"
for line in sys.stdin:
    message = json.loads(line)
    method, req = message.get("method"), message.get("id")
    if method == "initialize":
        send({"id": req, "result": {"userAgent": "FIXTURE", "platformFamily": "unix"}})
    elif method in {"thread/start", "thread/resume"}:
        if '--stall-thread' in sys.argv:
            print('bwrap permission denied CREDENTIAL_SENTINEL',file=sys.stderr,flush=True)
            continue
        if '--require-resume' in sys.argv and (method!='thread/resume' or message['params'].get('threadId')!=thread):
            raise SystemExit('Fixture requires resuming the existing thread')
        send({"id": req, "result": {"thread": {"id": thread}}})
    elif method == "turn/start":
        if '--stall-turn' in sys.argv:continue
        send({"id": req, "result": {"turn": {"id": "fixture_turn"}}})
        send({"method": "turn/started", "params": {"turn": {"id": "fixture_turn"}}})
        if '--model-proxy' in sys.argv:
            import os,urllib.request
            body=json.dumps({'model':'fixture-model','input':'public fixture','stream':True}).encode()
            request=urllib.request.Request('http://127.0.0.1:9041/v1/responses',body,{'Authorization':'Bearer '+os.environ['CODEXGLASSES_PROXY_TOKEN'],'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=10) as r:
                if b'fixture_payload' not in r.read():raise RuntimeError('broker_response_missing')
        send({"method": "item/reasoning/textDelta", "params": {"delta": "DO_NOT_EXPOSE_SECRET_REASONING"}})
        send({"id": "approval_1", "method": "item/commandExecution/requestApproval", "params": {"threadId": thread, "turnId": "fixture_turn", "command": "untrusted command"}})
    elif req == "approval_1" and "result" in message:
        if message["result"] != {"decision": "decline"}:
            raise SystemExit("Expected fail-closed decline")
        send({"method": "item/completed", "params": {"item": {"id": "cmd1", "type": "commandExecution", "status": "completed", "exitCode": 0, "command": "secret command", "aggregatedOutput": "secret output"}}})
        send({"method": "turn/plan/updated", "params": {"plan": [{"step": "Review", "status": "completed"}]}})
        send({"method": "item/completed", "params": {"item": {"id": "answer", "type": "agentMessage", "text": "Protocol fixture completed; no model executed."}}})
        send({"method": "turn/completed", "params": {"turn": {"id": "fixture_turn", "status": "completed"}}})
    elif method == "turn/interrupt":
        send({"id": req, "result": {}})
        send({"method": "turn/completed", "params": {"turn": {"id": "fixture_turn", "status": "interrupted"}}})
    elif req is not None and method:
        send({"id": req, "error": {"code": -32601, "message": "unsupported fixture method"}})
