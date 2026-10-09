"""Find the touchscreen by what it IS (multitouch/direct input), not by a fixed name, and read its real coordinate range.
A different panel vendor (GT1151 / FocalTech / GSLX680 / GalaxyCore all exist in this kernel) must still work."""
import fcntl, glob, os, struct

ABS_X, ABS_Y, ABS_MT_X, ABS_MT_Y = 0x00, 0x01, 0x35, 0x36
BTN_TOUCH = 0x14a
PREFERRED = ('mtk-tpd',)


def _rd(p):
    try: return open(p).read().strip()
    except OSError: return ''


def _width():
    return 64 if struct.calcsize('P') == 8 else 32


def _bits_native(hexstr):
    words = hexstr.split(); bits = set(); n = 0; w = _width()
    for word in reversed(words):
        v = int(word, 16)
        for i in range(w):
            if v >> i & 1: bits.add(n + i)
        n += w
    return bits


def candidates():
    out = []
    for d in sorted(glob.glob(os.environ.get('REMBLY_SYSFS', '') + '/sys/class/input/event*')):
        base = d + '/device'
        name = _rd(base + '/name')
        try:
            absb = _bits_native(_rd(base + '/capabilities/abs') or '0'); keyb = _bits_native(_rd(base + '/capabilities/key') or '0')
            props = _bits_native(_rd(base + '/properties') or '0')
        except ValueError:
            continue
        mt = ABS_MT_X in absb and ABS_MT_Y in absb
        st = ABS_X in absb and ABS_Y in absb and BTN_TOUCH in keyb
        direct = 1 in props                                   # INPUT_PROP_DIRECT = finger on the display
        if not (mt or st): continue
        if not direct and name not in PREFERRED and 'ouch' not in name and 'tp' not in name.lower(): continue   # skip trackpads / tablets (pen)
        score = (name in PREFERRED) * 4 + direct * 2 + mt
        out.append((score, '/dev/input/' + os.path.basename(d), name, mt))
    out.sort(reverse=True)
    return out


def find():
    """-> (device path, name, is_multitouch) of the best touchscreen, or None."""
    c = candidates()
    return (c[0][1], c[0][2], c[0][3]) if c else None


def ranges(dev):
    """(max_x, max_y) from the kernel (EVIOCGABS), or None."""
    res = []
    try:
        with open(dev, 'rb', buffering=0) as f:
            for code_mt, code in ((ABS_MT_X, ABS_X), (ABS_MT_Y, ABS_Y)):
                for c in (code_mt, code):
                    buf = bytearray(24)
                    try:
                        fcntl.ioctl(f, 0x80184540 + c, buf)       # EVIOCGABS(c): struct input_absinfo (6 x s32)
                        v = struct.unpack('6i', bytes(buf))
                        if v[2] > 0: res.append(v[2]); break
                    except OSError: pass
    except OSError:
        return None
    return (res[0] + 1, res[1] + 1) if len(res) == 2 else None


if __name__ == '__main__':
    import sys
    r = find()
    if not r: sys.exit(1)
    a = sys.argv[1] if len(sys.argv) > 1 else 'all'
    rg = ranges(r[0])
    print({'dev': r[0], 'name': r[1], 'all': '%s|%s|%s|%s' % (r[0], r[1], 'mt' if r[2] else 'st', '%dx%d' % rg if rg else '?')}[a if a in ('dev', 'name') else 'all'])
