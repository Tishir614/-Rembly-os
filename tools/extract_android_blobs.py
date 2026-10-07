#!/usr/bin/env python3
"""Extract the Android bits Rembley needs for MediaTek Wi-Fi / Bluetooth / modem from YOUR firmware dump.

    python3 tools/extract_android_blobs.py system.bin vendor.bin [-o out/android-blobs.tar.gz]

Needs `debugfs` (e2fsprogs); no root, nothing is mounted or modified. If an image is Android-sparse,
`simg2img` (android-tools / android-sdk-libsparse-utils) is used first. Selects connectivity daemons
(wmt_*, conn*, ccci*, md*, rild, nvram*, ...), the firmware, and the bionic library closure they need
(so they can run on glibc Linux via /system/bin/linker). The tarball is picked up by rootfs/build-rootfs.sh."""
import argparse, io, os, re, shutil, struct, subprocess, sys, tarfile, tempfile

BIN_RE = re.compile(r'^(wmt|conn|6620|6630|mt66|ccci|md_|mdlogger|emdlogger|rild|mtkrild|ril|gsm0710|nvram|nvram_daemon|'
                    r'atci|atcid|wlan|wifi|connsys|hostapd|wpa_|bt_|bluetooth|gps|mtk_agpsd|mnld|linker)', re.I)
FW_RE = re.compile(r'(wmt|WMT|wifi|WIFI|wlan|WLAN|mt66|MT66|mt6735|MT6735|soc|SOC|ROM|patch|PATCH|md1|md3|modem|MODEM|'
                   r'dsp|DSP|\.cfg|\.bin|\.img|\.dat|bt_|BT_|conn)')
DIRS_COPY = ['etc/wifi', 'etc/firmware', 'firmware', 'etc/bluetooth', 'etc/mddb', 'etc/ril']   # relative to partition root
LIBDIRS = ['system/lib', 'vendor/lib']


def dbg(img, cmd):
    r = subprocess.run(['debugfs', '-R', cmd, img], capture_output=True)
    return r.stdout.decode('utf8', 'replace')


def prep(path, tmp):
    with open(path, 'rb') as f:
        if f.read(4) == b'\x3a\xff\x26\xed':
            out = os.path.join(tmp, os.path.basename(path) + '.raw')
            subprocess.check_call(['simg2img', path, out]); return out
    return path


def ls(img, d):
    out = []
    for line in dbg(img, 'ls -p %s' % d).splitlines():
        p = line.split('/')
        if len(p) >= 7 and p[5] not in ('.', '..', ''):
            out.append((p[5], int(p[2], 8), p[1]))
    return out


def root_of(img):
    return '/system' if any(n == 'bin' for n, _, _ in ls(img, '/system')) else ''


def dump(img, src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    dbg(img, 'dump -p %s %s' % (src, dst))
    return os.path.exists(dst) and os.path.getsize(dst) > 0


def needed(path):
    try:
        d = open(path, 'rb').read()
        if d[:4] != b'\x7fELF' or d[4] != 1: return []
        phoff, = struct.unpack_from('<I', d, 28); phsz, phn = struct.unpack_from('<HH', d, 42)
        loads, dyn = [], None
        for i in range(phn):
            t, off, va, _, fs, ms = struct.unpack_from('<6I', d, phoff + i * phsz)
            if t == 1: loads.append((va, off, fs))
            if t == 2: dyn = (off, fs)
        if not dyn: return []
        v2o = lambda v: next((v - va + off for va, off, fs in loads if va <= v < va + fs), None)
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


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('images', nargs='+'); ap.add_argument('-o', default='out/android-blobs.tar.gz')
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix='a73blobs-'); stage = os.path.join(tmp, 'stage'); os.makedirs(stage)
    imgs = []
    for p in a.images:
        img = prep(p, tmp); name = 'vendor' if 'vendor' in os.path.basename(p).lower() else 'system'
        imgs.append((name, img, root_of(img) if name == 'system' else ''))
        print('%s: %s (root prefix %r)' % (name, p, imgs[-1][2]))
    got = []
    for part, img, pre in imgs:                       # 1. binaries + config/firmware dirs
        for sub in ('bin', 'xbin'):
            for n, mode, _ in ls(img, '%s/%s' % (pre, sub)):
                if (mode & 0o170000) == 0o100000 and BIN_RE.match(n):
                    dst = os.path.join(stage, part, sub, n)
                    if dump(img, '%s/%s/%s' % (pre, sub, n), dst): got.append(dst); print('  bin', part, sub, n)
        for d in DIRS_COPY:
            stack = ['%s/%s' % (pre, d)]
            while stack:
                cur = stack.pop()
                for n, mode, _ in ls(img, cur):
                    full = cur + '/' + n
                    if (mode & 0o170000) == 0o040000: stack.append(full)
                    elif (mode & 0o170000) == 0o100000 and (FW_RE.search(n) or 'wifi' in cur or 'bluetooth' in cur):
                        rel = full[len(pre):].lstrip('/')
                        if dump(img, full, os.path.join(stage, part, rel)): print('  data', part, rel)
    # 2. library closure
    libidx = {}
    for part, img, pre in imgs:
        for d in ('lib', ):
            for n, mode, _ in ls(img, '%s/%s' % (pre, d)): libidx.setdefault(n, (part, img, '%s/%s/%s' % (pre, d, n)))
    todo, seen = [p for p in got], set()
    while todo:
        for lib in needed(todo.pop()):
            if lib in seen: continue
            seen.add(lib)
            if lib in libidx:
                part, img, src = libidx[lib]; dst = os.path.join(stage, part, 'lib', lib)
                if dump(img, src, dst): todo.append(dst)
            else: print('  note: %s not found in images (may be a plain Linux lib)' % lib)
    if not got:
        sys.exit('No connectivity binaries found. Is this the right system/vendor image? (try: debugfs -R "ls /system/bin" system.bin)')
    # android linker is a symlink to /system/bin/linker (32-bit); make sure the 32-bit one is there
    os.makedirs(os.path.dirname(a.o) or '.', exist_ok=True)
    with tarfile.open(a.o, 'w:gz') as t:
        for part in ('system', 'vendor'):
            p = os.path.join(stage, part)
            if os.path.isdir(p): t.add(p, arcname=part)
    print('wrote %s (%d files, %.1f MB)' % (a.o, sum(len(f) for _, _, f in os.walk(stage)), os.path.getsize(a.o) / 1e6))
    shutil.rmtree(tmp, ignore_errors=True)


main()
