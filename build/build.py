#!/usr/bin/env python3
"""Build A73-linux-test.img from the stock boot.bin. Flashes NOTHING.
usage: build/build.py boot.bin recovery.bin [--busybox PATH_TO_ARMHF_STATIC_BUSYBOX]"""
import gzip, hashlib, io, lzma, os, re, stat, sys, tarfile, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import a73tool as T

EXPECT = 'a94d3f8a18d626d0e12c3c1fe0848076a5c7754f2f108f727a9a21249a3483f4'
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, 'out'); os.makedirs(OUT, exist_ok=True)
POOL = 'https://ports.ubuntu.com/ubuntu-ports/pool/main/b/busybox/'

def fetch_busybox():
    idx = urllib.request.urlopen(POOL, timeout=30).read().decode()
    debs = sorted(set(re.findall(r'busybox-static_[^"<>]*_armhf\.deb', idx)), reverse=True)
    for deb in debs:
        raw = urllib.request.urlopen(POOL + deb, timeout=120).read()
        o = 8
        while o < len(raw):                   # minimal ar reader; python has no zstd, so skip .zst debs
            name = raw[o:o+16].strip(); size = int(raw[o+48:o+58]); body = raw[o+60:o+60+size]
            o += 60 + size + (size & 1)
            if name.startswith(b'data.tar') and not name.endswith(b'zst'):
                tf = tarfile.open(fileobj=io.BytesIO(body))
                for m in tf:
                    if m.name.endswith('/bin/busybox'):
                        print('busybox from', deb); return tf.extractfile(m).read()
    raise SystemExit('no usable busybox-static deb (or pass --busybox FILE)')

def main():
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    boot, rec = a[0], a[1]
    bb = None
    if '--busybox' in sys.argv: bb = open(sys.argv[sys.argv.index('--busybox') + 1], 'rb').read()
    got = T.sha256(boot)
    if got != EXPECT: sys.exit('boot.bin sha256 mismatch: %s' % got)
    b = T.unpack_boot(boot)
    k = b['kernel']; dtb = k.find(b'\xd0\x0d\xfe\xed')
    print('kernel %d bytes, appended DTB at %d' % (len(k), dtb)); assert dtb == 6716608
    r = T.unpack_boot(rec)
    rents = {n: (m, body) for n, m, body in T.cpio_read(gzip.decompress(r['ramdisk']))}
    adbd = rents['sbin/adbd'][1]
    if bb is None: bb = fetch_busybox()
    assert bb[:4] == b'\x7fELF' and bb[18] == 40, 'busybox is not an ARM ELF'
    D, F, L = stat.S_IFDIR | 0o755, stat.S_IFREG, stat.S_IFLNK | 0o777
    ents = [('.', D, b'')]
    for d in ('bin','sbin','etc','proc','sys','dev','mnt','newroot','tmp','run','system','system/bin'):
        ents.append((d, D, b''))
    ents += [('bin/busybox', F | 0o755, bb), ('sbin/adbd', F | 0o755, adbd),
             ('init', F | 0o755, open(os.path.join(HERE, 'initramfs/init'), 'rb').read()),
             ('etc/mdev.conf', F | 0o644, open(os.path.join(HERE, 'initramfs/etc/mdev.conf'), 'rb').read()),
             ('splash.32.gz', F | 0o644, open(os.path.join(HERE, 'initramfs/splash.32.gz'), 'rb').read()),
             ('splash.16.gz', F | 0o644, open(os.path.join(HERE, 'initramfs/splash.16.gz'), 'rb').read()),
             ('noroot.32.gz', F | 0o644, open(os.path.join(HERE, 'initramfs/noroot.32.gz'), 'rb').read()),
             ('noroot.16.gz', F | 0o644, open(os.path.join(HERE, 'initramfs/noroot.16.gz'), 'rb').read()),
             ('bin/sh', L, b'busybox'), ('system/bin/sh', L, b'../../bin/busybox'),
             ('bin/rembly-bootanim', F | 0o755, open(os.path.join(HERE, 'initramfs/rembly-bootanim'), 'rb').read())]
    for bpp in ('32', '16'):                                   # intro frames of the boot animation (tools/gen_bootanim.py)
        ad = os.path.join(HERE, 'initramfs', 'anim', bpp)
        if os.path.isdir(ad):
            ents += [('anim', D, b''), ('anim/' + bpp, D, b'')] if bpp == '32' else [('anim/' + bpp, D, b'')]
            for fn in sorted(os.listdir(ad)):
                if fn.endswith('.gz'): ents.append(('anim/%s/%s' % (bpp, fn), F | 0o644, open(os.path.join(ad, fn), 'rb').read()))
    cpio = T.cpio_write(ents)
    rd = gzip.compress(cpio, 9, mtime=0)
    open(os.path.join(OUT, 'rembly-initramfs.cpio.gz'), 'wb').write(rd)
    img = os.path.join(OUT, 'A73-linux-test.img')
    sz = T.pack_boot(img, k, rd, 'bootopt=64S3,32N2,32N2 buildvariant=user')
    assert sz < 16 * 1024 * 1024, 'image too large: %d' % sz
    h = T.sha256(img)
    open(img + '.sha256', 'w').write('%s  A73-linux-test.img\n' % h)
    open(os.path.join(OUT, 'initramfs-files.txt'), 'w').write(
        ''.join('%06o %8d %s\n' % (m, len(bd), n) for n, m, bd in ents))
    print('wrote', img, sz, 'bytes\nsha256', h)

main()
