"""Self-healing for the Android helper programs (wmt_loader / wmt_launcher ...) running on Linux.

The most common reasons such a daemon fails on a different userland are *paths*: it opens a firmware or library at a place where the
file is not, but the very same file exists elsewhere on the tablet (another directory, or still only inside the Android partitions).
This module reads the evidence (strace output, linker errors, kernel firmware-load failures) and repairs what is safely repairable:

  * missing file whose basename exists somewhere else   -> symlink it into the expected place
  * missing file that only exists in the Android system/vendor partition -> fetch it (read-only, via debugfs)
  * missing shared library (and its own dependencies)   -> same
  * missing directory under /data/misc, /dev/socket ... -> create it

It never overwrites an existing file and only writes under an allow-list of prefixes. All paths can be relocated with ROOT for tests."""
import glob, os, re, subprocess

ALLOWED_WRITE = ('/system/', '/vendor/', '/etc/firmware/', '/lib/firmware/', '/data/misc/', '/data/nvram/', '/data/vendor/', '/dev/socket/', '/var/lib/rembley/')
SEARCH_ROOTS = ('/vendor', '/system', '/etc/firmware', '/lib/firmware', '/nvdata')
FW_DIRS = ('firmware', 'etc/firmware', 'vendor/firmware', 'etc/wifi', 'etc/bluetooth', 'etc/mddb')
LIB_DIRS = ('lib', 'lib/hw', 'lib/egl', 'vendor/lib', 'vendor/lib/hw', 'system/lib', 'system/vendor/lib', 'lib/vndk-sp', 'lib/vndk')
INTERESTING = re.compile(r'\.(so|bin|cfg|img|dat|conf|bt|patch|rc)(\.\d+)*$|WIFI|WMT|wmt|patch|firmware|ROMv', re.I)

RE_STRACE = re.compile(r'(?:openat\([^,]*,\s*|open\(|stat(?:64)?\(|lstat(?:64)?\(|access\(|readlink\(|execve\()"([^"]+)".*=\s*-1\s+ENOENT')
RE_LINKER = [re.compile(r'library "([^"]+\.so[^"]*)" not found'), re.compile(r'could not load library "([^"]+\.so[^"]*)"'),
             re.compile(r'dlopen failed: library "([^"]+)" not found')]
RE_FWFAIL = [re.compile(r'Direct firmware load for (\S+) failed'), re.compile(r'request_firmware\(?\)?:? .*?(\S+\.\w+).*(?:fail|error|-2)', re.I),
             re.compile(r'firmware:? (?:failed to load|load failed) (\S+)', re.I)]


class Healer:
    def __init__(self, root='', log=print, debugfs_devs=None, max_fixes=40):
        self.root, self.log, self.devs, self.max = root, log, debugfs_devs or {}, max_fixes
        self.fixed, self._index = [], None
        self._part_cache = {}

    # ---------- helpers ----------
    def p(self, path):
        return self.root + path

    def allowed(self, path):
        return any(path.startswith(a) for a in ALLOWED_WRITE) and '..' not in path.split('/')

    def index(self):
        """basename -> [full paths] for the trees that may hold the file elsewhere (built once, a few thousand entries)."""
        if self._index is None:
            self._index = {}
            for r in SEARCH_ROOTS:
                for dirpath, _, files in os.walk(self.p(r)):
                    for f in files:
                        self._index.setdefault(f, []).append(os.path.join(dirpath, f)[len(self.root):])
        return self._index

    def _debugfs(self, dev, cmd):
        r = subprocess.run(['debugfs', '-R', cmd, dev], capture_output=True)
        return r.stdout.decode('utf8', 'replace')

    def find_in_partitions(self, name, kinds):
        """Search the Android partitions (read-only) for a file called `name`; returns (dev, path) or None. kinds: 'fw' or 'lib'."""
        key = (name, kinds)
        if key in self._part_cache: return self._part_cache[key]
        dirs = FW_DIRS if kinds == 'fw' else LIB_DIRS
        for role, dev in self.devs.items():
            prefix = '/system' if role == 'system' and any(l.split('/')[5] == 'bin' for l in self._debugfs(dev, 'ls -p /system').splitlines() if len(l.split('/')) > 5) else ''
            for d in dirs:
                for base in (prefix + '/' + d, '/' + d):
                    for line in self._debugfs(dev, 'ls -p %s' % base).splitlines():
                        f = line.split('/')
                        if len(f) >= 6 and f[5] == name:
                            self._part_cache[key] = (dev, base + '/' + name); return self._part_cache[key]
        self._part_cache[key] = None
        return None

    def fetch(self, dev, src, dest):
        os.makedirs(os.path.dirname(self.p(dest)), exist_ok=True)
        self._debugfs(dev, 'dump -p %s %s' % (src, self.p(dest)))
        ok = os.path.exists(self.p(dest)) and os.path.getsize(self.p(dest)) > 0
        if ok: self.log('  fetched %s from Android partition (%s)' % (dest, src))
        return ok

    def link(self, dest, source):
        if os.path.lexists(self.p(dest)): return False
        os.makedirs(os.path.dirname(self.p(dest)), exist_ok=True)
        os.symlink(source, self.p(dest)); self.log('  linked %s -> %s' % (dest, source)); self.fixed.append(dest); return True

    # ---------- repairs ----------
    def fix_path(self, path):
        """One missing absolute path. True if we changed something."""
        if len(self.fixed) >= self.max or not self.allowed(path) or os.path.lexists(self.p(path)): return False
        name = os.path.basename(path)
        if not name: return False
        runtime_dir = path.startswith(('/data/misc/', '/dev/socket/', '/data/vendor/', '/data/nvram/'))
        if runtime_dir and '.' not in name:                      # daemons expect these runtime directories to exist
            os.makedirs(self.p(path), exist_ok=True); self.log('  created directory %s' % path); self.fixed.append(path); return True
        if not INTERESTING.search(name): return False
        for cand in self.index().get(name, []):
            if cand != path and os.path.exists(self.p(cand)):
                return self.link(path, cand)
        kinds = 'lib' if name.endswith('.so') or '.so.' in name else 'fw'
        hit = self.find_in_partitions(name, kinds)
        if hit and self.fetch(hit[0], hit[1], path):
            self.fixed.append(path); self._index = None
            if kinds == 'lib': self.fix_library_deps(path)
            return True
        return False

    def fix_library(self, lib):
        """Bionic could not find `lib`: look in every library directory, then in the Android partitions."""
        if os.path.exists(self.p('/system/lib/' + lib)):
            return False                                   # already in the default search path: not the cause
        for cand in self.index().get(lib, []):             # exists elsewhere (e.g. /vendor/lib, hidden by linker namespaces): make it visible
            if os.path.exists(self.p(cand)):
                return self.link('/system/lib/' + lib, cand)
        hit = self.find_in_partitions(lib, 'lib')
        if hit:
            dest = ('/vendor/lib/' if hit[1].startswith('/vendor') or '/vendor/' in hit[1] else '/system/lib/') + lib
            if self.fetch(hit[0], hit[1], dest):
                self.fixed.append(dest); self._index = None; self.fix_library_deps(dest); return True
        self.log('  library %s not found anywhere (also not in the Android partitions)' % lib)
        return False

    def fix_library_deps(self, dest, depth=0):
        """A fetched library may itself need libraries we do not have yet."""
        if depth > 4: return
        try:
            from rembley_blobs import _needed
        except Exception:
            return
        for dep in _needed(self.p(dest)):
            if not any(os.path.exists(self.p(d + '/' + dep)) for d in ('/system/lib', '/vendor/lib', '/lib', '/usr/lib')):
                hit = self.find_in_partitions(dep, 'lib')
                if hit:
                    d2 = '/vendor/lib/' + dep if '/vendor/' in hit[1] or hit[1].startswith('/vendor') else '/system/lib/' + dep
                    if self.fetch(hit[0], hit[1], d2): self.fixed.append(d2); self.fix_library_deps(d2, depth + 1)

    # ---------- evidence -> repairs ----------
    def from_strace(self, text):
        seen, n = set(), 0
        for m in RE_STRACE.finditer(text):
            path = m.group(1)
            if path in seen: continue
            seen.add(path)
            if self.fix_path(path): n += 1
        return n

    def from_linker(self, text):
        n = 0
        for rx in RE_LINKER:
            for m in rx.finditer(text):
                if self.fix_library(os.path.basename(m.group(1))): n += 1
        return n

    def from_kernel(self, text):
        n = 0
        for rx in RE_FWFAIL:
            for m in rx.finditer(text):
                name = m.group(1).strip('"\',:')
                for d in ('/etc/firmware/', '/lib/firmware/', '/vendor/firmware/'):
                    if self.fix_path(d + name): n += 1
        return n


def heal(logs, root='', devs=None, log=print):
    """logs: dict kind -> text with kinds 'strace', 'linker', 'kernel'. Returns the number of repairs."""
    h = Healer(root=root, log=log, debugfs_devs=devs)
    n = h.from_linker(logs.get('linker', '')) + h.from_strace(logs.get('strace', '')) + h.from_kernel(logs.get('kernel', ''))
    return n, h.fixed


if __name__ == '__main__':
    import sys
    sys.path[:0] = ['/usr/local/lib/rembley']
    def rd(p):
        try: return open(p, errors='replace').read()
        except OSError: return ''
    devs = {}
    for r in ('system', 'vendor'):
        for u in glob.glob('/sys/class/block/*/uevent'):
            if ('PARTNAME=%s' % r) in rd(u).split('\n'): devs[r] = '/dev/' + os.path.basename(os.path.dirname(u))
    dm = subprocess.run(['dmesg'], capture_output=True, text=True).stdout[-60000:]
    logs = {'strace': rd('/var/log/wmt.strace') + rd('/var/log/wmt.loader.strace'), 'linker': rd('/var/log/wmt_launcher.log') + rd('/var/log/wmt_loader.log'), 'kernel': dm}
    n, fixed = heal(logs, devs=devs)
    print('repairs: %d' % n)
    sys.exit(0 if n else 1)
