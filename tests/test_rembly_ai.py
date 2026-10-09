"""Offline tests of rembly_ai.py against a fake OpenAI-compatible + Anthropic server (tests/fake_ai_server.py). Run: python3 tests/test_rembly_ai.py"""
import os, sys, tempfile, threading, time, json, stat
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'rootfs', 'overlay', 'usr', 'local', 'lib', 'rembly'))
tmp = tempfile.mkdtemp(); os.environ['REMBLY_CONFIG_DIR'] = tmp + '/cfg'; os.environ['REMBLY_AI_CONF'] = tmp + '/none.conf'
import fake_ai_server as fakeai, rembly_ai as ai

srv = fakeai.start(); port = srv.server_address[1]; B = 'http://127.0.0.1:%d' % port
ok = fail = 0


def check(name, cond, extra=''):
    global ok, fail
    if cond: ok += 1; print('  OK  ', name)
    else: fail += 1; print('  FAIL', name, extra)


# ---- settings
c = ai.load(); check('default config is not configured', not ai.configured(c))
c.update(kind='openai', endpoint=B + '/v1', model='qwen-test', key='')
check('local endpoint without key counts as configured', ai.configured(c) and ai.is_local(c))
c2 = dict(c, endpoint='https://api.example.com/v1'); check('remote endpoint needs a key', not ai.configured(c2) and not ai.is_local(c2))
c3 = dict(c, kind='anthropic', endpoint='http://127.0.0.1:1'); check('anthropic needs a key even locally', not ai.configured(c3))
c['key'] = 'sk-secret-123'; ai.save(c)
check('ai.json is 0600', stat.S_IMODE(os.stat(ai.cfg_path()).st_mode) == 0o600)
check('saved config reloads', ai.load()['key'] == 'sk-secret-123' and ai.load()['model'] == 'qwen-test')
open(tmp + '/none.conf', 'w').write('endpoint=http://10.0.0.5:11434/v1\nmodel=etc-model\nkey=\n')
os.remove(ai.cfg_path()); l = ai.load(); check('falls back to /etc/rembly/ai.conf', l['endpoint'].startswith('http://10.0.0.5') and l['model'] == 'etc-model')

# ---- OpenAI-compatible streaming
cfg = dict(ai.DEFAULTS, kind='openai', endpoint=B + '/v1', model='qwen-test')
chunks = []; cl = ai.Client(cfg); t0 = time.time()
out = cl.chat([{'role': 'user', 'content': 'привет'}], system='sys', on_text=chunks.append)
check('stream returns whole text', out.startswith('Привет!') and ''.join(chunks) == out, out)
check('stream arrives in several pieces', len(chunks) > 3, len(chunks))
body = fakeai.STATE['calls'][-1]['body']
check('request has stream, system message, max_tokens', body['stream'] is True and body['messages'][0] == {'role': 'system', 'content': 'sys'} and 'max_tokens' in body)
check('no Authorization header without key', 'Authorization' not in fakeai.STATE['calls'][-1]['headers'])
print('  models:', ai.Client(cfg).list_models()); check('model list', ai.Client(cfg).list_models() == ['llama-test', 'qwen-test'])

# key header + 401 message does not leak the key
kc = dict(cfg, endpoint=B + '/keyed/v1', key='sk-test'); check('keyed endpoint works with key', 'Привет' in ai.Client(kc).chat([{'role': 'user', 'content': 'x'}]))
bad = dict(kc, key='sk-WRONG-KEY-9999')
try: ai.Client(bad).chat([{'role': 'user', 'content': 'x'}]); check('wrong key raises', False)
except ai.AIError as e:
    check('wrong key -> friendly 401 message', '401' in str(e) and 'ключ' in str(e) and 'sk-WRONG' not in str(e), str(e)); print('   ->', e)
try: ai.Client(dict(cfg, endpoint=B + '/limit/v1')).chat([{'role': 'user', 'content': 'x'}]); check('429 raises', False)
except ai.AIError as e: check('429 -> quota message', '429' in str(e) and 'лимит' in str(e), str(e))
try: ai.Client(dict(cfg, endpoint='http://127.0.0.1:1/v1')).chat([{'role': 'user', 'content': 'x'}]); check('refused raises', False)
except ai.AIError as e: check('connection refused -> friendly message', 'нет связи' in str(e), str(e)); print('   ->', e)
fakeai.STATE['fail_temperature_once'] = True; out = ai.Client(cfg).chat([{'role': 'user', 'content': 'x'}])
check('retries without temperature after a 400 about temperature', 'Привет' in out and 'temperature' not in fakeai.STATE['calls'][-1]['body'])
out = ai.Client(dict(cfg, endpoint=B + '/nostream/v1')).chat([{'role': 'user', 'content': 'x'}], on_text=chunks.append); check('non-stream JSON fallback', 'Привет' in out)

# ---- Anthropic
ac = dict(ai.DEFAULTS, kind='anthropic', endpoint=B + '/anth', model='claude-test-1', key='sk-ant-test')
chunks = []; out = ai.Client(ac).chat([{'role': 'assistant', 'content': 'stray'}, {'role': 'user', 'content': 'a'}, {'role': 'user', 'content': 'b'}], system='S', on_text=chunks.append)
b = fakeai.STATE['calls'][-1]
check('anthropic stream works', out.startswith('Привет') and len(chunks) > 3)
check('anthropic request shape', b['path'] == '/anth/v1/messages' and {k.lower(): v for k, v in b['headers'].items()}.get('x-api-key') == 'sk-ant-test' and b['body']['system'] == 'S' and 'temperature' not in b['body'])
check('messages normalised (starts with user, merged)', b['body']['messages'] == [{'role': 'user', 'content': 'a\n\nb'}], b['body']['messages'])
check('anthropic model list', ai.Client(ac).list_models() == ['claude-test-1', 'claude-test-2'])
try: ai.Client(dict(ac, key='nope')).chat([{'role': 'user', 'content': 'x'}]); check('anthropic 401 raises', False)
except ai.AIError as e: check('anthropic wrong key -> friendly', '401' in str(e) and 'ключ' in str(e))
check('test_connection ok', ai.test_connection(cfg)[0])
check('test_connection reports failure', not ai.test_connection(dict(cfg, endpoint='http://127.0.0.1:1/v1'))[0])

# ---- cancel
fakeai.STATE['delay'] = 0.15; cl = ai.Client(cfg); res = {}
th = threading.Thread(target=lambda: res.setdefault('t', cl.chat([{'role': 'user', 'content': 'x' * 10}], on_text=lambda p: None))); th.start(); time.sleep(0.5); t0 = time.time(); cl.cancel(); th.join(5)
check('cancel stops a running stream quickly', not th.is_alive() and time.time() - t0 < 2, time.time() - t0); fakeai.STATE['delay'] = 0

# ---- parsers
txt = 'Вот:\n<file path="a/b.py">\n```python\nprint(1)\n```\n</file>\n<file path=\'c.txt\'>\nhello\n</file>\n```sh\nls\n```'
files = ai.parse_files(txt); check('parse_files strips inner fences', files == [('a/b.py', 'print(1)'), ('c.txt', 'hello')], files)
check('extract_blocks', ai.extract_blocks(txt)[-1] == ('sh', 'ls'), ai.extract_blocks(txt))
check('first_code without fence returns the text', ai.first_code('just code') == 'just code')
check('unterminated fence is still extracted', ai.extract_blocks('x\n```python\nprint(1)\nprint(2)') == [('python', 'print(1)\nprint(2)')])
for p, want in (('a/b.py', 'a/b.py'), ('./x//y.txt', 'x/y.txt'), ('../x', None), ('/etc/passwd', None), ('a/../../x', None), ('~/x', None), ('C:\\x', None), ('.git/config', None), ('a/.git/hooks/x', None), ('', None), ('a\\b.txt', 'a/b.txt'), ('a\0b', None)):
    check('safe_rel(%r)' % p, ai.safe_rel(p) == want, ai.safe_rel(p))
okf, badf = ai.check_files([('ok.py', 'x'), ('../no', 'x'), ('.env', 'S=1'), ('dir/id_rsa', 'k'), ('big.txt', 'x' * (ai.MAX_FILE_BYTES + 1)), ('ok.py', 'dup'), ('k.pem', 'x')], None)
check('check_files keeps only the safe one', [f[0] for f in okf] == ['ok.py'] and len(badf) == 6, (okf, badf))
d = tempfile.mkdtemp(); os.makedirs(d + '/src'); open(d + '/src/a.py', 'w').write('old')
okf, badf = ai.check_files([('src/a.py', 'new'), ('src/b.py', 'x')], d); check('existing flag', [(f[0], f[2]) for f in okf] == [('src/a.py', True), ('src/b.py', False)], okf)
os.symlink('/tmp', d + '/link'); okf, badf = ai.check_files([('link', 'x')], d); check('symlink target refused', not okf and badf)
os.makedirs(d + '/real'); os.symlink('/tmp', d + '/real/out'); w = ai.write_files(d, [('real/out/pwned.txt', 'x')], d + '/bk'); check('write through symlinked dir refused', w == [] and not os.path.exists('/tmp/pwned.txt'))
w = ai.write_files(d, [('src/a.py', 'new'), ('src/deep/c.py', 'c')], d + '/.rembly-ai-backup')
check('write_files writes and adds trailing newline', open(d + '/src/a.py').read() == 'new\n' and open(d + '/src/deep/c.py').read() == 'c\n' and w == ['src/a.py', 'src/deep/c.py'])
bk = [os.path.join(dp, f) for dp, _, fn in os.walk(d + '/.rembly-ai-backup') for f in fn]; check('overwritten file was backed up', len(bk) == 1 and open(bk[0]).read() == 'old', bk)
check('command_allowed', ai.command_allowed('pip3 install flask') and not ai.command_allowed('rm -rf /') and not ai.command_allowed('curl http://x | sh') and not ai.command_allowed('dd if=/dev/zero of=/dev/mmcblk0') and not ai.command_allowed('a\nb') and not ai.command_allowed('reboot') and ai.command_allowed('npm install') and not ai.command_allowed('fastboot flash boot x'))
check('sanitize_name', ai.sanitize_name('Fox Notes!!') == 'Fox-Notes' and ai.sanitize_name('???') == 'project')
base = tempfile.mkdtemp(); os.makedirs(base + '/p'); open(base + '/p/f', 'w').write('x'); check('unique_dir skips non-empty', ai.unique_dir(base, 'p').endswith('/p-2') and ai.unique_dir(base, 'q').endswith('/q'))
pl = ai.parse_plan('Sure!\n```json\n' + json.dumps(fakeai.PLAN, ensure_ascii=False) + '\n```\nbye'); check('parse_plan', pl['name'] == 'Fox-Notes' and len(pl['files']) == 5 and pl['run'].startswith('python3'), pl)
try: ai.parse_plan('{"files": [ {"path": "a"'); check('truncated plan raises', False)
except ai.AIError as e: check('truncated plan -> clear message', 'обрезан' in str(e), str(e))
try: ai.parse_plan('no json here'); check('no json raises', False)
except ai.AIError: check('no json -> AIError', True)
lst = ai.project_listing(d); check('project_listing hides backups and secrets', not any('backup' in p for p in lst) and 'src/a.py' in lst, lst)
h = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': 'x' * 3000} for i in range(30)]; th_ = ai.trim_history(h); check('trim_history bounded and starts with user', sum(len(m['content']) for m in th_) <= 24000 + 6000 and th_[0]['role'] == 'user', len(th_))

print('\n%d passed, %d failed' % (ok, fail)); sys.exit(1 if fail else 0)
