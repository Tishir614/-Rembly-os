"""rembly_servers - what the Servers app (rembly-ssh) knows without any GUI: the saved connections, the command line for each kind of connection,
quick-connect parsing, SSH keys and the sshfs mount points. Passwords are NEVER stored: the program asks for them in the terminal (use keys where you can)."""
import glob, json, os, re, shlex, subprocess

KINDS = [('ssh', 'SSH (терминал сервера)'), ('serial', 'Последовательный порт (USB-UART, роутер, Raspberry Pi)'), ('rdp', 'RDP (удалённый рабочий стол Windows)'), ('vnc', 'VNC (удалённый рабочий стол)'),
         ('telnet', 'Telnet (старое оборудование, без шифрования)')]
DEFAULT_PORT = {'ssh': 22, 'rdp': 3389, 'vnc': 5900, 'telnet': 23}
BAUDS = ['9600', '19200', '38400', '57600', '115200', '230400']
SSH_OPTS = ['-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=4', '-o', 'ConnectTimeout=15', '-o', 'StrictHostKeyChecking=accept-new']


def home():
    return os.path.expanduser('~')


def store_path():
    return os.path.join(os.environ.get('REMBLY_CONFIG_DIR') or os.path.join(home(), '.config', 'rembly'), 'servers.json')


def new_conn(**kw):
    c = {'name': '', 'kind': 'ssh', 'host': '', 'port': 22, 'user': '', 'key': '', 'extra': '', 'startup': '', 'device': '/dev/ttyUSB0', 'baud': '115200',
         'domain': '', 'size': '', 'path': '/', 'notes': ''}
    c.update(kw); return c


def load():
    try: lst = json.load(open(store_path()))
    except Exception: return []
    return [new_conn(**{k: v for k, v in c.items() if k in new_conn()}) for c in lst if isinstance(c, dict)]


def save(conns):
    p = store_path(); os.makedirs(os.path.dirname(p), exist_ok=True); tmp = p + '.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f: json.dump(conns, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def parse_quick(text):
    """'user@host', 'user@host:2222', 'host', 'ssh://user@host:22', '[::1]:22' -> connection dict or None"""
    t = (text or '').strip()
    if not t: return None
    t = re.sub(r'^ssh://', '', t)
    user = ''
    if '@' in t: user, t = t.rsplit('@', 1)
    port = 22
    m = re.match(r'^\[([0-9A-Fa-f:]+)\](?::(\d+))?$', t)
    if m: host, port = m.group(1), int(m.group(2) or 22)
    elif t.count(':') == 1 and t.rsplit(':', 1)[1].isdigit(): host, p = t.rsplit(':', 1); port = int(p)
    else: host = t
    if not re.match(r'^[A-Za-z0-9._:-]+$', host) or not (0 < port < 65536): return None
    return new_conn(name=('%s@%s' % (user, host)) if user else host, host=host, port=port, user=user.strip())


def label(c):
    k = c['kind']
    if k == 'serial': return '%s @ %s' % (c['device'], c['baud'])
    who = ('%s@' % c['user']) if c.get('user') else ''
    return '%s%s%s' % (who, c['host'], (':%s' % c['port']) if int(c.get('port') or 0) not in (0, DEFAULT_PORT.get(k, 0)) else '')


def validate(c):
    """list of problems (Russian), empty when the connection can be saved"""
    p = []
    if not c.get('name', '').strip(): p.append('нет названия')
    if c['kind'] == 'serial':
        if not c.get('device', '').startswith('/dev/'): p.append('устройство должно быть вида /dev/ttyUSB0')
        if str(c.get('baud')) not in BAUDS and not str(c.get('baud')).isdigit(): p.append('скорость порта — число')
    else:
        if not re.match(r'^[A-Za-z0-9._:-]+$', c.get('host', '')): p.append('адрес сервера пуст или содержит недопустимые символы')
        try:
            if not (0 < int(c.get('port') or 0) < 65536): p.append('порт от 1 до 65535')
        except (TypeError, ValueError): p.append('порт — число')
    if c.get('user') and not re.match(r'^[A-Za-z0-9._\\-]+$', c['user']): p.append('имя пользователя содержит недопустимые символы')
    return p


def build_command(c):
    """argv that runs the connection inside a terminal (password prompts appear there). Raises ValueError for an invalid connection."""
    bad = validate(c)
    if bad: raise ValueError('; '.join(bad))
    k, host, port = c['kind'], c.get('host', ''), int(c.get('port') or DEFAULT_PORT.get(c['kind'], 0) or 0)
    if k == 'ssh':
        a = ['ssh'] + SSH_OPTS + ['-p', str(port)]
        if c.get('key'): a += ['-i', os.path.expanduser(c['key']), '-o', 'IdentitiesOnly=yes']
        if c.get('extra'): a += shlex.split(c['extra'])
        if c.get('startup'): a.append('-t')
        a.append(('%s@%s' % (c['user'], host)) if c.get('user') else host)
        if c.get('startup'): a.append(c['startup'])
        return a
    if k == 'serial':
        return ['picocom', '-b', str(c.get('baud') or '115200'), c['device']]
    if k == 'rdp':
        a = ['xfreerdp', '/v:%s:%d' % (host, port), '/cert:tofu', '/bpp:16', '+clipboard', '-wallpaper', '-aero', '-themes', '-decorations']
        a.append('/size:' + c['size'] if re.match(r'^\d{3,4}x\d{3,4}$', c.get('size') or '') else '/f')
        if c.get('user'): a.append('/u:' + c['user'])
        if c.get('domain'): a.append('/d:' + c['domain'])
        return a
    if k == 'vnc':
        return ['xtightvncviewer', '%s::%d' % (host, port), '-quality', '5', '-compresslevel', '6', '-encodings', 'tight hextile']
    if k == 'telnet':
        return ['telnet', host, str(port)]
    raise ValueError('неизвестный тип подключения')


def hint(c):
    return {'ssh': 'Выйти: exit или Ctrl+D. Пароль вводится здесь, в терминале (он нигде не сохраняется).',
            'serial': 'Выйти из picocom: Ctrl+A, затем Ctrl+X (на панели: Ctrl, затем A, затем Ctrl, затем X).',
            'rdp': 'Окно удалённого рабочего стола откроется отдельно; пароль вводится в этом терминале. Закрыть: закройте окно или Ctrl+C здесь.',
            'vnc': 'Окно VNC откроется отдельно; пароль VNC вводится в этом терминале. Закрыть: закройте окно или Ctrl+C здесь.',
            'telnet': 'Telnet не шифрует ничего, включая пароль: только для оборудования в своей сети. Выйти: Ctrl+], затем quit.'}.get(c['kind'], '')


def tools_missing(c):
    """names of programs this kind of connection needs that are not installed"""
    from shutil import which
    return [b for b in (build_command(c)[0],) if not which(b)]


def serial_devices():
    return sorted(glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyAMA*'))


# ---- ssh keys
def ssh_dir():
    return os.path.join(home(), '.ssh')


def keys():
    """[(private_path, public_path_or_None, fingerprint_or_'')] of the user's keys"""
    out = []
    for pub in sorted(glob.glob(os.path.join(ssh_dir(), '*.pub'))):
        priv = pub[:-4]
        if not os.path.exists(priv): continue
        fp = ''
        try: fp = subprocess.run(['ssh-keygen', '-lf', pub], capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception: pass
        out.append((priv, pub, fp))
    return out


def keygen_command(path, passphrase='', comment=None):
    """argv for ssh-keygen ed25519 (small, fast on the A53); the passphrase may be empty"""
    return ['ssh-keygen', '-q', '-t', 'ed25519', '-N', passphrase, '-C', comment or ('rembly@' + (os.uname().nodename or 'tablet')), '-f', path]


def copy_id_command(c, pub):
    a = ['ssh-copy-id', '-i', pub, '-p', str(int(c.get('port') or 22))] + ['-o', 'StrictHostKeyChecking=accept-new']
    a.append(('%s@%s' % (c['user'], c['host'])) if c.get('user') else c['host'])
    return a


# ---- sshfs
def mount_dir(c):
    n = re.sub(r'[^A-Za-z0-9._-]+', '_', c['name']).strip('_.')                                            # never '.' or '..'
    if not n:
        import hashlib; n = 'srv-' + hashlib.md5(c['name'].encode('utf8')).hexdigest()[:6]                  # a name without Latin letters (e.g. Cyrillic) still gets its own folder
    return os.path.join(home(), 'Servers', n)


def is_mounted(path):
    try: return os.path.ismount(path)
    except OSError: return False


def sshfs_command(c, target):
    a = ['sshfs', '-p', str(int(c.get('port') or 22)), '-o', 'reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,StrictHostKeyChecking=accept-new,idmap=user,follow_symlinks']
    if c.get('key'): a += ['-o', 'IdentityFile=' + os.path.expanduser(c['key']) + ',IdentitiesOnly=yes']
    a += ['%s%s:%s' % (('%s@' % c['user']) if c.get('user') else '', c['host'], c.get('path') or '/'), target]
    return a


def fuse_ready():
    """(ok, why): sshfs needs the program and /dev/fuse"""
    from shutil import which
    if not which('sshfs'): return False, 'не установлена программа sshfs (apt-get install sshfs)'
    if not os.path.exists('/dev/fuse'): return False, 'нет /dev/fuse: в ядре планшета FUSE включён, но узел устройства не создан (mknod /dev/fuse c 10 229; modprobe fuse)'
    return True, ''
