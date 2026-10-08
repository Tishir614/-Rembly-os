"""Find the MediaTek connectivity pieces (Wi-Fi/BT/GPS/modem daemons, firmware, init .rc, bionic libs) inside Android system/vendor
images or partitions and pack them into a tarball. READ-ONLY: uses `debugfs` (e2fsprogs) which never writes unless told to.
Works on image files and directly on block devices (e.g. the tablet's own /dev/mmcblk0p24 'system').
Used by `rembley-drivers` (on the tablet) and `tools/extract_android_blobs.py` (on a PC)."""
import os, re, shutil, struct, subprocess, tarfile, tempfile

BIN_RE = re.compile(r'^(wmt|conn|6620|6630|mt66|ccci|md_|mdlogger|emdlogger|rild|mtkrild|ril|gsm0710|nvram|nvram_daemon|'
                    r'atci|atcid|wlan|wifi|connsys|hostapd|wpa_|bt_|bluetooth|gps|mtk_agpsd|mnld|linker)', re.I)
FW_RE = re.compile(r'(wmt|WMT|wifi|WIFI|wlan|WLAN|mt66|MT66|mt6735|MT6735|mt6625|MT6625|soc|SOC|ROM|patch|PATCH|md1|md3|modem|MODEM|gps|GPS|mnl|fm_|FM_|'
                   r'dsp|DSP|\.cfg|\.bin|\.img|\.dat|bt_|BT_|conn)')
DIRS_COPY = ['etc/wifi', 'etc/firmware', 'firmware', 'etc/bluetooth', 'etc/mddb', 'etc/ril', 'etc/init']   # relative to a partition's root
MODEM_RE = re.compile(r'md1|md3|modem|MODEM')


def _dbg(img, cmd):
    r = subprocess.run(['debugfs', '-R', cmd, img], capture_output=True)
    return r.stdout.decode('utf8', 'replace')


def prepare(path, tmp):
    """Android-sparse images are expanded first (needs simg2img); raw images and block devices are used as they are."""
    with open(path, 'rb') as f:
        if f.read(4) == b'\x3a\xff\x26\xed':
            out = os.path.join(tmp, os.path.basename(path) + '.raw')
            subprocess.check_call(['simg2img', path, out]); return out
    return path


def _ls(img, d):
    out = []
    for line in _dbg(img, 'ls -p %s' % d).splitlines():
        p = line.split('/')
        if len(p) >= 7 and p[5] not in ('.', '..', ''):
            out.append((p[5], int(p[2], 8), p[1], int(p[6]) if p[6].isdigit() else 0))
    return out


def looks_like_android(img):
    """True if the image/partition holds an Android /system or /vendor tree."""
    names = {n for n, _, _, _ in _ls(img, '/')}
    return bool(names & {'bin', 'lib', 'etc', 'firmware', 'system', 'build.prop'})


def _root_of(img):
    return '/system' if any(n == 'bin' for n, _, _, _ in _ls(img, '/system')) else ''


def _dump(img, src, dst, list_only):
    if list_only: return True
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    _dbg(img, 'dump -p %s %s' % (src, dst))
    return os.path.exists(dst) and os.path.getsize(dst) > 0


def _needed(path):
    """DT_NEEDED libraries of a 32-bit little-endian ELF file."""
    try:
        d = open(path, 'rb').read()
        if d[:4] != b'\x7fELF' or d[4] != 1: return []
        phoff, = struct.unpack_from('<I', d, 28); phsz, phn = struct.unpack_from('<HH', d, 42)
        loads, dyn = [], None
        for i in range(phn):
            t, off, va, _, fs, _ms = struct.unpack_from('<6I', d, phoff + i * phsz)
            if t == 1: loads.append((va, off, fs))
            if t == 2: dyn = (off, fs)
        if not dyn: return []
        def v2o(v): return next((v - va + off for va, off, fs in loads if va <= v < va + fs), None)
        ents, strtab = [], None
        for i in range(dyn[1] // 8):
            tag, val = struct.unpack_from('<iI', d, dyn[0] + i * 8)
            if tag == 0: break
            if tag == 1: ents.append(val)
            if tag == 5: strtab = v2o(val)
        if strtab is None: return []
        return [d[strtab + o:d.index(b'\0', strtab + o)].decode() for o in ents]
    except Exception:
        return []


def run(images, out=None, list_only=False, max_mb=40, log=print):
    """images: [(role, path)] with role 'system' or 'vendor'. Returns a dict summary; writes `out` (tar.gz) unless list_only.
    Raises RuntimeError if nothing connectivity-related was found."""
    tmp = tempfile.mkdtemp(prefix='a73blobs-'); stage = os.path.join(tmp, 'stage'); os.makedirs(stage)
    try:
        imgs = []
        for role, p in images:
            img = prepare(p, tmp); imgs.append((role, img, _root_of(img) if role == 'system' else ''))
            log('%s: %s (root prefix %r)' % (role, p, imgs[-1][2]))
        got = []
        for part, img, pre in imgs:                                   # 1. binaries + config/firmware dirs
            for sub in ('bin', 'xbin'):
                for n, mode, _, _sz in _ls(img, '%s/%s' % (pre, sub)):
                    if (mode & 0o170000) == 0o100000 and BIN_RE.match(n):
                        dst = os.path.join(stage, part, sub, n)
                        if _dump(img, '%s/%s/%s' % (pre, sub, n), dst, list_only): got.append(dst); log('  bin %s %s %s' % (part, sub, n))
            for d in DIRS_COPY:
                stack = ['%s/%s' % (pre, d)]
                while stack:
                    cur = stack.pop()
                    for n, mode, _, sz in _ls(img, cur):
                        full = cur + '/' + n
                        if sz > max_mb * 2 ** 20 and not MODEM_RE.search(n): log('  skip (too big, %d MB): %s' % (sz // 2 ** 20, full)); continue
                        if (mode & 0o170000) == 0o040000: stack.append(full)
                        elif (mode & 0o170000) == 0o100000 and (FW_RE.search(n) or 'wifi' in cur or 'bluetooth' in cur or
                                                                ((cur.endswith('etc/init') or '/etc/init/' in cur) and n.endswith('.rc'))):
                            rel = full[len(pre):].lstrip('/')
                            if _dump(img, full, os.path.join(stage, part, rel), list_only): log('  data %s %s' % (part, rel))
            for n, mode, _, sz in _ls(img, '%s/etc' % pre):             # fstab/ueventd: partition map + device permissions
                if (mode & 0o170000) == 0o100000 and (n.startswith('fstab') or n.startswith('ueventd')) and sz < 1 << 20:
                    rel = 'etc/' + n
                    if _dump(img, '%s/%s' % (pre, rel), os.path.join(stage, part, rel), list_only): log('  conf %s %s' % (part, rel))
        libidx = {}                                                      # 2. bionic library closure of what we picked
        for part, img, pre in imgs:
            for n, mode, _, _sz in _ls(img, '%s/lib' % pre): libidx.setdefault(n, (part, img, '%s/lib/%s' % (pre, n)))
        todo, seen = list(got), set()
        while todo:
            for lib in _needed(todo.pop()):
                if lib in seen: continue
                seen.add(lib)
                if lib in libidx:
                    part, img, src = libidx[lib]; dst = os.path.join(stage, part, 'lib', lib)
                    if _dump(img, src, dst, list_only): todo.append(dst)
                else: log('  note: %s not found in images (may be a plain Linux lib)' % lib)
        summary = {'binaries': sorted(os.path.basename(g) for g in got), 'files': 0, 'bytes': 0, 'out': out}
        if list_only: return summary
        if not got:
            raise RuntimeError('No connectivity binaries found. Wrong system/vendor image? (try: debugfs -R "ls /system/bin" system.bin)')
        for part in ('system', 'vendor'):
            for root, _, files in os.walk(os.path.join(stage, part)):
                for fn in files: summary['files'] += 1; summary['bytes'] += os.path.getsize(os.path.join(root, fn))
        man = os.path.join(stage, 'MANIFEST.txt')
        with open(man, 'w') as f:
            for root, _, files in os.walk(stage):
                for fn in sorted(files):
                    fp = os.path.join(root, fn)
                    if fp != man: f.write('%10d  %s\n' % (os.path.getsize(fp), os.path.relpath(fp, stage)))
        if out:
            os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
            with tarfile.open(out, 'w:gz') as t:
                t.add(man, arcname='MANIFEST.txt')
                for part in ('system', 'vendor'):
                    p = os.path.join(stage, part)
                    if os.path.isdir(p): t.add(p, arcname=part)
        return summary
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
