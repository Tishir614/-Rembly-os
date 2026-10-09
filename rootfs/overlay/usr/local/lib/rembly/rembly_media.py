"""Media helpers for rembly-player (no GTK here, so everything can be tested headless):
library scan, tag cache, covers, thumbnails (pictures and video frames), waveform for the seek bar, and a small mpv JSON-IPC client.
Everything is built for 2 GB RAM and a 4x A53: lazy, cached on disk, run at the lowest priority, with time limits."""
import hashlib, json, os, socket, subprocess, tempfile, threading, time

AUDIO = ('.mp3', '.flac', '.ogg', '.oga', '.opus', '.m4a', '.aac', '.wav', '.wma', '.mka')
VIDEO = ('.mp4', '.mkv', '.webm', '.avi', '.mov', '.m4v', '.mpg', '.mpeg', '.3gp', '.flv', '.ts', '.wmv')
IMAGE = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
EXT = {'audio': AUDIO, 'video': VIDEO, 'image': IMAGE}
HOME = os.path.expanduser('~')
CACHE = os.path.join(HOME, '.cache', 'rembly')
SKIP = {'.git', 'node_modules', '__pycache__', 'lost+found', 'Android', 'proc', 'sys', 'dev', '.cache', '.thumbnails', '$RECYCLE.BIN', 'System Volume Information'}
FOLDER = {'audio': ('Music', 'Музыка'), 'video': ('Videos', 'Видео', 'Movies'), 'image': ('Pictures', 'Изображения', 'Photos', 'DCIM')}
COVER_NAMES = ('cover', 'folder', 'front', 'album', 'albumart')
MPV_BASE = ['--no-config', '--idle=yes', '--force-window=no', '--no-terminal', '--osc=no', '--no-input-default-bindings', '--audio-display=no',
            '--keep-open=yes', '--cache=yes', '--demuxer-max-bytes=24MiB', '--demuxer-max-back-bytes=8MiB', '--volume-max=130']
# low-end video profile: x11 output (no GPU), software decode, drop late frames instead of stalling, skip the loop filter on non-reference frames
MPV_VIDEO = ['--vo=x11', '--hwdec=no', '--framedrop=vo', '--vd-lavc-fast', '--vd-lavc-skiploopfilter=nonref', '--vd-lavc-threads=4', '--scale=bilinear', '--cscale=bilinear',
             '--dscale=bilinear', '--video-sync=audio', '--sub-auto=fuzzy', '--sub-font=Noto Sans', '--sub-font-size=44', '--sub-border-size=2']


def kind_of(path):
    e = os.path.splitext(path)[1].lower()
    for k, exts in EXT.items():
        if e in exts: return k
    return None


def roots(kind):
    """folders worth looking in: the user's own, then every mounted drive (rembly-automount mounts under /media)"""
    out = []
    for n in FOLDER[kind]:
        p = os.path.join(HOME, n)
        if os.path.isdir(p): out.append(p)
    for base in ('/media', '/mnt', '/run/media'):
        try:
            for e in sorted(os.scandir(base), key=lambda e: e.name):
                if e.is_dir(follow_symlinks=False) and os.path.ismount(e.path): out.append(e.path)
        except OSError: pass
    dl = os.path.join(HOME, 'Downloads')
    if os.path.isdir(dl): out.append(dl)
    seen, res = set(), []
    for r in out:
        rp = os.path.realpath(r)
        if rp not in seen: seen.add(rp); res.append(r)
    return res


def scan(kind, folders, limit=30000, depth=7):
    """[(path, size, mtime)] sorted by path; iterative, bounded, skips hidden/system folders"""
    exts = EXT[kind]; res = []; stack = [(r, 0) for r in reversed(folders)]
    while stack and len(res) < limit:
        d, lvl = stack.pop()
        try: ents = list(os.scandir(d))
        except OSError: continue
        sub = []
        for e in ents:
            n = e.name
            if n.startswith('.') or n in SKIP: continue
            try:
                if e.is_dir(follow_symlinks=False):
                    if lvl < depth: sub.append((e.path, lvl + 1))
                elif n.lower().endswith(exts):
                    st = e.stat(); res.append((e.path, st.st_size, st.st_mtime))
            except OSError: continue
        stack.extend(reversed(sub))
    res.sort(key=lambda t: t[0].lower()); return res


def fmt_time(s):
    try: s = int(max(0, s))
    except (TypeError, ValueError): return '--:--'
    return ('%d:%02d:%02d' % (s // 3600, s // 60 % 60, s % 60)) if s >= 3600 else ('%d:%02d' % (s // 60, s % 60))


# ---------------------------------------------------------------- tags
class Tags:
    """title/artist/album/duration per audio file, cached in ~/.cache/rembly/media-tags.json (key: path, valid while size and mtime match)"""
    def __init__(self, cache_dir=CACHE):
        self.f = os.path.join(cache_dir, 'media-tags.json'); self.d = {}; self.dirty = 0; self.lock = threading.Lock()
        try: self.d = json.load(open(self.f))
        except Exception: self.d = {}

    def cached(self, path, size, mtime):
        e = self.d.get(path)
        return e if e and e.get('s') == size and e.get('m') == int(mtime) else None

    def read(self, path, size=0, mtime=0):
        e = self.cached(path, size, mtime)
        if e: return e
        e = {'s': size, 'm': int(mtime), 't': os.path.splitext(os.path.basename(path))[0], 'a': '', 'b': '', 'd': 0.0}
        try:
            import mutagen
            f = mutagen.File(path, easy=True)
            if f is not None:
                def first(k):
                    v = f.get(k); return str(v[0]).strip() if v else ''
                e['t'] = first('title') or e['t']; e['a'] = first('artist') or first('albumartist'); e['b'] = first('album')
                if getattr(f, 'info', None) and getattr(f.info, 'length', None): e['d'] = float(f.info.length)
        except Exception: pass
        with self.lock: self.d[path] = e; self.dirty += 1
        return e

    def save(self):
        with self.lock:
            if not self.dirty: return
            try:
                os.makedirs(os.path.dirname(self.f), exist_ok=True)
                if len(self.d) > 60000: self.d = dict(list(self.d.items())[-40000:])
                tmp = self.f + '.tmp'; json.dump(self.d, open(tmp, 'w')); os.replace(tmp, self.f); self.dirty = 0
            except OSError: pass


def cover_bytes(path):
    """embedded cover (ID3 APIC / MP4 covr / FLAC picture), else cover.jpg & co. from the same folder; None when there is none"""
    try:
        import mutagen
        f = mutagen.File(path)
        if f is not None:
            tags = getattr(f, 'tags', None)
            if hasattr(f, 'pictures') and f.pictures: return bytes(f.pictures[0].data)
            if tags is not None:
                for k in list(tags.keys()):
                    if str(k).startswith('APIC'): return bytes(tags[k].data)
                if 'covr' in tags and tags['covr']: return bytes(tags['covr'][0])
    except Exception: pass
    d = os.path.dirname(path)
    try:
        for e in os.scandir(d):
            n, x = os.path.splitext(e.name.lower())
            if n in COVER_NAMES and x in ('.jpg', '.jpeg', '.png'):
                with open(e.path, 'rb') as fh: return fh.read(8_000_000)
    except OSError: pass
    return None


# ---------------------------------------------------------------- thumbnails
def _thumb_path(path, size, cache_dir):
    try: st = os.stat(path); key = '%s|%d|%d|%d' % (path, st.st_size, int(st.st_mtime), size)
    except OSError: key = '%s|%d' % (path, size)
    return os.path.join(cache_dir, 'thumbs', hashlib.md5(key.encode('utf8', 'replace')).hexdigest() + '.jpg')


def thumb(path, size=200, cache_dir=CACHE):
    """path of a cached JPEG thumbnail (size x size, centre-cropped) for a picture or a video; None if it cannot be made.
    JPEGs are decoded at reduced size (PIL draft mode), so a 12 MP photo costs a few ms instead of a second."""
    out = _thumb_path(path, size, cache_dir)
    if os.path.exists(out): return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    try:
        from PIL import Image, ImageOps
        src = path
        if kind_of(path) == 'video':
            tmp = tempfile.mkdtemp(prefix='rb-th-')
            try:
                for start in ('10%', '0'):
                    subprocess.run(['nice', '-n', '19', 'mpv', '--no-config', '--really-quiet', '--no-audio', '--hwdec=no', '--vo=image', '--vo-image-format=jpg', '--vo-image-outdir=' + tmp,
                                    '--frames=1', '--start=' + start, '--vd-lavc-threads=2', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
                    got = sorted(os.listdir(tmp))
                    if got: src = os.path.join(tmp, got[0]); break
                else: return None
                im = Image.open(src); im.load()
            finally:
                for n in os.listdir(tmp):
                    try: os.remove(os.path.join(tmp, n))
                    except OSError: pass
                try: os.rmdir(tmp)
                except OSError: pass
        else:
            im = Image.open(src)
            try: im.draft('RGB', (size * 2, size * 2))
            except Exception: pass
            im = ImageOps.exif_transpose(im)
        im = im.convert('RGB'); im = ImageOps.fit(im, (size, size), Image.BILINEAR)
        tmp = out + '.%d.tmp' % os.getpid(); im.save(tmp, 'JPEG', quality=80); os.replace(tmp, out); return out
    except Exception:
        return None


def prune_thumbs(cache_dir=CACHE, max_mb=60):
    """keep the thumbnail cache small: delete the oldest files above max_mb"""
    d = os.path.join(cache_dir, 'thumbs')
    try:
        fl = [(e.stat().st_atime, e.stat().st_size, e.path) for e in os.scandir(d) if e.name.endswith('.jpg')]
    except OSError: return
    tot = sum(f[1] for f in fl)
    for at, sz, p in sorted(fl):
        if tot <= max_mb * 1048576: break
        try: os.remove(p); tot -= sz
        except OSError: pass


def waveform(path, n=240, max_sec=1500, timeout=40):
    """n peaks (0..1) of the track for the seek bar; decoded by mpv to 4 kHz mono 8-bit PCM at lowest priority. None if it fails"""
    try:
        p = subprocess.run(['nice', '-n', '19', 'mpv', '--no-config', '--really-quiet', '--no-video', '--vid=no', '--ao=pcm', '--ao-pcm-file=/dev/stdout', '--ao-pcm-waveheader=no',
                            '--audio-format=u8', '--audio-samplerate=4000', '--audio-channels=mono', '--end=%d' % max_sec, '--vd-lavc-threads=1', path],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
        raw = p.stdout
    except Exception: return None
    if len(raw) < n * 2: return None
    step = len(raw) / float(n); out = []
    for i in range(n):
        seg = raw[int(i * step):int((i + 1) * step)] or b'\x80'
        out.append(max(abs(b - 128) for b in seg[::max(1, len(seg) // 64)]) / 128.0)
    mx = max(out) or 1.0
    return [min(1.0, (v / mx) ** 0.8) for v in out]


# ---------------------------------------------------------------- mpv
def _die_with_parent():
    """child setup: mpv gets SIGTERM when the player dies (crash, kill), so no orphaned mpv keeps playing or holding memory"""
    try:
        import ctypes, signal
        ctypes.CDLL('libc.so.6', use_errno=True).prctl(1, int(signal.SIGTERM))          # PR_SET_PDEATHSIG
    except Exception:
        pass


class MPV:
    """one mpv process driven over its JSON IPC socket. Events and property changes arrive on a reader thread and go to on_event(dict)."""
    def __init__(self, video=False, wid=None, input_conf=None, on_event=None, extra=()):
        self.on_event = on_event; self.sock = None; self.proc = None; self._id = 0; self._wait = {}; self.alive = False
        self.path = os.path.join(os.environ.get('XDG_RUNTIME_DIR') or '/tmp', 'rembly-mpv-%d-%d.sock' % (os.getpid(), int(time.time() * 1000) % 100000))
        ao = os.environ.get('REMBLY_MPV_AO') or 'alsa'                              # REMBLY_MPV_AO=null in tests (no sound card needed)
        cmd = ['mpv'] + MPV_BASE + ['--input-ipc-server=' + self.path, '--ao=' + ao] + (MPV_VIDEO if video else ['--vid=no'])
        if wid: cmd += ['--wid=%d' % wid]
        if input_conf: cmd += ['--input-conf=' + input_conf]
        cmd += list(extra)
        self.err = ''
        try: self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=_die_with_parent)
        except OSError as e: self.err = 'mpv: %s' % e; return
        for _ in range(100):                                                       # up to 5 s for the socket
            if os.path.exists(self.path): break
            if self.proc.poll() is not None: self.err = 'mpv завершился (код %s)' % self.proc.returncode; return
            time.sleep(0.05)
        try:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); self.sock.connect(self.path)
        except OSError as e: self.err = 'нет связи с mpv: %s' % e; self.close(); return
        self.alive = True; self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        buf = b''
        while True:
            try: chunk = self.sock.recv(65536)
            except OSError: chunk = b''
            if not chunk: break
            buf += chunk
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                try: msg = json.loads(line.decode('utf8', 'replace'))
                except ValueError: continue
                rid = msg.get('request_id')
                if rid in self._wait: self._wait[rid]['r'] = msg; self._wait[rid]['e'].set(); continue
                if self.on_event and 'event' in msg: self.on_event(msg)
        self.alive = False
        if self.on_event: self.on_event({'event': 'rembly-dead'})

    def cmd(self, *args, wait=False, timeout=2.0):
        if not self.alive: return None
        self._id += 1; rid = self._id; slot = None
        if wait: slot = self._wait[rid] = {'e': threading.Event(), 'r': None}
        try:
            with self.lock: self.sock.sendall((json.dumps({'command': list(args), 'request_id': rid}) + '\n').encode())
        except OSError: self.alive = False; return None
        if not wait: return None
        slot['e'].wait(timeout); self._wait.pop(rid, None); r = slot['r']
        return r.get('data') if r and r.get('error') == 'success' else None

    def get(self, prop): return self.cmd('get_property', prop, wait=True)
    def set(self, prop, val): self.cmd('set_property', prop, val)
    def observe(self, *props):
        for i, p in enumerate(props): self.cmd('observe_property', 100 + i, p)

    def close(self):
        try:
            if self.alive: self.cmd('quit')
        except Exception: pass
        try:
            if self.sock: self.sock.close()
        except OSError: pass
        if self.proc:
            try: self.proc.wait(timeout=1.5)
            except Exception:
                try: self.proc.kill()
                except OSError: pass
        try: os.remove(self.path)
        except OSError: pass
        self.alive = False


def has_sound_card():
    try: return bool(open('/proc/asound/cards').read().strip()) and 'no soundcards' not in open('/proc/asound/cards').read()
    except OSError: return False
