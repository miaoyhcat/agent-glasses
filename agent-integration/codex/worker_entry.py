#!/usr/bin/env python3
"""Networkless Docker entry: multiplex official Codex stdio and bounded model IO.

No Unix socket, host TCP listener, provider credential, or original project is
mounted. The only credential in the worker is an expiring bounded job token.
"""
import base64,http.server,json,os,queue,signal,subprocess,sys,threading,uuid

class Worker:
    def __init__(self):self.output=threading.Lock();self.pending={};self.lock=threading.Lock();self.child=None
    def send(self,frame):
        with self.output:sys.stdout.write(json.dumps(frame,separators=(',',':'))+'\n');sys.stdout.flush()
    def input(self):
        try:
            for raw in sys.stdin:
                if len(raw)>4*1024*1024:break
                frame=json.loads(raw)
                if frame.get('channel')=='codex':
                    self.child.stdin.write((json.dumps(frame['payload'])+'\n').encode());self.child.stdin.flush()
                elif frame.get('channel')=='model':
                    with self.lock:target=self.pending.get(frame.get('id'))
                    if target is not None:target.put(frame,timeout=5)
        except (ValueError,OSError,queue.Full):pass
        finally:
            if self.child and self.child.poll() is None:self.child.terminate()
    def handler(self):
        worker=self
        class Relay(http.server.BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*_):pass
            def do_POST(self):
                if self.path!='/v1/responses':self.send_error(404);return
                if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Encoding','identity')!='identity':self.send_error(400);return
                try:length=int(self.headers.get('Content-Length','-1'))
                except ValueError:self.send_error(400);return
                if not 1<=length<=256*1024:self.send_error(413);return
                try:body=json.loads(self.rfile.read(length))
                except (ValueError,UnicodeError):self.send_error(400);return
                request_id=uuid.uuid4().hex;responses=queue.Queue(maxsize=4)
                with worker.lock:
                    if len(worker.pending)>=2:self.send_error(429);return
                    worker.pending[request_id]=responses
                try:
                    worker.send({'channel':'model','kind':'request','id':request_id,'token':self.headers.get('Authorization','').removeprefix('Bearer '),'body':body})
                    while True:
                        frame=responses.get(timeout=135);kind=frame.get('kind')
                        if kind=='start':
                            self.send_response(frame['status']);self.send_header('Content-Type',frame['content_type']);self.send_header('Connection','close');self.end_headers()
                        elif kind=='chunk':
                            self.wfile.write(base64.b64decode(frame['data'],validate=True));self.wfile.flush()
                            worker.send({'channel':'model','kind':'ack','id':request_id,'seq':frame['seq']})
                        elif kind in {'end','abort'}:break
                    self.close_connection=True
                except (OSError,ValueError,queue.Empty):self.close_connection=True
                finally:
                    with worker.lock:worker.pending.pop(request_id,None)
        return Relay
    def run(self,command):
        if not os.environ.get('AGENTGLASS_PROXY_TOKEN'):raise RuntimeError('missing_job_token')
        server=http.server.ThreadingHTTPServer(('127.0.0.1',9041),self.handler());server.daemon_threads=True
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        threading.Thread(target=self.input,daemon=True).start()
        def stop(*_):
            if self.child.poll() is None:self.child.terminate()
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        try:
            for line in self.child.stdout:
                if len(line)>4*1024*1024:raise RuntimeError('codex_frame_too_large')
                self.send({'channel':'codex','payload':json.loads(line)})
            return self.child.wait()
        finally:
            server.shutdown();server.server_close()
            if self.child.poll() is None:self.child.kill();self.child.wait()

def command():
    settings=['analytics.enabled=false','feedback.enabled=false','otel.exporter="none"','otel.metrics_exporter="none"','otel.trace_exporter="none"','web_search="disabled"','features.api_key_model_discovery=false','features.plugins=false','features.remote_plugin=false','features.apps=false','shell_environment_policy.inherit="none"','model_provider="agentglass_proxy"',
      'model_providers.agentglass_proxy={name="AgentGlass bounded Responses broker",base_url="http://127.0.0.1:9041/v1",env_key="AGENTGLASS_PROXY_TOKEN",wire_api="responses",requires_openai_auth=false}']
    result=['codex']
    for value in settings:result+=['-c',value]
    return result+['app-server']
if __name__=='__main__':raise SystemExit(Worker().run(command()))
