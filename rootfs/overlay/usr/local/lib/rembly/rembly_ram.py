"""The tablet's REAL memory: measured, never trusted from what a bootloader / fastboot / spec sheet claims.
Sources (all read from the running kernel): /proc/meminfo (usable), /proc/iomem ("System RAM" ranges = RAM the kernel actually maps),
the device tree memory node, the kernel boot line "Memory: x K/y K available" in dmesg, and a pattern test that writes a different value into every
page and reads it all back (memory that does not really exist shows up as aliasing: two pages end up with the same content, or data changes).
Pattern test works on free RAM only, in user space; it cannot damage anything."""
import mmap, os, re, struct, subprocess, time

ROOT = os.environ.get('REMBLY_RAM_ROOT', '')


def rd(p, d=''):
    try: return open(ROOT + p, errors='replace').read()
    except OSError: return d


def meminfo():
    return {l.split(':')[0]: int(l.split()[1]) for l in rd('/proc/meminfo').splitlines() if ':' in l and len(l.split()) > 1}


def iomem_ranges():
    """[(start, end)] of 'System RAM' from /proc/iomem (needs root for real addresses)."""
    out = []
    for l in rd('/proc/iomem').splitlines():
        m = re.match(r'\s*([0-9a-f]+)-([0-9a-f]+) : System RAM', l)
        if m and int(m.group(1), 16) or (m and int(m.group(2), 16)): out.append((int(m.group(1), 16), int(m.group(2), 16)))
    return out


def dt_memory():
    """Memory node of the device tree: (base, size) pairs; cells are 32 or 64 bit big endian (the boot loader fills them in)."""
    reg = None
    try: reg = open(ROOT + '/proc/device-tree/memory/reg', 'rb').read()
    except OSError:
        import glob
        for p in glob.glob(ROOT + '/proc/device-tree/memory@*/reg'):
            reg = open(p, 'rb').read(); break
    if not reg: return []
    out = []
    for fmt, n in (('>QQ', 16), ('>II', 8)):
        if len(reg) % n == 0:
            out = [struct.unpack_from(fmt, reg, i) for i in range(0, len(reg), n)]
            if all(s > 0 for _, s in out): return out
    return []


def dmesg_memory():
    """'Memory: 1750000K/1900000K available (...)' -> (available_kb, total_kb) as the kernel counted them at boot."""
    try: t = subprocess.run('dmesg 2>/dev/null | grep -m1 -E "Memory: [0-9]+K/[0-9]+K"', shell=True, capture_output=True, text=True, timeout=5).stdout
    except Exception: t = ''
    m = re.search(r'Memory: (\d+)K/(\d+)K', t)
    return (int(m.group(1)), int(m.group(2))) if m else None


def measure():
    mi = meminfo(); usable = mi.get('MemTotal', 0) // 1024
    ranges = iomem_ranges(); iomem_mb = sum(e - s + 1 for s, e in ranges) // 2 ** 20 if ranges else None
    dt = dt_memory(); dt_mb = sum(sz for _, sz in dt) // 2 ** 20 if dt else None
    dm = dmesg_memory(); dm_mb = dm[1] // 1024 if dm else None
    cands = [(k, v) for k, v in (('iomem', iomem_mb), ('device-tree', dt_mb), ('dmesg', dm_mb)) if v]
    phys = max(v for _, v in cands) if cands else usable          # physical RAM the kernel knows about: the largest honest source
    return {'usable_mb': usable, 'physical_mb': phys, 'sources': dict(cands), 'free_mb': mi.get('MemAvailable', 0) // 1024,
            'reserved_mb': max(0, phys - usable), 'swap_mb': mi.get('SwapTotal', 0) // 1024}


def pattern_test(mb, log=None):
    """Fill `mb` MiB with a unique word per 4 KiB page + walking patterns, read back, count problems. -> dict"""
    page = mmap.PAGESIZE; n = mb * 2 ** 20 // page
    t0 = time.time(); mm = mmap.mmap(-1, n * page); bad = alias = 0
    try:
        for i in range(n): mm[i * page:i * page + 8] = struct.pack('<Q', (i * 2654435761 + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF)
        seen = set()
        for i in range(n):
            v, = struct.unpack('<Q', mm[i * page:i * page + 8])
            if v != (i * 2654435761 + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF: bad += 1
            if v in seen: alias += 1
            seen.add(v)
        mib = 2 ** 20
        for pat in (b'\x55', b'\xaa', b'\x00', b'\xff'):                 # stuck bits: whole region, both polarities, 1 MiB at a time (C speed)
            blk = pat * mib
            for off in range(0, mb * mib, mib): mm[off:off + mib] = blk
            for off in range(0, mb * mib, mib):
                if mm[off:off + mib] != blk: bad += 1
    finally:
        mm.close()
    return {'tested_mb': mb, 'pages': n, 'bad_pages': bad, 'aliased_pages': alias, 'seconds': round(time.time() - t0, 1)}


def check(claim_mb=None, test_mb=None, full=False):
    m = measure(); notes = []; verdict = 'ok'
    if m['usable_mb'] < 256: notes.append('usable RAM %d MB is implausibly small' % m['usable_mb']); verdict = 'warn'
    src = m['sources']
    if len(set(src.values())) > 1 and max(src.values()) - min(src.values()) > 64:
        notes.append('sources disagree: %s' % ', '.join('%s=%d MB' % kv for kv in sorted(src.items()))); verdict = 'warn'
    if claim_mb:
        if claim_mb > m['physical_mb'] * 1.12: notes.append('CLAIMED %d MB but the kernel can address only %d MB: the claim is wrong or inflated' % (claim_mb, m['physical_mb'])); verdict = 'mismatch'
        elif claim_mb < m['physical_mb'] * 0.88: notes.append('claimed %d MB is lower than the %d MB the kernel sees' % (claim_mb, m['physical_mb'])); verdict = 'warn'
    free = m['free_mb']
    mb = test_mb if test_mb else (int(free * 0.7) if full else min(128, int(free * 0.25)))
    mb = max(16, min(mb, int(free * 0.7)))
    t = pattern_test(mb) if free >= 64 else None
    if t is None: notes.append('not enough free RAM (%d MB) for a pattern test' % free); verdict = 'warn' if verdict == 'ok' else verdict
    elif t['bad_pages'] or t['aliased_pages']:
        notes.append('PATTERN TEST FAILED: %d bad and %d aliased pages in %d MB — the memory is damaged or does not exist as reported' % (t['bad_pages'], t['aliased_pages'], t['tested_mb'])); verdict = 'FAIL'
    return {'measured': m, 'claim_mb': claim_mb, 'test': t, 'verdict': verdict, 'notes': notes}
