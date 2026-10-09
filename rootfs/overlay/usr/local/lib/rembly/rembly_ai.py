"""rembly_ai - the AI side of Rembly Code and rembly-ai (no GTK here, so it is testable on its own):
provider settings (your key, or a local model server), a streaming chat client for OpenAI-compatible servers and for the Anthropic API,
prompts, and the parsers/guards that decide what an AI answer may do (code blocks, <file> blocks, project plans, safe paths, command deny-list).

Nothing here talks to the network unless a function is called with a configured provider, and nothing from an answer is executed or written
by this module: the callers show every file and every command to the user first."""
import json, os, re, time, urllib.error, urllib.parse, urllib.request

ANTHROPIC_VERSION = '2023-06-01'
SYSTEM_FACTS = 'Rembly OS tablet: Ubuntu 20.04 armhf, Python 3.8, GCC 9, Node.js 10, no GPU, 2 GB RAM, touch screen.'

# name shown in the settings -> provider settings. Model names change often: they are EXAMPLES, the user can type any model the server offers.
PRESETS = [
    {'id': 'anthropic', 'title': 'Claude (Anthropic API, нужен ключ)', 'kind': 'anthropic', 'endpoint': 'https://api.anthropic.com', 'model': 'claude-sonnet-5-5', 'key': True,
     'note': 'Ключ создаётся в консоли Anthropic. Другие модели: claude-haiku-5-5 (быстрее и дешевле), claude-opus-5-5.'},
    {'id': 'openai', 'title': 'OpenAI (нужен ключ)', 'kind': 'openai', 'endpoint': 'https://api.openai.com/v1', 'model': 'gpt-4o-mini', 'key': True,
     'note': 'Имя модели — пример: возьмите актуальное из кнопки «Список моделей».'},
    {'id': 'openrouter', 'title': 'OpenRouter (один ключ, много моделей)', 'kind': 'openai', 'endpoint': 'https://openrouter.ai/api/v1', 'model': 'meta-llama/llama-3.3-70b-instruct:free', 'key': True,
     'note': 'Есть модели с пометкой :free (условия и лимиты смотрите на сайте провайдера, они меняются).'},
    {'id': 'groq', 'title': 'Groq (нужен ключ)', 'kind': 'openai', 'endpoint': 'https://api.groq.com/openai/v1', 'model': 'llama-3.3-70b-versatile', 'key': True, 'note': 'Очень быстрые ответы; условия бесплатного уровня смотрите у провайдера.'},
    {'id': 'gemini', 'title': 'Google Gemini (OpenAI-совместимый, нужен ключ)', 'kind': 'openai', 'endpoint': 'https://generativelanguage.googleapis.com/v1beta/openai', 'model': 'gemini-2.0-flash', 'key': True,
     'note': 'Ключ из Google AI Studio; название модели — пример.'},
    {'id': 'ollama', 'title': 'Локальная: Ollama на вашем ПК (без ключа)', 'kind': 'openai', 'endpoint': 'http://192.168.1.50:11434/v1', 'model': 'qwen2.5-coder:3b', 'key': False,
     'note': 'На ПК в той же сети: ollama serve (переменная OLLAMA_HOST=0.0.0.0), ollama pull qwen2.5-coder:3b. Впишите адрес вашего ПК.'},
    {'id': 'llamacpp', 'title': 'Локальная на планшете: llama.cpp server (127.0.0.1:8080)', 'kind': 'openai', 'endpoint': 'http://127.0.0.1:8080/v1', 'model': 'local', 'key': False,
     'note': 'Нужен свой собранный llama-server и маленькая модель (до ~0,5–1 млрд параметров на 2 ГБ ОЗУ); скорость порядка нескольких токенов в секунду. Не проверено на этом планшете.'},
    {'id': 'custom', 'title': 'Свой сервер (любой OpenAI-совместимый)', 'kind': 'openai', 'endpoint': '', 'model': '', 'key': False, 'note': 'LM Studio, vLLM, text-generation-webui, LiteLLM и т. п.'},
]
DEFAULTS = {'provider': 'custom', 'kind': 'openai', 'endpoint': '', 'model': '', 'key': '', 'max_tokens': 2048, 'temperature': 0.2, 'timeout': 0,
            'ctx_file': True, 'ctx_project': True, 'accepted_hosts': []}

# commands an AI may suggest are only ever OFFERED; these never even get a checkbox (partitions, flashing, wiping, pipes into a shell, ...)
DENY = re.compile(r'(\bmkfs|\bdd\b|fastboot|flash|nvram|nvdata|protect[12]|secro|/dev/(mmcblk|sd|mtd)|\bfdisk|\bparted|\bwipefs|\bshred\b|'
                  r'rm\s+-[a-z]*r[a-z]*f?\s+(/|~|\*|/\*|\.\.|/etc|/usr|/var|/root|/data|/home|/boot|/bin|/lib)(\s|$)|:\(\)\s*\{|\bshutdown|\bpoweroff|\bhalt\b|\breboot|'
                  r'chmod\s+-R\s+\S+\s+/(\s|$)|chown\s+-R\s+\S+\s+/(\s|$)|\bcurl\b[^|]*\|\s*(sudo\s+)?(ba)?sh|\bwget\b[^|]*\|\s*(sudo\s+)?(ba)?sh|>\s*/dev/|/etc/(passwd|shadow|sudoers)|\bpasswd\b|\buserdel|\bcrontab\s+-r)', re.I)
SENSITIVE_NAMES = re.compile(r'(^|/)(\.env(\..*)?|id_[a-z0-9]+|.*\.(pem|key|p12|pfx|kdbx|keystore)|\.netrc|\.npmrc|\.pypirc|credentials(\.json)?|secrets?(\.\w+)?|\.git-credentials|ai\.json)$', re.I)
MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES = 60, 200 * 1024, 1024 * 1024


# ---------------------------------------------------------------- settings
def cfg_dir():
    return os.environ.get('REMBLY_CONFIG_DIR') or os.path.expanduser('~/.config/rembly')


def cfg_path():
    return os.path.join(cfg_dir(), 'ai.json')


def load():
    """settings of this user; falls back to the system file /etc/rembly/ai.conf (what rembly-doctor/rembly-ai read) so one setup serves both"""
    c = dict(DEFAULTS)
    try:
        c.update(json.load(open(cfg_path())))
    except Exception:
        pass
    if not (c.get('endpoint') and c.get('model')):
        try:
            for line in open(os.environ.get('REMBLY_AI_CONF', '/etc/rembly/ai.conf')):
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1); k = k.strip().lower()
                    if k in ('endpoint', 'model', 'key') and v.strip(): c[k] = v.strip()
        except OSError:
            pass
    return c


def save(c):
    """~/.config/rembly/ai.json with mode 0600 (the key is stored in plain text on the device: there is no keyring on this system)"""
    os.makedirs(cfg_dir(), exist_ok=True)
    out = {k: c.get(k, DEFAULTS[k]) for k in DEFAULTS}
    tmp = cfg_path() + '.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f: json.dump(out, f, indent=2)
    os.replace(tmp, cfg_path())


def host_of(c):
    return urllib.parse.urlparse(c.get('endpoint') or '').hostname or ''


def is_local(c):
    h = host_of(c)
    if h in ('localhost', '::1') or h.endswith('.local') or h.startswith('127.') or h.startswith('10.') or h.startswith('192.168.'): return True
    m = re.match(r'172\.(\d+)\.', h)
    return bool(m and 16 <= int(m.group(1)) <= 31)


def configured(c):
    if not (c.get('endpoint') and c.get('model')): return False
    return bool(c.get('key')) or (c.get('kind') == 'openai' and is_local(c))


def describe(c):
    if not configured(c): return 'ИИ не настроен'
    return '%s · %s%s' % (c['model'], host_of(c) or '?', ' (локально)' if is_local(c) else '')


# ---------------------------------------------------------------- client
class AIError(Exception):
    """message is meant for the user (Russian), never contains the key"""


def _clean_err(body):
    try:
        j = json.loads(body)
        e = j.get('error', j)
        if isinstance(e, dict): e = e.get('message') or e.get('detail') or json.dumps(e)
        return str(e)[:300]
    except Exception:
        return (body or '').strip()[:300]


def _friendly(e, c):
    h = host_of(c) or 'сервер'
    if isinstance(e, urllib.error.HTTPError):
        try: body = e.read().decode('utf8', 'replace')
        except Exception: body = ''
        det = _clean_err(body); code = e.code
        tip = {401: 'ключ не принят: проверьте ключ в настройках ИИ', 403: 'доступ запрещён (ключ без прав, регион или квота)', 404: 'адрес или модель не найдены: проверьте endpoint и имя модели',
               408: 'сервер долго не отвечал', 413: 'запрос слишком большой: выключите «проект» в контексте или выделите меньше кода', 429: 'лимит запросов или закончилась квота'}.get(code)
        if tip is None: tip = 'ошибка сервера' if code >= 500 else 'запрос отклонён'
        return AIError('%s (HTTP %d): %s%s' % (h, code, tip, (' — ' + det) if det else ''))
    if isinstance(e, (TimeoutError,)) or 'timed out' in str(e):
        return AIError('%s не ответил вовремя. Локальной модели на слабом железе нужно больше времени: увеличьте таймаут в настройках ИИ.' % h)
    if isinstance(e, urllib.error.URLError):
        return AIError('нет связи с %s: %s. Проверьте Wi-Fi и адрес в настройках ИИ.' % (h, getattr(e, 'reason', e)))
    return AIError('%s: %s' % (type(e).__name__, e))


class Client:
    """one request at a time. chat() streams: on_text(chunk) is called from the calling thread for every piece; cancel() from another thread aborts."""
    def __init__(self, cfg):
        self.cfg = cfg; self._resp = None; self.cancelled = False

    def timeout(self):
        t = int(self.cfg.get('timeout') or 0)
        return t if t > 0 else (240 if is_local(self.cfg) else 90)

    def cancel(self):
        self.cancelled = True
        try:
            if self._resp is not None: self._resp.close()
        except Exception:
            pass

    def _headers(self):
        c = self.cfg; h = {'Content-Type': 'application/json', 'User-Agent': 'rembly-code'}
        if c.get('kind') == 'anthropic':
            h['x-api-key'] = c.get('key', ''); h['anthropic-version'] = ANTHROPIC_VERSION
        elif c.get('key'):
            h['Authorization'] = 'Bearer ' + c['key']
        return h

    def _url(self, what):
        e = (self.cfg.get('endpoint') or '').rstrip('/')
        if self.cfg.get('kind') == 'anthropic':
            if what == 'chat': return e + ('/messages' if e.endswith('/v1') else '/v1/messages')
            return e + ('/models' if e.endswith('/v1') else '/v1/models')
        if what == 'chat': return e if e.endswith('/chat/completions') else e + '/chat/completions'
        return e[:-len('/chat/completions')] + '/models' if e.endswith('/chat/completions') else e + '/models'

    def list_models(self):
        req = urllib.request.Request(self._url('models'), headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=20) as r: j = json.load(r)
        except Exception as e:
            raise _friendly(e, self.cfg)
        items = j.get('data') or j.get('models') or []
        ids = [(m.get('id') or m.get('name') or '') if isinstance(m, dict) else str(m) for m in items]
        return sorted(i for i in ids if i)

    def chat(self, messages, system='', max_tokens=None, on_text=None):
        """messages: [{'role': 'user'|'assistant', 'content': str}]; returns the whole answer text"""
        self.cancelled = False; c = self.cfg
        if not configured(c): raise AIError('ИИ не настроен: откройте настройки ИИ (кнопка ⚙) и введите ключ или адрес локального сервера.')
        mt = int(max_tokens or c.get('max_tokens') or 2048); msgs = self._normalise(messages)
        if c.get('kind') == 'anthropic':
            body = {'model': c['model'], 'max_tokens': mt, 'messages': msgs, 'stream': True}
            if system: body['system'] = system
            return self._post(body, on_text)
        body = {'model': c['model'], 'messages': ([{'role': 'system', 'content': system}] if system else []) + msgs, 'stream': True,
                'temperature': float(c.get('temperature', 0.2))}
        body['max_completion_tokens' if host_of(c) == 'api.openai.com' else 'max_tokens'] = mt
        for attempt in range(3):                                                  # servers differ on which sampling parameters they accept: adapt once or twice
            try:
                return self._post(body, on_text)
            except AIError as e:
                s = str(e).lower()
                if 'http 400' in s and attempt < 2:
                    if 'max_tokens' in s and 'max_tokens' in body: body['max_completion_tokens'] = body.pop('max_tokens'); continue
                    if 'temperature' in s and 'temperature' in body: body.pop('temperature'); continue
                raise

    @staticmethod
    def _normalise(messages):
        """alternating roles starting with user (the Anthropic API insists, other servers do not mind)"""
        out = []
        for m in messages:
            role = 'assistant' if m['role'] == 'assistant' else 'user'
            if out and out[-1]['role'] == role: out[-1]['content'] += '\n\n' + m['content']
            else: out.append({'role': role, 'content': m['content']})
        while out and out[0]['role'] != 'user': out.pop(0)
        return out

    def _post(self, body, on_text):
        req = urllib.request.Request(self._url('chat'), json.dumps(body).encode('utf8'), self._headers(), method='POST')
        parts = []
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout()); self._resp = resp
            ctype = resp.headers.get('Content-Type', '')
            if 'event-stream' not in ctype:                                       # a server that ignored stream:true
                j = json.loads(resp.read().decode('utf8', 'replace')); text = self._whole(j)
                if on_text and text: on_text(text)
                return text
            for raw in resp:
                if self.cancelled: break
                line = raw.decode('utf8', 'replace').strip()
                if not line.startswith('data:'): continue
                data = line[5:].strip()
                if data == '[DONE]': break
                try: j = json.loads(data)
                except ValueError: continue
                piece = self._piece(j)
                if piece:
                    parts.append(piece)
                    if on_text: on_text(piece)
        except AIError:
            raise
        except Exception as e:
            if self.cancelled: return ''.join(parts)
            raise _friendly(e, self.cfg)
        finally:
            try:
                if self._resp is not None: self._resp.close()
            except Exception:
                pass
            self._resp = None
        return ''.join(parts)

    def _piece(self, j):
        if self.cfg.get('kind') == 'anthropic':
            t = j.get('type')
            if t == 'content_block_delta':
                d = j.get('delta') or {}
                return d.get('text', '') if d.get('type') in (None, 'text_delta') else ''
            if t == 'error': raise AIError('Anthropic: ' + str((j.get('error') or {}).get('message', j))[:300])
            return ''
        if 'error' in j and not j.get('choices'): raise AIError('%s: %s' % (host_of(self.cfg), _clean_err(json.dumps(j))))
        ch = (j.get('choices') or [{}])[0]
        return (ch.get('delta') or {}).get('content') or ''

    def _whole(self, j):
        if self.cfg.get('kind') == 'anthropic':
            return ''.join(b.get('text', '') for b in j.get('content', []) if isinstance(b, dict))
        if 'error' in j and not j.get('choices'): raise AIError('%s: %s' % (host_of(self.cfg), _clean_err(json.dumps(j))))
        return ((j.get('choices') or [{}])[0].get('message') or {}).get('content') or ''


def test_connection(cfg):
    """(ok, text, seconds): a tiny real request, for the 'check' button"""
    t0 = time.time()
    try:
        out = Client(cfg).chat([{'role': 'user', 'content': 'Reply with the single word: ok'}], max_tokens=16)
        return True, (out.strip() or '(пустой ответ)')[:80], time.time() - t0
    except AIError as e:
        return False, str(e), time.time() - t0


# ---------------------------------------------------------------- prompts
def system_chat(project_rules=''):
    s = ('You are the coding assistant built into Rembly Code, an editor on a tablet (%s). Be concise and practical. Answer in the language of the user. '
         'Use fenced code blocks with a language tag for code. When the user asks you to create or change FILES, answer with one block per file in exactly this form, '
         'with the COMPLETE file content and no code fence inside: <file path="relative/path.ext">\\n...content...\\n</file>. Paths are relative to the project folder. '
         'Never invent library functions; if you are unsure, say so. Never suggest commands that touch partitions, flashing, system accounts or delete outside the project.' % SYSTEM_FACTS)
    return s + (('\n\nProject rules from the user:\n' + project_rules[:2000]) if project_rules else '')


SYSTEM_EDIT = ('You edit code in an editor. Reply with ONLY the replacement text in ONE fenced code block, nothing before or after: the replacement for the selected code '
               '(or the whole file when nothing is selected). Keep the existing style, indentation and language. Do not add explanations.')
SYSTEM_PLAN = ('You design small software projects for %s. Reply with ONLY one JSON object, no prose, no code fence: '
               '{"name": "short-kebab-case-name", "summary": "one sentence", "files": [{"path": "relative/path", "purpose": "what the file contains"}], '
               '"setup": ["optional shell commands that install dependencies"], "run": "one command that starts or tests the project"}. '
               'At most 12 files unless the task truly needs more; no binary files, no lock files, no node_modules, no virtualenvs. Prefer light dependencies (they run on a 2 GB tablet). '
               'Always include README.md with how to run it.' % SYSTEM_FACTS)
SYSTEM_FILE = ('You write ONE file of a software project. Reply with ONLY the complete content of that file inside a single fenced code block, nothing else. '
               'It must be consistent with the plan and with the files already written. Target: %s' % SYSTEM_FACTS)


# ---------------------------------------------------------------- parsing and guards
FENCE = re.compile(r'```([A-Za-z0-9_+.#-]*)[ \t]*\n(.*?)(?:\n)?```', re.S)
FILE_TAG = re.compile(r'<file\s+path\s*=\s*["\']([^"\'\n]+)["\']\s*>\n?(.*?)\n?</file>', re.S)


def extract_blocks(text):
    """[(lang, code)] of the fenced blocks; an unterminated last fence (answer cut off) is returned too"""
    out = [(m.group(1), m.group(2)) for m in FENCE.finditer(text)]
    if not out:
        m = re.search(r'```([A-Za-z0-9_+.#-]*)[ \t]*\n(.*)$', text, re.S)
        if m: out.append((m.group(1), m.group(2).rstrip()))
    return out


def first_code(text):
    """the code of the first fenced block; when the model forgot the fence, the whole answer"""
    b = extract_blocks(text)
    return b[0][1] if b else text.strip('\n')


def parse_files(text):
    """[(path, content)] from <file path="..."> blocks; a code fence the model put INSIDE a block is removed"""
    res = []
    for m in FILE_TAG.finditer(text):
        body = m.group(2)
        fm = FENCE.fullmatch(body.strip('\n'))
        if fm: body = fm.group(2)
        res.append((m.group(1).strip(), body))
    return res


def safe_rel(path):
    """normalised relative path inside the project, or None for anything that could escape it or hit something sensitive"""
    p = (path or '').replace('\\', '/').strip()
    if not p or '\0' in p or p.startswith(('/', '~')) or re.match(r'^[A-Za-z]:', p): return None
    p = os.path.normpath(p).replace('\\', '/')
    if p in ('.', '') or p.startswith('../') or p == '..' or '/../' in p or len(p) > 200: return None
    parts = p.split('/')
    if parts[0] == '.git' or '.git' in parts: return None
    return p


def check_files(files, existing_root=None):
    """validate a list of (path, content): returns (ok_list, problems) where ok_list is [(rel, content, exists)]"""
    ok, bad, total = [], [], 0
    seen = set()
    for path, content in files:
        rel = safe_rel(path)
        if rel is None: bad.append((path, 'недопустимый путь')); continue
        if rel in seen: bad.append((path, 'повтор пути')); continue
        if SENSITIVE_NAMES.search(rel): bad.append((path, 'секретный файл: ИИ не должен его создавать')); continue
        size = len(content.encode('utf8', 'replace'))
        if size > MAX_FILE_BYTES: bad.append((path, 'файл больше %d КБ' % (MAX_FILE_BYTES // 1024))); continue
        total += size
        if len(ok) >= MAX_FILES or total > MAX_TOTAL_BYTES: bad.append((path, 'слишком много файлов или данных за один раз')); continue
        seen.add(rel); exists = bool(existing_root and os.path.lexists(os.path.join(existing_root, rel)))
        if exists and os.path.islink(os.path.join(existing_root, rel)): bad.append((path, 'это символическая ссылка')); continue
        ok.append((rel, content, exists))
    return ok, bad


def write_files(root, files, backup_dir=None):
    """write [(rel, content)] under root; an existing file is first copied into backup_dir/<timestamp>/rel. returns the list of written relative paths"""
    stamp = time.strftime('%Y%m%d-%H%M%S'); done = []
    for rel, content in files:
        rel = safe_rel(rel)
        if rel is None: continue
        dst = os.path.join(root, rel)
        real = os.path.realpath(os.path.dirname(dst))
        if not (real == os.path.realpath(root) or real.startswith(os.path.realpath(root) + os.sep)): continue      # a symlinked directory pointing outside
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst) and backup_dir:
            b = os.path.join(backup_dir, stamp, rel); os.makedirs(os.path.dirname(b), exist_ok=True)
            with open(dst, 'rb') as s, open(b, 'wb') as d: d.write(s.read())
        with open(dst, 'w', encoding='utf8', newline='') as f: f.write(content if content.endswith('\n') or not content else content + '\n')
        done.append(rel)
    return done


def parse_plan(text):
    """the project plan from the model's answer: first balanced {...}; returns a dict with name/summary/files/setup/run or raises AIError"""
    s = text.strip()
    fm = FENCE.search(s)
    if fm: s = fm.group(2)
    i = s.find('{')
    if i < 0: raise AIError('ИИ не вернул план проекта (нет JSON)')
    depth = 0; instr = False; esc = False; end = -1
    for k in range(i, len(s)):
        ch = s[k]
        if instr:
            if esc: esc = False
            elif ch == '\\': esc = True
            elif ch == '"': instr = False
        elif ch == '"': instr = True
        elif ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0: end = k; break
    if end < 0: raise AIError('план проекта оборван (ответ ИИ обрезан): увеличьте «макс. токенов» в настройках ИИ')
    try: plan = json.loads(s[i:end + 1])
    except ValueError as e: raise AIError('план проекта не разобрался как JSON: %s' % e)
    files = []
    for f in plan.get('files') or []:
        if isinstance(f, str): f = {'path': f, 'purpose': ''}
        if isinstance(f, dict) and f.get('path'): files.append({'path': str(f['path']), 'purpose': str(f.get('purpose', ''))})
    if not files: raise AIError('в плане проекта нет файлов')
    setup = [str(c) for c in (plan.get('setup') or []) if isinstance(c, (str, int, float)) and str(c).strip()]
    run = plan.get('run') if isinstance(plan.get('run'), str) else ''
    return {'name': sanitize_name(str(plan.get('name') or 'project')), 'summary': str(plan.get('summary') or ''), 'files': files, 'setup': setup, 'run': run.strip()}


def sanitize_name(n):
    n = re.sub(r'[^A-Za-z0-9._-]+', '-', (n or '').strip()).strip('-._')[:48]
    return n or 'project'


def unique_dir(base, name):
    p = os.path.join(base, name); k = 2
    while os.path.exists(p) and (not os.path.isdir(p) or os.listdir(p)):
        p = os.path.join(base, '%s-%d' % (name, k)); k += 1
    return p


def command_allowed(cmd):
    """False for anything on the deny-list or that is not a single plain line"""
    c = (cmd or '').strip()
    return bool(c) and '\n' not in c and len(c) < 400 and not DENY.search(c)


def project_listing(root, limit=150):
    """relative file paths of the project for the AI's context (no hidden/build folders, no secret files)"""
    skip = {'.git', 'node_modules', '__pycache__', '.cache', '.venv', 'venv', '.idea', 'build', 'dist', 'target', '.mypy_cache', '.rembly-ai-backup'}
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = sorted(d for d in dn if d not in skip and not d.startswith('.'))
        for f in sorted(fn):
            rel = os.path.relpath(os.path.join(dp, f), root).replace(os.sep, '/')
            if f.startswith('.') and f not in ('.gitignore',): continue
            if SENSITIVE_NAMES.search(rel): continue
            out.append(rel)
            if len(out) >= limit: return out
    return out


def trim_history(hist, max_chars=24000, max_turns=10):
    h = hist[-max_turns * 2:]
    while len(h) > 2 and sum(len(m['content']) for m in h) > max_chars: h = h[2:]
    return h


def mask_secrets(t):
    """for text taken from the terminal before it goes to a server: passwords, tokens, API keys, private key blocks, Bearer headers"""
    t = re.sub(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----', '[private key removed]', t, flags=re.S)
    t = re.sub(r'(?i)\b(bearer|token|api[_-]?key|secret|passwd|password|pass|psk)\b(\s*[=:]\s*|\s+)([^\s\'"]{6,})', lambda m: m.group(1) + m.group(2) + '***', t)
    t = re.sub(r'\b(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,})\b', '***', t)
    return t
