"""Tiny Xlib/XScreenSaver bridge via ctypes: read window-manager properties and the idle time IN-PROCESS.
Replaces polling with wmctrl/xprop/xprintidle subprocesses (each spawn costs real CPU on a Cortex-A53).
Not thread-safe: use one XConn per thread."""
import ctypes, ctypes.util

_x11 = ctypes.CDLL(ctypes.util.find_library('X11') or 'libX11.so.6')
_x11.XOpenDisplay.restype = ctypes.c_void_p; _x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
_x11.XDefaultRootWindow.restype = ctypes.c_ulong; _x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
_x11.XInternAtom.restype = ctypes.c_ulong; _x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
_x11.XFree.argtypes = [ctypes.c_void_p]
_x11.XGetWindowProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long, ctypes.c_long, ctypes.c_int, ctypes.c_ulong,
                                    ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
                                    ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_void_p)]
_x11.XGetWindowProperty.restype = ctypes.c_int
_x11.XFlush.argtypes = [ctypes.c_void_p]

try:
    _xtst = ctypes.CDLL(ctypes.util.find_library('Xtst') or 'libXtst.so.6')
    _xtst.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    _xtst.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
except OSError:
    _xtst = None
_x11.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]; _x11.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]

try:
    _xss = ctypes.CDLL(ctypes.util.find_library('Xss') or 'libXss.so.1')
    _xss.XScreenSaverAllocInfo.restype = ctypes.c_void_p
    _xss.XScreenSaverQueryInfo.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p]
except OSError:
    _xss = None


class _SSInfo(ctypes.Structure):
    _fields_ = [('window', ctypes.c_ulong), ('state', ctypes.c_int), ('kind', ctypes.c_int),
                ('til_or_since', ctypes.c_ulong), ('idle', ctypes.c_ulong), ('eventMask', ctypes.c_ulong)]


class XConn:
    def __init__(self):
        self.d = _x11.XOpenDisplay(None)
        if not self.d: raise RuntimeError('cannot open X display')
        self.root = _x11.XDefaultRootWindow(self.d); self._atoms = {}
        self._ss = _xss.XScreenSaverAllocInfo() if _xss else None

    def atom(self, name):
        if name not in self._atoms: self._atoms[name] = _x11.XInternAtom(self.d, name.encode(), 0)
        return self._atoms[name]

    def prop(self, name, window=None, maxlen=4096):
        """Format-32 property as a list of ints (CARDINAL/WINDOW/ATOM). [] if missing."""
        t, fmt, n, rest, data = ctypes.c_ulong(), ctypes.c_int(), ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_void_p()
        r = _x11.XGetWindowProperty(self.d, window or self.root, self.atom(name), 0, maxlen, 0, 0,
                                    ctypes.byref(t), ctypes.byref(fmt), ctypes.byref(n), ctypes.byref(rest), ctypes.byref(data))
        if r != 0 or not data.value or fmt.value != 32 or n.value == 0:
            if data.value: _x11.XFree(data)
            return []
        arr = (ctypes.c_ulong * n.value).from_address(data.value); out = [int(v) for v in arr]
        _x11.XFree(data); return out

    def current_desktop(self):
        v = self.prop('_NET_CURRENT_DESKTOP'); return v[0] if v else 0

    def clients(self):
        return self.prop('_NET_CLIENT_LIST')

    def window_types(self, wid):
        names = {self.atom(n): n for n in ('_NET_WM_WINDOW_TYPE_NORMAL', '_NET_WM_WINDOW_TYPE_DIALOG', '_NET_WM_WINDOW_TYPE_DOCK',
                                           '_NET_WM_WINDOW_TYPE_DESKTOP', '_NET_WM_WINDOW_TYPE_UTILITY', '_NET_WM_WINDOW_TYPE_SPLASH')}
        return [names.get(a, str(a)) for a in self.prop('_NET_WM_WINDOW_TYPE', wid)]

    def idle_ms(self):
        if not self._ss: return None
        if _xss.XScreenSaverQueryInfo(self.d, self.root, self._ss) == 0: return None
        return _SSInfo.from_address(self._ss).idle

    def size(self):
        return _x11.XDisplayWidth(self.d, 0), _x11.XDisplayHeight(self.d, 0)

    def move(self, x, y):
        if _xtst: _xtst.XTestFakeMotionEvent(self.d, 0, int(x), int(y), 0); _x11.XFlush(self.d)

    def click(self, button, x=None, y=None):
        """Synthetic click (1 left, 2 middle, 3 right, 4/5 scroll up/down) via XTest."""
        if not _xtst: return False
        if x is not None: _xtst.XTestFakeMotionEvent(self.d, 0, int(x), int(y), 0)
        _xtst.XTestFakeButtonEvent(self.d, button, 1, 0); _xtst.XTestFakeButtonEvent(self.d, button, 0, 0); _x11.XFlush(self.d); return True
