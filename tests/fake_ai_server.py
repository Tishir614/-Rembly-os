"""A fake OpenAI-compatible + Anthropic server for tests. Replies depend on the system prompt, so the whole project-creation flow can run offline."""
import json, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PLAN = {'name': 'Fox Notes!!', 'summary': 'tiny notes CLI', 'files': [{'path': 'README.md', 'purpose': 'how to run'}, {'path': 'notes/app.py', 'purpose': 'the CLI'},
        {'path': '../evil.txt', 'purpose': 'escape attempt'}, {'path': '.env', 'purpose': 'secrets'}, {'path': 'tests/test_app.py', 'purpose': 'unit test'}],
        'setup': ['pip3 install -r requirements.txt', 'rm -rf /'], 'run': 'python3 notes/app.py'}
STATE = {'calls': [], 'fail_temperature_once': False, 'delay': 0.0}


def last_user(body):
    msgs = body.get('messages', [])
    return msgs[-1]['content'] if msgs else ''


def system_of(body, anth=False):
    if anth: return body.get('system', '')
    return next((m['content'] for m in body.get('messages', []) if m['role'] == 'system'), '')


def reply_for(body, anth=False):
    sysm, user = system_of(body, anth), last_user(body)
    if 'design small software projects' in sysm: return json.dumps(PLAN)
    if 'write ONE file' in sysm:
        if 'notes/app.py' in user.split('TARGET FILE:')[-1]: return '```python\nimport sys\nprint("fox notes", sys.argv[1:])\n```'
        if 'README.md' in user.split('TARGET FILE:')[-1]: return '```markdown\n# Fox Notes\nRun: python3 notes/app.py\n```'
        return '```python\ndef test_ok():\n    assert True\n```'
    if 'edit code in an editor' in sysm: return '```python\ndef add(a, b):\n    """Add two numbers."""\n    return a + b\n```'
    if 'create files' in user.lower() or 'создай файл' in user.lower():
        return 'Вот файл:\n<file path="hello.py">\nprint("hi")\n</file>\nи ещё\n```sh\npython3 hello.py\n```'
    return 'Привет! Это ответ поддельного ИИ. Вы спросили: ' + user[-60:]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send_json(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path.endswith('/models'):
            if self.path.startswith('/anth'):
                if self.headers.get('x-api-key') != 'sk-ant-test': return self.send_json(401, {'type': 'error', 'error': {'type': 'authentication_error', 'message': 'invalid x-api-key'}})
                return self.send_json(200, {'data': [{'id': 'claude-test-1'}, {'id': 'claude-test-2'}]})
            return self.send_json(200, {'data': [{'id': 'qwen-test'}, {'id': 'llama-test'}]})
        self.send_json(404, {'error': 'nope'})

    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0)); body = json.loads(self.rfile.read(n) or b'{}')
        anth = self.path.startswith('/anth')
        STATE['calls'].append({'path': self.path, 'headers': dict(self.headers), 'body': body})
        if anth:
            if self.headers.get('x-api-key') != 'sk-ant-test': return self.send_json(401, {'type': 'error', 'error': {'type': 'authentication_error', 'message': 'invalid x-api-key'}})
            if self.headers.get('anthropic-version') != '2023-06-01': return self.send_json(400, {'error': {'message': 'bad version'}})
        else:
            if self.path.startswith('/keyed') and self.headers.get('Authorization') != 'Bearer sk-test': return self.send_json(401, {'error': {'message': 'Incorrect API key provided'}})
            if STATE['fail_temperature_once'] and 'temperature' in body:
                STATE['fail_temperature_once'] = False; return self.send_json(400, {'error': {'message': "Unsupported value: 'temperature' does not support 0.2 with this model"}})
            if self.path.startswith('/limit'): return self.send_json(429, {'error': {'message': 'Rate limit reached'}})
        text = reply_for(body, anth)
        if not body.get('stream') or self.path.startswith('/nostream'):
            if anth: return self.send_json(200, {'content': [{'type': 'text', 'text': text}]})
            return self.send_json(200, {'choices': [{'message': {'role': 'assistant', 'content': text}}]})
        self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
        pieces = [text[i:i + 7] for i in range(0, len(text), 7)]
        if anth:
            self.wfile.write(b'event: message_start\ndata: {"type":"message_start"}\n\n')
        for p in pieces:
            if STATE['delay']: time.sleep(STATE['delay'])
            obj = ({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': p}} if anth else {'choices': [{'delta': {'content': p}}]})
            try:
                self.wfile.write(('data: ' + json.dumps(obj) + '\n\n').encode()); self.wfile.flush()
            except Exception:
                return
        self.wfile.write(b'data: {"type":"message_stop"}\n\n' if anth else b'data: [DONE]\n\n')


def start(port=0):
    srv = ThreadingHTTPServer(('127.0.0.1', port), H); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv
