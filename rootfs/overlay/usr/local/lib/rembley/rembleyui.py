#!/usr/bin/env python3
"""Shared UI toolkit for Rembley programs (glass panels, wallpaper blur, icons, helpers).

Glass look = a blurred copy of the wallpaper painted behind each panel (done once, so it costs
nothing while running). Windows: home (desktop layer), bar (dock + workspaces + tray, with strut),
launcher (all apps)."""
import glob, json, math, os, shutil, subprocess, sys, threading, time, urllib.request

import gi
gi.require_version('Gtk', '3.0'); gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio, Pango, GdkPixbuf
try:
    gi.require_version('GdkX11', '3.0'); from gi.repository import GdkX11
except Exception:
    GdkX11 = None
import cairo
from PIL import Image, ImageFilter

DEMO = bool(os.environ.get('REMBLEY_DEMO'))          # fills widgets with sample data (screenshots only)
CFG = os.path.expanduser('~/.config/rembley'); os.makedirs(CFG, exist_ok=True)
SHARE = os.environ.get('REMBLEY_SHARE', '/usr/share/rembley')
BAR = 68
USER = os.environ.get('REMBLEY_USER') or (open(CFG + '/user').read().strip() if os.path.exists(CFG + '/user') else 'Rembley')

RU_DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
RU_MON = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']

CSS = b"""
window.rl-win { background-color: transparent; background-image: none; }
label { color: #ece6ff; }
.rl-title { font-weight: 600; font-size: 15px; color: #f3eeff; }
.clock { font-size: 66px; font-weight: 300; color: #f6f1ff; text-shadow: 0 0 20px rgba(165,135,255,0.95); }
.date { font-size: 17px; color: #e4dcff; text-shadow: 0 0 8px rgba(120,90,220,0.9); }
.small { font-size: 12px; color: #cfc6ee; }
.name { font-size: 16px; font-weight: 600; color: #fff; }
.online { font-size: 12px; color: #b9aee6; }
.temp { font-size: 30px; color: #fff; }
.side-item { padding: 0 12px; border-radius: 14px; min-height: 42px; background-image: none; background-color: transparent;
             border: none; box-shadow: none; color: #ece6ff; font-size: 15px; }
.side-item:hover, .side-item:active, .side-item.active { background-image: linear-gradient(90deg, rgba(196,120,196,0.60), rgba(120,92,205,0.38)); }
.tile { background-image: none; background-color: transparent; border: none; box-shadow: none; border-radius: 16px; padding: 6px 2px; color: #e9e3ff; font-size: 12px; }
.tile:hover, .tile:active { background-color: rgba(255,255,255,0.14); }
.dockbtn { background-image: none; background-color: transparent; border: none; box-shadow: none; border-radius: 16px; padding: 4px; min-width: 44px; min-height: 44px; }
.dockbtn:hover, .dockbtn:active { background-color: rgba(255,255,255,0.18); }
.ws { background-image: none; background-color: rgba(255,255,255,0.07); border: 1px solid rgba(190,170,255,0.25); border-radius: 12px; color: #e8e0ff; min-width: 48px; min-height: 40px; padding: 0; font-size: 14px; box-shadow: none; }
.ws.cur { border: 2px solid #c08cff; background-color: rgba(190,140,255,0.28); }
.tray { color: #f0eaff; font-size: 14px; }
.note-box { background-color: #fdeea6; border-radius: 6px; }
.note-box textview, .note-box textview text { background-color: #fdeea6; color: #3a3320; font-size: 14px; }
.note-title { color: #3a3320; font-weight: 600; font-size: 13px; }
.note-btn { background-image: none; background-color: transparent; border: none; box-shadow: none; color: #3a3320; min-width: 30px; min-height: 30px; padding: 0; font-size: 20px; }
.mbtn { background-image: none; background-color: transparent; border: none; box-shadow: none; padding: 2px 10px; min-height: 40px; }
.mbtn:active { background-color: rgba(255,255,255,0.18); border-radius: 14px; }
entry.rl-search { background-color: rgba(255,255,255,0.12); color: #fff; border-radius: 14px; border: 1px solid rgba(190,170,255,0.3); min-height: 38px; }
"""

_KEEP = []


def surface_from(im):
    r, g, b = im.convert('RGB').split()
    im = Image.merge('RGBA', (b, g, r, Image.new('L', im.size, 255)))
    buf = bytearray(im.tobytes()); _KEEP.append(buf)
    return cairo.ImageSurface.create_for_data(buf, cairo.FORMAT_ARGB32, im.size[0], im.size[1], im.size[0] * 4)


def load_wallpaper(w, h):
    path = os.environ.get('REMBLEY_WALL') or next((p for p in (CFG + '/wallpaper.png', CFG + '/wallpaper.jpg',
                                                               SHARE + '/wallpaper.png') if os.path.exists(p)), None)
    if path:
        im = Image.open(path).convert('RGB')
        s = max(w / im.width, h / im.height)
        im = im.resize((math.ceil(im.width * s), math.ceil(im.height * s)), Image.BILINEAR)
        l, t = (im.width - w) // 2, (im.height - h) // 2
        im = im.crop((l, t, l + w, t + h))
    else:
        im = Image.new('RGB', (w, h), (30, 22, 70))
    small = im.resize((max(1, w // 4), max(1, h // 4)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(4))
    return surface_from(im), surface_from(small.resize((w, h), Image.BILINEAR))


def rrect(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0); cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi); cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()


class Glass(Gtk.Box):
    """Rounded translucent panel painted from the blurred wallpaper. Content lives in self.inner,
    so padding is done with margins (border_width would shift the draw origin)."""
    def __init__(self, radius=22, tint=(0.08, 0.06, 0.17, 0.58), orientation=Gtk.Orientation.HORIZONTAL, spacing=0, **kw):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kw)
        self.radius, self.tint = radius, tint
        self.set_has_window(False)
        self.inner = Gtk.Box(orientation=orientation, spacing=spacing)
        Gtk.Box.pack_start(self, self.inner, True, True, 0)

    def pack_start(self, *a): self.inner.pack_start(*a)
    def pack_end(self, *a): self.inner.pack_end(*a)
    def set_spacing(self, n): self.inner.set_spacing(n)

    def set_border_width(self, n):
        for side in ('top', 'bottom', 'start', 'end'): self.inner.set_property('margin-' + side, n)

    def do_draw(self, cr):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        top = self.get_toplevel(); ox, oy = getattr(top, 'origin', (0, 0))
        pos = self.translate_coordinates(top, 0, 0) or (0, 0)
        blur = getattr(top, 'blur', None)
        cr.save(); rrect(cr, 0.5, 0.5, w - 1, h - 1, self.radius); cr.clip_preserve()
        if blur is not None:
            cr.set_source_surface(blur, -(pos[0] + ox), -(pos[1] + oy)); cr.paint()
        cr.set_source_rgba(*self.tint); cr.paint(); cr.restore()
        rrect(cr, 0.75, 0.75, w - 1.5, h - 1.5, self.radius)
        cr.set_source_rgba(0.72, 0.66, 1.0, 0.38); cr.set_line_width(1.3); cr.stroke()
        return Gtk.Box.do_draw(self, cr)


class Win(Gtk.Window):
    def __init__(self, wall=None, blur=None, origin=(0, 0), **kw):
        super().__init__(**kw)
        self.wall, self.blur, self.origin = wall, blur, origin
        self.get_style_context().add_class('rl-win')
        self.set_app_paintable(True)

    def do_draw(self, cr):
        if self.wall is not None:
            ox, oy = self.origin
            cr.set_source_surface(self.wall, -ox, -oy); cr.paint()
        return Gtk.Window.do_draw(self, cr)


THEME = None


def icon(names, px):
    names = [names] if isinstance(names, str) else names
    for n in names:
        try:
            if THEME.has_icon(n):
                return Gtk.Image.new_from_pixbuf(THEME.load_icon(n, px, Gtk.IconLookupFlags.FORCE_SIZE))
        except Exception:
            pass
    return Gtk.Image.new_from_icon_name('application-x-executable', Gtk.IconSize.DIALOG)


_TILES = {}


def _dominant_hue(pb):
    """(hue, saturation) of the most colourful part of an icon pixbuf; greys fall back to a violet accent."""
    import colorsys
    sm = pb.scale_simple(12, 12, GdkPixbuf.InterpType.BILINEAR); px, n, rs = sm.get_pixels(), sm.get_n_channels(), sm.get_rowstride()
    best, w_tot, hs, ss = 0, 0, 0.0, 0.0
    for y in range(12):
        for x in range(12):
            o = y * rs + x * n; r, g, b = px[o] / 255, px[o + 1] / 255, px[o + 2] / 255; a = px[o + 3] / 255 if n == 4 else 1
            h, sat, v = colorsys.rgb_to_hsv(r, g, b); wgt = a * sat * v
            if wgt > 0.02: hs += h * wgt; ss += sat * wgt; w_tot += wgt
    if w_tot < 0.3: return 0.74, 0.5                                   # neutral icon -> violet tile (matches the OS accent)
    return hs / w_tot, min(1.0, ss / w_tot)


def tile_icon(names, px):
    """Modern app icon: rounded 'squircle' glass tile tinted from the icon's own colour, soft highlight, thin rim."""
    import colorsys
    names = [names] if isinstance(names, str) else names
    key = (tuple(names), px)
    if key in _TILES: return Gtk.Image.new_from_surface(_TILES[key])
    pb = None
    for n in names:
        try:
            if THEME.has_icon(n): pb = THEME.load_icon(n, int(px * 0.62), Gtk.IconLookupFlags.FORCE_SIZE); break
        except Exception: pass
    if pb is None: return icon(names, px)
    h, sat = _dominant_hue(pb)
    sf = cairo.ImageSurface(cairo.FORMAT_ARGB32, px, px); cr = cairo.Context(sf)
    r = px * 0.27
    top = colorsys.hsv_to_rgb(h, min(0.75, 0.35 + sat * 0.4), 0.46); bot = colorsys.hsv_to_rgb(h, min(0.85, 0.45 + sat * 0.4), 0.17)
    g = cairo.LinearGradient(0, 0, 0, px); g.add_color_stop_rgb(0, *top); g.add_color_stop_rgb(1, *bot)
    rrect(cr, 1, 1, px - 2, px - 2, r); cr.set_source(g); cr.fill_preserve(); cr.save(); cr.clip()
    hl = cairo.LinearGradient(0, 0, 0, px * 0.55); hl.add_color_stop_rgba(0, 1, 1, 1, 0.20); hl.add_color_stop_rgba(1, 1, 1, 1, 0.0)
    cr.set_source(hl); cr.rectangle(0, 0, px, px * 0.55); cr.fill()                                  # glossy top highlight
    glow = cairo.RadialGradient(px / 2, px * 1.05, px * 0.05, px / 2, px * 1.05, px * 0.7)
    glow.add_color_stop_rgba(0, *colorsys.hsv_to_rgb(h, 0.6, 1.0), 0.28); glow.add_color_stop_rgba(1, 0, 0, 0, 0)
    cr.set_source(glow); cr.paint(); cr.restore()                                                    # coloured glow from below
    rrect(cr, 1, 1, px - 2, px - 2, r); cr.set_source_rgba(1, 1, 1, 0.20); cr.set_line_width(1.2); cr.stroke()   # rim
    off = (px - pb.get_width()) / 2
    Gdk.cairo_set_source_pixbuf(cr, pb, off, off - px * 0.01); cr.paint()
    _TILES[key] = sf
    return Gtk.Image.new_from_surface(sf)


def appicon(names, px):
    """Icon for apps: modern tiles by default; ~/.config/rembley/icons containing 'flat' switches to plain icons."""
    try: flat = open(CFG + '/icons').read().strip() == 'flat'
    except OSError: flat = False
    return icon(names, px) if flat else tile_icon(names, px)


def sh(cmd):
    try:
        subprocess.Popen(cmd, shell=True, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def out(cmd, t=3):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t).stdout.strip()
    except Exception:
        return ''


def osk(show=True):
    sh('dbus-send --type=method_call --dest=org.onboard.Onboard /org/onboard/Onboard/Keyboard '
       'org.onboard.Onboard.Keyboard.%s' % ('Show' if show else 'Hide'))


def have(exe):
    return bool(shutil.which(exe.split()[0]))


class Gauge(Gtk.DrawingArea):
    def __init__(self, label, size=76):
        super().__init__(); self.label, self.val, self.text = label, 0.0, ''
        self.set_size_request(size, size)

    def set(self, val, text):
        self.val, self.text = val, text; self.queue_draw()

    def do_draw(self, cr):
        w, h = self.get_allocated_width(), self.get_allocated_height(); r = min(w, h) / 2 - 5
        cx, cy = w / 2, h / 2; cr.set_line_width(5); cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(1, 1, 1, 0.14); cr.arc(cx, cy, r, 0, 2 * math.pi); cr.stroke()
        if self.val > 0.005:
            g = cairo.LinearGradient(0, 0, w, h); g.add_color_stop_rgb(0, .55, .45, 1); g.add_color_stop_rgb(1, .86, .55, 1)
            cr.set_source(g); cr.arc(cx, cy, r, -math.pi / 2, -math.pi / 2 + 2 * math.pi * min(1, self.val)); cr.stroke()
        for txt, dy, size, a in ((self.label, -8, 13, 1.0), (self.text, 11, 11, 0.75)):
            cr.set_source_rgba(.93, .9, 1, a); cr.select_font_face('Noto Sans', 0, 1 if dy < 0 else 0); cr.set_font_size(size)
            ext = cr.text_extents(txt); cr.move_to(cx - ext.width / 2 - ext.x_bearing, cy + dy + 4); cr.show_text(txt)


class Avatar(Gtk.DrawingArea):
    """Round avatar: the fox from the Rembley logo (usr/share/rembley/avatar.png), vector cat as fallback."""
    _pb = {}

    def __init__(self, size=52):
        super().__init__(); self.size = size; self.set_size_request(size, size)
        key = size
        if key not in Avatar._pb:
            try: Avatar._pb[key] = GdkPixbuf.Pixbuf.new_from_file_at_size(os.path.join(SHARE, 'avatar.png'), size - 4, size - 4)
            except Exception: Avatar._pb[key] = None
        self.pb = Avatar._pb[key]

    def do_draw(self, cr):
        w, h = self.get_allocated_width(), self.get_allocated_height(); r = min(w, h) / 2 - 2
        if self.pb is not None:
            cr.set_source_rgba(0.72, 0.62, 1.0, 0.55); cr.arc(w / 2, h / 2, r + 1, 0, 2 * math.pi); cr.set_line_width(1.6); cr.stroke()
            Gdk.cairo_set_source_pixbuf(cr, self.pb, (w - self.pb.get_width()) / 2, (h - self.pb.get_height()) / 2); cr.paint(); return
        cx, cy = w / 2, h / 2 + 3
        g = cairo.LinearGradient(0, 0, w, h); g.add_color_stop_rgb(0, .85, .8, 1); g.add_color_stop_rgb(1, .55, .5, .9)
        cr.set_source(g); cr.arc(w / 2, h / 2, r, 0, 2 * math.pi); cr.fill()
        cr.set_source_rgb(.98, .97, 1); cr.arc(cx, cy, r * .62, 0, 2 * math.pi); cr.fill()
        for sgn in (-1, 1):
            cr.move_to(cx + sgn * r * .62, cy - r * .1); cr.line_to(cx + sgn * r * .5, cy - r * .85); cr.line_to(cx + sgn * r * .1, cy - r * .5); cr.close_path(); cr.fill()


def init_theme():
    """Call once after Gtk is loaded: dark theme, no animations, icon theme handle, CSS."""
    global THEME
    s = Gtk.Settings.get_default()
    s.set_property('gtk-application-prefer-dark-theme', True)
    s.set_property('gtk-enable-animations', False)                  # no animation: smoother on this SoC
    if not os.environ.get('REMBLEY_KEEP_THEME'):
        for k, v in (('gtk-theme-name', 'Adwaita'), ('gtk-icon-theme-name', 'Papirus-Dark'), ('gtk-font-name', 'Noto Sans 11')):
            try: s.set_property(k, v)
            except Exception: pass
    THEME = Gtk.IconTheme.get_default()
    p = Gtk.CssProvider(); p.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_USER)


def screen_size():
    sc = Gdk.Screen.get_default(); return sc.get_width(), sc.get_height()


def write_sys(path, value):
    try:
        with open(path, 'w') as f: f.write(str(value))
        return True
    except Exception:
        return False


def backlight_path():
    for p in ('/sys/class/leds/lcd-backlight/brightness', *sorted(glob.glob('/sys/class/backlight/*/brightness')),
              *sorted(glob.glob('/sys/class/leds/*/brightness'))):
        if os.path.exists(p) and os.access(p, os.W_OK): return p
    return None
