#!/usr/bin/env python3
"""Pure-python Android boot image v0 + cpio(newc) helpers (no mkbootimg/cpio needed)."""
import gzip, hashlib, io, os, stat, struct, sys

def sha256(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()

def unpack_boot(path):
    d = open(path, 'rb').read()
    assert d[:8] == b'ANDROID!', 'not an Android boot image'
    (ks, ka, rs, ra, ss, sa, ta, ps, hv, osv) = struct.unpack('<10I', d[8:48])
    assert hv == 0, 'only header v0 supported'
    pg = lambda n: (n + ps - 1) // ps * ps
    ko = ps; ro = ko + pg(ks); so = ro + pg(rs)
    return dict(kernel=d[ko:ko + ks], ramdisk=d[ro:ro + rs], second=d[so:so + ss],
                kaddr=ka, raddr=ra, saddr=sa, taddr=ta, pagesize=ps, osv=osv,
                name=d[48:64].rstrip(b'\0'), cmdline=d[64:576].rstrip(b'\0').decode(),
                extra_cmdline=d[608:1024].rstrip(b'\0').decode())

def pack_boot(out, kernel, ramdisk, cmdline, pagesize=0x800, base=0,
              kernel_offset=0x40008000, ramdisk_offset=0x44000000,
              second_offset=0x40f00000, tags_offset=0x4e000000, os_version=(8, 1, 0),
              patch=(2018, 1)):
    # NB: the stock offsets here are absolute (base 0), same as the original image.
    a, b, c = os_version; y, m = patch
    osv = ((a << 14 | b << 7 | c) << 11) | ((y - 2000) << 4 | m)
    h = b'ANDROID!' + struct.pack('<10I', len(kernel), base + kernel_offset, len(ramdisk),
        base + ramdisk_offset, 0, base + second_offset, base + tags_offset, pagesize, 0, osv)
    h += b'\0' * 16
    cb = cmdline.encode(); assert len(cb) < 512
    h += cb.ljust(512, b'\0')
    sid = hashlib.sha1(kernel + struct.pack('<I', len(kernel)) + ramdisk +
                       struct.pack('<I', len(ramdisk)) + struct.pack('<I', 0)).digest()
    h += sid.ljust(32, b'\0') + b'\0' * 1024  # id + extra_cmdline
    h = h[:1584] if len(h) > 1584 else h
    pad = lambda b: b + b'\0' * (-len(b) % pagesize)
    img = pad(h) + pad(kernel) + pad(ramdisk)
    open(out, 'wb').write(img)
    return len(img)

# ---- cpio newc ----
def cpio_read(data):
    ents, o = [], 0
    while True:
        assert data[o:o + 6] == b'070701', 'bad cpio magic at %d' % o
        f = [int(data[o + 6 + 8 * i:o + 14 + 8 * i], 16) for i in range(13)]
        ino, mode, uid, gid, nl, mt, fs = f[:7]; nsz = f[11]
        name = data[o + 110:o + 110 + nsz - 1].decode()
        o = (o + 110 + nsz + 3) & ~3
        body = data[o:o + fs]; o = (o + fs + 3) & ~3
        if name == 'TRAILER!!!': break
        ents.append((name, mode, body))
    return ents

def cpio_write(entries):
    """entries: list of (name, mode, bytes). Sorted, ino assigned, uid/gid 0."""
    out = io.BytesIO(); ino = 1
    def w(name, mode, body, ino):
        nm = name.encode() + b'\0'
        out.write(b'070701' + b''.join(b'%08X' % v for v in
            (ino, mode, 0, 0, 1, 0, len(body), 0, 0, 0, 0, len(nm), 0)))
        out.write(nm); out.write(b'\0' * (-(110 + len(nm)) % 4))
        out.write(body); out.write(b'\0' * (-len(body) % 4))
    for name, mode, body in entries:
        w(name, mode, body, ino); ino += 1
    w('TRAILER!!!', 0, b'', 0)
    return out.getvalue()

def extract(ents, root):
    for name, mode, body in ents:
        p = os.path.join(root, name)
        if stat.S_ISDIR(mode): os.makedirs(p, exist_ok=True)
        elif stat.S_ISLNK(mode):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            if os.path.lexists(p): os.remove(p)
            os.symlink(body.decode(), p)
        elif stat.S_ISREG(mode):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'wb').write(body); os.chmod(p, mode & 0o7777)

if __name__ == '__main__':
    if sys.argv[1] == 'unpack':   # unpack boot.img outdir
        b = unpack_boot(sys.argv[2]); od = sys.argv[3]; os.makedirs(od, exist_ok=True)
        open(od + '/kernel', 'wb').write(b['kernel']); open(od + '/ramdisk', 'wb').write(b['ramdisk'])
        print({k: v for k, v in b.items() if k not in ('kernel', 'ramdisk', 'second')})
        if b['ramdisk'][:2] == b'\x1f\x8b':
            ents = cpio_read(gzip.decompress(b['ramdisk'])); extract(ents, od + '/ramdisk_files')
            print(len(ents), 'ramdisk entries')
