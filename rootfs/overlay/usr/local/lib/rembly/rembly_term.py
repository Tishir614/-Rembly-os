"""rembly_term - one terminal widget for every Rembly app that needs a shell (Rembly Code, Servers): Vte in the system colours (black-and-white or hacker green),
a spawn helper that works with both old (0.60, Ubuntu 20.04) and new Vte, reading the recent output (for "ask the AI about this error"), and a touch key bar
with the keys an on-screen keyboard lacks: Esc, Tab, sticky Ctrl/Alt, arrows, Home/End/PgUp/PgDn, | ~ / - and copy/paste, font size."""
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango
try:
    gi.require_version('Vte', '2.91'); from gi.repository import Vte
except (ValueError, ImportError):
    Vte = None
import remblyui as ui

MONO_PALETTE = ('#1a1a1a', '#bdbdbd', '#d0d0d0', '#e0e0e0', '#a8a8a8', '#c8c8c8', '#d8d8d8', '#e8e8e8', '#555555', '#cfcfcf', '#dedede', '#ececec', '#bcbcbc', '#d6d6d6', '#e4e4e4', '#ffffff')
HACKER_PALETTE = ('#0b140e', '#ff5555', '#39ff88', '#f1fa8c', '#4da6ff', '#d58cff', '#3de0d0', '#c9ffe0', '#2f5d42', '#ff7777', '#7dffb0', '#ffff99', '#80c0ff', '#e0aaff', '#7ff0e6', '#ffffff')


def available():
    return Vte is not None


def make_terminal(font_size=11, scrollback=5000):
    """a Vte.Terminal in the current style; None when Vte is not installed"""
    if Vte is None: return None
    t = Vte.Terminal(); t.set_scrollback_lines(scrollback); t.set_font(Pango.FontDescription('Fira Code %d' % font_size)); t.set_cursor_blink_mode(Vte.CursorBlinkMode.ON)
    t.set_audible_bell(False)
    fg, bg = Gdk.RGBA(), Gdk.RGBA(); fg.parse('#39ff88' if ui.HACKER else '#eaeaea'); bg.parse('#020604' if ui.HACKER else '#060606')
    pal = []
    for h in (HACKER_PALETTE if ui.HACKER else MONO_PALETTE):
        g = Gdk.RGBA(); g.parse(h); pal.append(g)
    t.set_colors(fg, bg, pal)
    return t


def spawn(term, argv, cwd=None, env=None, callback=None):
    """start argv in the terminal; callback(pid, error) when it started. env: dict of extra variables (merged with the current environment)."""
    import os
    envv = None
    if env:
        e = dict(os.environ); e.update(env); envv = ['%s=%s' % kv for kv in e.items()]
    cwd = cwd if cwd and os.path.isdir(cwd) else os.path.expanduser('~')

    def done(t, pid, err, _data=None):
        if callback: callback(pid, err)
    try:
        term.spawn_async(Vte.PtyFlags.DEFAULT, cwd, list(argv), envv, GLib.SpawnFlags.SEARCH_PATH, None, None, -1, None, done, None)
    except Exception:
        try:
            ok, pid = term.spawn_sync(Vte.PtyFlags.DEFAULT, cwd, list(argv), envv, GLib.SpawnFlags.SEARCH_PATH, None, None)[:2]
            done(term, pid, None)
        except Exception as e:
            done(term, 0, e)


def feed(term, text):
    """type text into the program running in the terminal"""
    data = text.encode('utf8') if isinstance(text, str) else text
    try: term.feed_child(data)
    except TypeError: term.feed_child(data.decode('utf8', 'replace'), -1)


def recent_text(term, lines=60):
    """the last `lines` lines on screen/scrollback as text ('' when it cannot be read: depends on the Vte version)"""
    txt = ''
    fns = [lambda: term.get_text_format(Vte.Format.TEXT)] if hasattr(term, 'get_text_format') else [lambda: term.get_text(None, None), lambda: term.get_text()]
    for fn in fns:
        try:
            r = fn()
            txt = r[0] if isinstance(r, tuple) else r
            if txt: break
        except Exception:
            continue
    rows = [l.rstrip() for l in (txt or '').splitlines()]
    while rows and not rows[-1]: rows.pop()
    return '\n'.join(rows[-lines:])


def send_key(term, keyval, state=0):
    """deliver a real key press to the terminal, so Vte applies its own modes (cursor keys in vim/less, Home/End, ...)"""
    win = term.get_window()
    if win is None: return False
    keymap = Gdk.Keymap.get_for_display(term.get_display())
    found, keys = keymap.get_entries_for_keyval(keyval)
    for press in (True, False):
        ev = Gdk.Event.new(Gdk.EventType.KEY_PRESS if press else Gdk.EventType.KEY_RELEASE)
        ev.window = win; ev.send_event = True; ev.time = Gtk.get_current_event_time() or 0; ev.keyval = keyval; ev.state = Gdk.ModifierType(state)
        ev.hardware_keycode = keys[0].keycode if found and keys else 0; ev.group = keys[0].group if found and keys else 0; ev.length = 0; ev.string = ''
        ev.set_device(Gdk.Display.get_default().get_default_seat().get_keyboard())
        term.event(ev)
    return True


class KeyBar(Gtk.ScrolledWindow):
    """one scrolling row of touch keys for `term`. Ctrl and Alt are sticky: tap, then type the next key (on-screen or hardware)."""
    KEYS = [('Esc', Gdk.KEY_Escape), ('Tab', Gdk.KEY_Tab), ('Ctrl', 'ctrl'), ('Alt', 'alt'), ('↑', Gdk.KEY_Up), ('↓', Gdk.KEY_Down), ('←', Gdk.KEY_Left), ('→', Gdk.KEY_Right),
            ('Home', Gdk.KEY_Home), ('End', Gdk.KEY_End), ('PgUp', Gdk.KEY_Page_Up), ('PgDn', Gdk.KEY_Page_Down), ('|', '|'), ('~', '~'), ('/', '/'), ('-', '-'), (':', ':'), ('^C', '\x03'), ('^D', '\x04'),
            ('Копир.', 'copy'), ('Встав.', 'paste'), ('A−', 'font-'), ('A+', 'font+'), ('⌨', 'osk')]

    def __init__(self, term, font_cb=None):
        super().__init__(); self.term = term; self.ctrl = False; self.alt = False; self.btns = {}; self.font_cb = font_cb
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER); self.set_size_request(-1, 52)
        row = Gtk.Box(spacing=4); row.set_margin_start(4); row.set_margin_end(4); row.set_margin_top(3); row.set_margin_bottom(3); self.add(row)
        for label, key in self.KEYS:
            b = Gtk.Button(label=label); b.set_size_request(56 if len(label) < 4 else 72, 44); b.set_can_focus(False); b.set_focus_on_click(False)
            b.connect('clicked', lambda _b, k=key, l=label: self.press(k, l)); row.pack_start(b, False, False, 0); self.btns[key] = b
        term.connect('key-press-event', self.on_term_key)

    def press(self, key, label):
        t = self.term
        if key in ('ctrl', 'alt'):
            if key == 'ctrl': self.ctrl = not self.ctrl
            else: self.alt = not self.alt
            self.sync(); t.grab_focus(); return
        if key == 'copy':
            try: t.copy_clipboard_format(Vte.Format.TEXT)
            except Exception:
                try: t.copy_clipboard()
                except Exception: pass
        elif key == 'paste': t.paste_clipboard()
        elif key == 'osk': ui.osk(True)
        elif key in ('font-', 'font+'):
            if self.font_cb: self.font_cb(-1 if key == 'font-' else 1)
        elif isinstance(key, int):
            send_key(t, key, (Gdk.ModifierType.CONTROL_MASK if self.ctrl else 0) | (Gdk.ModifierType.MOD1_MASK if self.alt else 0)); self.ctrl = self.alt = False; self.sync()
        else:
            feed(t, self.mod(key)); self.ctrl = self.alt = False; self.sync()
        t.grab_focus()

    def mod(self, s):
        """apply sticky Ctrl/Alt to typed text"""
        out = ''
        for ch in s:
            if self.ctrl and ch.isalpha() and ch.isascii(): ch = chr(ord(ch.lower()) - 96)
            elif self.ctrl and ch in '[]\\@^_': ch = chr(ord(ch) & 0x1f)
            if self.alt: ch = '\x1b' + ch
            out += ch
        return out

    def on_term_key(self, term, ev):
        """sticky modifiers also apply to the next key typed on the on-screen or hardware keyboard"""
        ctrl_shift = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
        if (ev.state & ctrl_shift) == ctrl_shift and Gdk.keyval_name(ev.keyval) in ('C', 'c'): self.press('copy', ''); return True        # Ctrl+Shift+C / V like desktop terminals
        if (ev.state & ctrl_shift) == ctrl_shift and Gdk.keyval_name(ev.keyval) in ('V', 'v'): self.press('paste', ''); return True
        if not (self.ctrl or self.alt): return False
        u = Gdk.keyval_to_unicode(ev.keyval)
        if u and not (ev.state & Gdk.ModifierType.CONTROL_MASK):
            feed(term, self.mod(chr(u))); self.ctrl = self.alt = False; self.sync(); return True
        return False

    def sync(self):
        for key, on in (('ctrl', self.ctrl), ('alt', self.alt)):
            sc = self.btns[key].get_style_context(); sc.add_class('on') if on else sc.remove_class('on')
