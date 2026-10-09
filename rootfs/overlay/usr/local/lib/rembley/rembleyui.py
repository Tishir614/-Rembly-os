#!/usr/bin/env python3
"""Shared UI toolkit for Rembley programs (glass panels, wallpaper blur, icons, helpers).

Glass look = a blurred copy of the wallpaper painted behind each panel (done once, so it costs
nothing while running). Windows: home (desktop layer), bar (dock + workspaces + tray, with strut),
launcher (all apps)."""
import glob, json, math, os, re, shutil, subprocess, sys, threading, time, urllib.request

import gi
gi.require_version('Gtk', '3.0'); gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio, Pango, GdkPixbuf
try:
    gi.require_version('GdkX11', '3.0'); from gi.repository import GdkX11
except Exception:
    GdkX11 = None
import cairo

DEMO = bool(os.environ.get('REMBLEY_DEMO'))          # fills widgets with sample data (screenshots only)
CFG = os.path.expanduser('~/.config/rembley'); os.makedirs(CFG, exist_ok=True)
SHARE = os.environ.get('REMBLEY_SHARE', '/usr/share/rembley')
BAR = 40
USER = os.environ.get('REMBLEY_USER') or (open(CFG + '/user').read().strip() if os.path.exists(CFG + '/user') else 'Rembley')

RU_DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
RU_MON = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']

CSS = b"""
window.rl-win { background-color: transparent; background-image: none; }
label { color: #ffffff; }
.rl-title { font-weight: 600; font-size: 15px; color: #ffffff; }
.clock { font-size: 66px; font-weight: 300; color: #ffffff; text-shadow: 0 0 20px rgba(255,255,255,0.95); }
.date { font-size: 17px; color: #ffffff; text-shadow: 0 0 8px rgba(220,220,220,0.9); }
.small { font-size: 12px; color: #eeeeee; }
.name { font-size: 16px; font-weight: 600; color: #ffffff; }
.online { font-size: 12px; color: #e6e6e6; }
.temp { font-size: 30px; color: #ffffff; }
.side-item { padding: 0 12px; border-radius: 14px; min-height: 42px; background-image: none; background-color: transparent;
             border: none; box-shadow: none; color: #ffffff; font-size: 15px; }
.side-item:hover, .side-item:active, .side-item.active { background-image: linear-gradient(90deg, rgba(196,196,196,0.60), rgba(205,205,205,0.38)); }
.tile { background-image: none; background-color: transparent; border: none; box-shadow: none; border-radius: 16px; padding: 6px 2px; color: #ffffff; font-size: 12px; }
.tile:hover, .tile:active { background-color: rgba(255,255,255,0.14); }
.dockbtn { background-image: none; background-color: transparent; border: none; box-shadow: none; border-radius: 16px; padding: 4px; min-width: 44px; min-height: 44px; }
.dockbtn:hover, .dockbtn:active { background-color: rgba(255,255,255,0.18); }
.ws { background-image: none; background-color: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.25); border-radius: 12px; color: #ffffff; min-width: 48px; min-height: 40px; padding: 0; font-size: 14px; box-shadow: none; }
.ws.cur { border: 2px solid #ffffff; background-color: rgba(255,255,255,0.28); }
.tray { color: #ffffff; font-size: 14px; }
.note-box { background-color: #fdfdfd; border-radius: 6px; }
.note-box textview, .note-box textview text { background-color: #fdfdfd; color: #3a3a3a; font-size: 14px; }
.note-title { color: #3a3a3a; font-weight: 600; font-size: 13px; }
.note-btn { background-image: none; background-color: transparent; border: none; box-shadow: none; color: #3a3a3a; min-width: 30px; min-height: 30px; padding: 0; font-size: 20px; }
.fab { padding: 0; margin: 0; min-width: 0; min-height: 0; border: none; border-radius: 15px; background-image: none; background-color: transparent; box-shadow: none; }
.fab:active { background-color: rgba(255,255,255,0.18); }
.mbtn { background-image: none; background-color: transparent; border: none; box-shadow: none; padding: 2px 10px; min-height: 40px; }
.mbtn:active { background-color: rgba(255,255,255,0.18); border-radius: 14px; }
.pad { background-image: none; background-color: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.30); border-radius: 36px;
       min-width: 72px; min-height: 72px; padding: 0; color: #ffffff; font-size: 28px; font-weight: 300; box-shadow: none; }
.pad:active { background-color: rgba(255,255,255,0.45); border-color: rgba(255,255,255,0.8); }
.pad-ok { background-color: rgba(255,255,255,0.40); border-color: rgba(255,255,255,0.7); }
.pad-small { font-size: 22px; }
.lockclock { font-size: 84px; font-weight: 200; color: #ffffff; text-shadow: 0 0 30px rgba(255,255,255,0.9); }
.lockhello { font-size: 20px; color: #ffffff; text-shadow: 0 0 10px rgba(220,220,220,0.9); }
.lockhint { font-size: 15px; color: #eeeeee; }
.lockbtn { background-image: linear-gradient(90deg, rgba(196,196,196,0.75), rgba(205,205,205,0.65)); border: none; border-radius: 30px; color: #ffffff; font-size: 20px; min-height: 60px; padding: 0 40px; box-shadow: 0 0 22px rgba(255,255,255,0.55); }
.rapp { background-image: linear-gradient(160deg, #1f1f1f, #2f2f2f 55%, #464646); color: #f6f6f6; }
.rapp label { color: #ffffff; }
.rapp label.small, .rapp .dim { color: #e8e8e8; }
.rcard { background-image: linear-gradient(160deg, rgba(255,255,255,0.12), rgba(255,255,255,0.05)); border: 1px solid rgba(255,255,255,0.28); border-radius: 20px; padding: 14px; }
.rcard-title { font-size: 17px; font-weight: 600; color: #ffffff; }
.rcard-big { font-size: 30px; font-weight: 300; color: #ffffff; text-shadow: 0 0 14px rgba(255,255,255,0.8); }
.rapp button { background-image: linear-gradient(90deg, rgba(235,235,235,0.80), rgba(225,225,225,0.72)); border: none; border-radius: 16px; color: #ffffff; min-height: 44px; text-shadow: none; box-shadow: 0 3px 12px rgba(0,0,0,0.30); padding: 0 18px; font-weight: 500; }
.rapp button:hover { background-image: linear-gradient(90deg, rgba(255,255,255,0.92), rgba(245,245,245,0.85)); }
.rapp button:active { background-image: linear-gradient(90deg, rgba(255,255,255,1), rgba(255,255,255,1)); }
.rapp button:disabled { opacity: 0.45; }
.rapp button.btn-danger { background-image: linear-gradient(90deg, rgba(255,255,255,0.92), rgba(220,220,220,0.88)); font-size: 18px; }
.rapp button.btn-neutral { background-image: none; background-color: rgba(255,255,255,0.12); box-shadow: none; }
.rapp button.btn-main { font-size: 18px; }

.rapp button.flat, .rapp .titlebutton { background-image: none; box-shadow: none; }
.rapp progressbar trough { background-color: rgba(255,255,255,0.12); border: none; border-radius: 10px; min-height: 14px; }
.rapp progressbar progress { background-image: linear-gradient(90deg, #ffffff, #ffffff); border: none; border-radius: 10px; min-height: 14px; }
.rapp progressbar text { color: #ffffff; font-size: 12px; }
.rapp treeview, .rapp treeview.view { background-color: transparent; color: #ffffff; }
.rapp treeview.view:selected { background-image: linear-gradient(90deg, rgba(196,196,196,0.60), rgba(205,205,205,0.55)); color: #ffffff; }
.rapp treeview header button { background-image: none; background-color: rgba(255,255,255,0.08); border-radius: 0; box-shadow: none; min-height: 38px; font-weight: 600; }
.rapp textview, .rapp textview text { background-color: rgba(30,30,30,0.45); color: #ffffff; border-radius: 14px; }
.rapp scrolledwindow { border-radius: 16px; }
.rapp entry { background-color: rgba(255,255,255,0.10); color: #ffffff; border: 1px solid rgba(255,255,255,0.35); border-radius: 14px; min-height: 40px; }
.rapp stacksidebar { background-color: rgba(30,30,30,0.35); }
.rapp stacksidebar row { min-height: 52px; padding: 0 14px; border-radius: 14px; margin: 2px 8px; }
.rapp stacksidebar row:selected { background-image: linear-gradient(90deg, rgba(196,196,196,0.65), rgba(205,205,205,0.50)); }
.rapp stack { background-color: transparent; }
.rapp scale trough { background-color: rgba(255,255,255,0.15); border-radius: 8px; min-height: 8px; }
.rapp scale highlight { background-image: linear-gradient(90deg, #ffffff, #ffffff); border-radius: 8px; }
.rapp scale slider { background-color: #ffffff; border-radius: 12px; min-width: 24px; min-height: 24px; }
.rapp list, .rapp listbox, .rapp viewport, .rapp .frame { background-color: rgba(30,30,30,0.30); border-radius: 16px; border-color: transparent; }
.rapp list row, .rapp listbox row { border-radius: 12px; min-height: 48px; margin: 3px 6px; padding: 2px 10px; background-color: rgba(255,255,255,0.06); }
.rapp list row:selected, .rapp listbox row:selected { background-image: linear-gradient(90deg, rgba(196,196,196,0.60), rgba(205,205,205,0.55)); }
.rapp notebook > header { background-color: rgba(30,30,30,0.35); border: none; }
.rapp notebook > header > tabs > tab { padding: 10px 22px; border-radius: 12px 12px 0 0; color: #eeeeee; }
.rapp notebook > header > tabs > tab:checked { background-image: linear-gradient(180deg, rgba(235,235,235,0.0), rgba(235,235,235,0.45)); color: #ffffff; box-shadow: inset 0 -3px 0 #ffffff; }
.rapp switch { background-color: rgba(255,255,255,0.18); border-radius: 16px; border: none; }
.rapp switch:checked { background-image: linear-gradient(90deg, #ffffff, #ffffff); }
.rapp switch slider { background-color: #ffffff; border-radius: 14px; border: none; }
.rapp combobox button, .rapp spinbutton button { min-height: 38px; }
.rapp checkbutton label { padding-left: 4px; }
entry.rl-search { background-color: rgba(255,255,255,0.12); color: #ffffff; border-radius: 14px; border: 1px solid rgba(255,255,255,0.3); min-height: 38px; }

.bar-lbl { font-family: 'Fira Code', 'DejaVu Sans Mono', monospace; font-size: 12px; color: #f4f4f4; }
.bar-btn { background-image: none; background-color: transparent; border: none; box-shadow: none; border-radius: 5px; padding: 0 5px; min-height: 24px; min-width: 22px; color: #f4f4f4; font-family: 'Fira Code', 'DejaVu Sans Mono', monospace; font-size: 12px; }
.bar-btn:hover, .bar-btn:active { background-color: rgba(255,255,255,0.22); }
.wsdot { background-image: none; background-color: transparent; border: none; box-shadow: none; padding: 0 3px; min-width: 16px; min-height: 24px; color: #e9e9e9; font-size: 13px; }
.wsdot.cur { color: #ffffff; text-shadow: 0 0 8px rgba(255,255,255,0.95); }
.mono { font-family: 'Fira Code', 'DejaVu Sans Mono', monospace; }
.ff-title { font-family: 'Fira Code', 'DejaVu Sans Mono', monospace; font-size: 13px; font-weight: 600; color: #d7d7d7; }
.ff-line { font-family: 'Fira Code', 'DejaVu Sans Mono', monospace; font-size: 12px; color: #d9d9d9; }
.ff-sep { font-family: 'Fira Code', 'DejaVu Sans Mono', monospace; font-size: 10px; color: #8d8d8d; }

/* ---- monochrome fox theme: black ground, white line work (overrides the generic palette above) ---- */
.rapp { background-image: linear-gradient(160deg, #080808, #121212 55%, #1b1b1b); color: #f2f2f2; }
.rapp button { background-image: linear-gradient(180deg, #262626, #0f0f0f); border: 1px solid rgba(240,240,240,0.82); border-radius: 6px; color: #f6f6f6; text-shadow: none;
               box-shadow: inset 0 0 0 2px rgba(0,0,0,0.70), inset 0 0 0 3px rgba(255,255,255,0.16); padding: 0 16px; min-height: 42px; font-weight: 500; }
.rapp button:hover { background-image: linear-gradient(180deg, #363636, #181818); border-color: #ffffff; }
.rapp button:active { background-image: none; background-color: #f4f4f4; color: #050505; }
.rapp button:disabled { opacity: 0.4; }
.rapp button.btn-danger { background-image: linear-gradient(180deg, #f6f6f6, #b9b9b9); color: #050505; border-color: #ffffff; font-size: 18px; }
.rapp button.btn-main { font-size: 18px; }
.rapp button.btn-neutral { background-image: none; background-color: rgba(255,255,255,0.06); box-shadow: none; }
.rapp progressbar trough { background-color: rgba(255,255,255,0.12); border-radius: 3px; }
.rapp progressbar progress { background-image: linear-gradient(90deg, #ffffff, #8c8c8c); border-radius: 3px; }
.rapp scale highlight { background-image: linear-gradient(90deg, #ffffff, #8c8c8c); border-radius: 3px; }
.rapp scale trough { border-radius: 3px; }
.rapp treeview.view:selected { background-image: none; background-color: rgba(255,255,255,0.18); color: #ffffff; }
.rapp stacksidebar row:selected, .rapp list row:selected, .rapp listbox row:selected { background-image: none; background-color: rgba(255,255,255,0.14); box-shadow: inset 3px 0 0 #ffffff; }
.rapp stacksidebar row, .rapp list row, .rapp listbox row { border-radius: 4px; }
.rapp switch:checked { background-image: linear-gradient(90deg, #ffffff, #9a9a9a); }
.rapp entry { border: 1px solid rgba(235,235,235,0.55); border-radius: 5px; background-color: rgba(255,255,255,0.06); }
.rapp textview, .rapp textview text { background-color: rgba(0,0,0,0.55); border-radius: 6px; }
.rcard { background-image: linear-gradient(160deg, rgba(255,255,255,0.07), rgba(255,255,255,0.02)); border: 1px solid rgba(235,235,235,0.55); border-radius: 8px; }
.rcard-big { text-shadow: 0 0 14px rgba(255,255,255,0.55); }
.clock, .lockclock { text-shadow: 0 0 22px rgba(255,255,255,0.65); }
.tile:hover, .tile:active, .dockbtn:hover, .dockbtn:active, .bar-btn:hover, .bar-btn:active { background-color: rgba(255,255,255,0.14); }
.pad { background-color: rgba(255,255,255,0.05); border: 1px solid rgba(240,240,240,0.7); border-radius: 6px; }
.pad:active { background-color: #f4f4f4; color: #050505; border-color: #ffffff; }
.pad-ok { background-color: rgba(255,255,255,0.16); }
.lockbtn { background-image: linear-gradient(180deg, #f6f6f6, #b9b9b9); color: #050505; border-radius: 6px; box-shadow: 0 0 22px rgba(255,255,255,0.35); }
.wsdot.cur { color: #ffffff; text-shadow: 0 0 8px rgba(255,255,255,0.9); }
.wsdot { color: #b5b5b5; }
.ff-title { color: #ffffff; } .ff-line { color: #d6d6d6; } .ff-sep { color: #777777; }
.bar-lbl, .bar-btn { color: #f0f0f0; }
"""

def load_wallpaper(w, h):
    """(sharp, blurred) cairo surfaces covering w x h. Native GdkPixbuf only (no PIL): scale-to-cover, then the glass blur is a
    cheap down/up-scale (box-like blur) done once at startup."""
    path = os.environ.get('REMBLEY_WALL') or next((p for p in (CFG + '/wallpaper.png', CFG + '/wallpaper.jpg',
                                                               SHARE + '/wallpaper.png') if os.path.exists(p)), None)
    pb = None
    if path:
        try: pb = GdkPixbuf.Pixbuf.new_from_file(path)
        except Exception: pb = None
    if pb is None:
        pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, w, h); pb.fill(0x1e1646ff)
    s = max(w / pb.get_width(), h / pb.get_height())
    sw_, sh_ = max(w, math.ceil(pb.get_width() * s)), max(h, math.ceil(pb.get_height() * s))
    pb = pb.scale_simple(sw_, sh_, GdkPixbuf.InterpType.BILINEAR)
    pb = pb.new_subpixbuf((sw_ - w) // 2, (sh_ - h) // 2, w, h)
    small = pb.scale_simple(max(1, w // 8), max(1, h // 8), GdkPixbuf.InterpType.HYPER)          # 1/8: averages 8x8 blocks
    small = small.scale_simple(max(1, w // 24), max(1, h // 24), GdkPixbuf.InterpType.HYPER)     # 1/24: soft glass
    blur = small.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
    return Gdk.cairo_surface_create_from_pixbuf(pb, 1, None), Gdk.cairo_surface_create_from_pixbuf(blur, 1, None)


def rrect(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0); cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi); cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()


class Glass(Gtk.Box):
    """Rounded translucent panel painted from the blurred wallpaper. Content lives in self.inner,
    so padding is done with margins (border_width would shift the draw origin)."""
    def __init__(self, radius=5, tint=(0.04, 0.04, 0.04, 0.82), orientation=Gtk.Orientation.HORIZONTAL, spacing=0, **kw):
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
        cr.set_source_rgba(*self.tint); cr.paint()
        sheen = cairo.LinearGradient(0, 0, 0, min(h, 220)); sheen.add_color_stop_rgba(0, 1, 1, 1, 0.06); sheen.add_color_stop_rgba(1, 1, 1, 1, 0)   # light falling on glass
        cr.set_source(sheen); cr.paint(); cr.restore()
        rrect(cr, 0.75, 0.75, w - 1.5, h - 1.5, self.radius)
        edge = cairo.LinearGradient(0, 0, w, h); edge.add_color_stop_rgba(0, 1, 1, 1, 0.95); edge.add_color_stop_rgba(0.5, 0.82, 0.82, 0.82, 0.80); edge.add_color_stop_rgba(1, 1, 1, 1, 0.90)
        cr.set_source(edge); cr.set_line_width(1.8); cr.stroke()                  # thin light-pink frame, like a tiled window
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
        extra = getattr(self, 'paint_extra', None)
        if extra is not None: extra(cr)                      # animated sprites between the wallpaper and the widgets
        return Gtk.Window.do_draw(self, cr)


THEME = None


def icon(names, px):
    names = [names] if isinstance(names, str) else names
    pb, _ = load_icon_pixbuf(names, px)
    if pb is not None: return Gtk.Image.new_from_pixbuf(pb)
    return Gtk.Image.new_from_icon_name('application-x-executable', Gtk.IconSize.DIALOG)


_TILES = {}
ICON_CACHE = os.path.join(os.path.expanduser('~'), '.cache', 'rembley', 'icons')
TILE_VER = 'm1'


def _cache_path(kind, name, px):
    try:
        th = Gtk.Settings.get_default().get_property('gtk-icon-theme-name') or 'x'
    except Exception:
        th = 'x'
    return os.path.join(ICON_CACHE, '%s_%s_%s_%s_%d.png' % (kind, TILE_VER, th, name.replace('/', '_'), px))


def _mono_pixbuf(pb):
    """White glyph from any (coloured) icon: its alpha shape, with the darker half of its own tones cut out, so the icon becomes white line work.
    Flat single-tone icons become solid white silhouettes. Runs once per icon (result is cached on disk)."""
    try:
        from PIL import Image, ImageChops
        w, h, n, rs = pb.get_width(), pb.get_height(), pb.get_n_channels(), pb.get_rowstride()
        mode = 'RGBA' if n == 4 else 'RGB'
        im = Image.frombuffer(mode, (w, h), pb.get_pixels(), 'raw', mode, rs, 1).convert('RGBA')
        a = im.getchannel('A'); L = im.convert('L')
        vals = sorted(v for v, av in zip(L.getdata(), a.getdata()) if av > 128)
        if not vals: return pb
        med = vals[len(vals) // 2]; spread = vals[int(len(vals) * 0.9)] - vals[int(len(vals) * 0.1)]
        if spread < 14: alpha = a                                                       # one tone: plain white silhouette
        else:
            lut = [max(0, min(255, int((v - (med - 22)) * 255 / 44))) for v in range(256)]
            alpha = ImageChops.multiply(a, L.point(lut))
        out = Image.new('RGBA', (w, h), (255, 255, 255, 0)); out.putalpha(alpha)
        return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(out.tobytes()), GdkPixbuf.Colorspace.RGB, True, 8, w, h, w * 4)
    except Exception:
        return pb


def load_icon_pixbuf(names, px):
    """Theme icon as a WHITE glyph Pixbuf (symbolic variant if the theme has one, otherwise the coloured icon turned into white line work),
    rendered ONCE and kept as a PNG on disk (SVG rendering costs ~13 ms each on a fast PC, far more on the A53)."""
    for n in names:
        cp = _cache_path('i', n, px)
        try:
            if os.path.exists(cp): return GdkPixbuf.Pixbuf.new_from_file(cp), n
        except Exception: pass
        try:
            pb = None
            sym = n + '-symbolic'
            if THEME.has_icon(sym):
                info = THEME.lookup_icon(sym, px, Gtk.IconLookupFlags.FORCE_SIZE)
                if info is not None: pb = info.load_symbolic(Gdk.RGBA(1, 1, 1, 1), None, None, None)[0]
            if pb is None and THEME.has_icon(n):
                pb = _mono_pixbuf(THEME.load_icon(n, px, Gtk.IconLookupFlags.FORCE_SIZE))
            if pb is not None:
                try: os.makedirs(ICON_CACHE, exist_ok=True); pb.savev(cp, 'png', [], [])
                except Exception: pass
                return pb, n
        except Exception: pass
    return None, None


def _dominant_hue(pb):
    """(hue, saturation) of the most colourful part of an icon pixbuf; greys fall back to a violet accent."""
    import colorsys
    sm = pb.scale_simple(12, 12, GdkPixbuf.InterpType.BILINEAR); px, n, rs = sm.get_pixels(), sm.get_n_channels(), sm.get_rowstride()
    w_tot, hs, ss = 0, 0.0, 0.0
    for y in range(12):
        for x in range(12):
            o = y * rs + x * n; r, g, b = px[o] / 255, px[o + 1] / 255, px[o + 2] / 255; a = px[o + 3] / 255 if n == 4 else 1
            h, sat, v = colorsys.rgb_to_hsv(r, g, b); wgt = a * sat * v
            if wgt > 0.02: hs += h * wgt; ss += sat * wgt; w_tot += wgt
    if w_tot < 0.3: return 0.74, 0.5                                   # neutral icon -> violet tile (matches the OS accent)
    return hs / w_tot, min(1.0, ss / w_tot)


def tile_icon(names, px):
    """App icon in the style of the reference sheet: a near-black rounded square with a bevelled light frame and a white glyph."""
    names = [names] if isinstance(names, str) else names
    key = (tuple(names), px)
    if key in _TILES: return Gtk.Image.new_from_surface(_TILES[key])
    tp = _cache_path('t', names[0], px)
    try:                                            # finished tile cached on disk by an earlier run
        if os.path.exists(tp):
            _TILES[key] = cairo.ImageSurface.create_from_png(tp); return Gtk.Image.new_from_surface(_TILES[key])
    except Exception: pass
    pb, used = load_icon_pixbuf(names, int(px * 0.56))
    if pb is None: return icon(names, px)
    tp = _cache_path('t', used, px)
    sf = cairo.ImageSurface(cairo.FORMAT_ARGB32, px, px); cr = cairo.Context(sf)
    r = px * 0.17
    g = cairo.LinearGradient(0, 0, 0, px); g.add_color_stop_rgb(0, 0.17, 0.17, 0.17); g.add_color_stop_rgb(1, 0.045, 0.045, 0.045)
    rrect(cr, 1.5, 1.5, px - 3, px - 3, r); cr.set_source(g); cr.fill()
    rrect(cr, 1.5, 1.5, px - 3, px - 3, r); cr.set_source_rgba(0.94, 0.94, 0.94, 0.96); cr.set_line_width(max(1.6, px * 0.04)); cr.stroke()          # outer light frame
    i = px * 0.085; rrect(cr, i, i, px - 2 * i, px - 2 * i, max(1, r - i * 0.6)); cr.set_source_rgba(0, 0, 0, 0.75); cr.set_line_width(max(1.0, px * 0.026)); cr.stroke()   # dark groove
    i2 = px * 0.105; rrect(cr, i2, i2, px - 2 * i2, px - 2 * i2, max(1, r - i2 * 0.6)); cr.set_source_rgba(1, 1, 1, 0.20); cr.set_line_width(1.0); cr.stroke()           # inner highlight
    off = (px - pb.get_width()) / 2
    Gdk.cairo_set_source_pixbuf(cr, pb, off, off); cr.paint()
    _TILES[key] = sf
    try: os.makedirs(ICON_CACHE, exist_ok=True); sf.write_to_png(tp)
    except Exception: pass
    return Gtk.Image.new_from_surface(sf)


def appicon(names, px):
    """Icon for apps: modern tiles by default; ~/.config/rembley/icons containing 'flat' switches to plain icons."""
    try: flat = open(CFG + '/icons').read().strip() == 'flat'
    except OSError: flat = False
    return icon(names, px) if flat else tile_icon(names, px)


def _low_priority():
    """Child setup: programs started from the desktop run at lower CPU/IO priority than Xorg, the window manager and this shell,
    so one heavy app cannot freeze the touch UI."""
    try:
        os.nice(10)
        import platform
        nr = {'armv7l': 314, 'armv8l': 314, 'aarch64': 30, 'x86_64': 251}.get(platform.machine())
        if nr:
            import ctypes
            ctypes.CDLL(None, use_errno=True).syscall(nr, 1, 0, (2 << 13) | 6)     # ioprio_set(IOPRIO_WHO_PROCESS, self, best-effort level 6)
    except Exception:
        pass


def sh(cmd):
    try:
        subprocess.Popen(cmd, shell=True, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=_low_priority)
    except Exception:
        pass


def launch_gapp(app):
    """Start a Gio.DesktopAppInfo through sh() so it gets the low priority above (Terminal=true apps go through Gio's own launcher)."""
    try:
        cmd = re.sub(r'%[a-zA-Z%]', '', app.get_commandline() or '').strip()
        if cmd and not app.get_boolean('Terminal'):
            sh('rembley-guard ' + cmd); return
    except Exception:
        pass
    app.launch([], None)


def motion_mode():
    """'full' | 'reduced' | 'off' (Settings -> Screen -> Animations)."""
    try:
        v = open(CFG + '/motion').read().strip()
        return v if v in ('full', 'reduced', 'off') else 'full'
    except OSError:
        return 'full'


def system_busy():
    """True when animations should stand down: high load, battery saver, or low battery."""
    try:
        if os.path.exists('/run/rembley/eco'): return True
        if float(open('/proc/loadavg').read().split()[0]) > 1.6: return True
    except Exception:
        pass
    return False


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
            cr.set_source_rgba(1, 1, 1, 0.85); cr.arc(w / 2, h / 2, r + 1, 0, 2 * math.pi); cr.set_line_width(1.6); cr.stroke()
            Gdk.cairo_set_source_pixbuf(cr, self.pb, (w - self.pb.get_width()) / 2, (h - self.pb.get_height()) / 2); cr.paint(); return
        cx, cy = w / 2, h / 2 + 3
        g = cairo.LinearGradient(0, 0, w, h); g.add_color_stop_rgb(0, .85, .8, 1); g.add_color_stop_rgb(1, .55, .5, .9)
        cr.set_source(g); cr.arc(w / 2, h / 2, r, 0, 2 * math.pi); cr.fill()
        cr.set_source_rgb(.98, .97, 1); cr.arc(cx, cy, r * .62, 0, 2 * math.pi); cr.fill()
        for sgn in (-1, 1):
            cr.move_to(cx + sgn * r * .62, cy - r * .1); cr.line_to(cx + sgn * r * .5, cy - r * .85); cr.line_to(cx + sgn * r * .1, cy - r * .5); cr.close_path(); cr.fill()


def install_crash_handler():
    """Uncaught exceptions in any Rembley program: full traceback into /var/log/rembley-crash.log + one notification (rate-limited)."""
    import traceback
    name = os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else 'rembley'
    prev, last = sys.excepthook, [0.0]

    def hook(et, ev, tb):
        try:
            with open('/var/log/rembley-crash.log', 'a') as f:
                f.write('\n==== %s %s\n%s' % (time.strftime('%F %T'), name, ''.join(traceback.format_exception(et, ev, tb))))
            if time.time() - last[0] > 30:
                last[0] = time.time()
                subprocess.Popen(['notify-send', '-u', 'critical', 'Ошибка в %s' % name, 'Подробности: /var/log/rembley-crash.log (их соберёт rembley-report)'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        prev(et, ev, tb)
    sys.excepthook = hook


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
    install_crash_handler()
    THEME = Gtk.IconTheme.get_default()
    p = Gtk.CssProvider(); p.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_USER)


def style_app(win):
    """Colourful app look (gradient background, rounded gradient buttons/bars/rows) for ordinary windows; needs init_theme() first."""
    win.get_style_context().add_class('rapp')


def card(title=None, spacing=8):
    """Rounded translucent card; returns the box to pack into (the card widget itself is box.card)."""
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing); b.get_style_context().add_class('rcard')
    if title:
        t = Gtk.Label(label=title, xalign=0); t.get_style_context().add_class('rcard-title'); b.pack_start(t, False, False, 0)
    return b


class Meter(Gtk.DrawingArea):
    """Coloured bar with an icon dot, a title and a value: one per storage category / memory / load."""
    def __init__(self, title, c1=(1.0, 1.0, 1.0), c2=(0.55, 0.55, 0.55), emoji=''):
        super().__init__(); self.title, self.val, self.frac, self.c1, self.c2, self.emoji = title, '…', 0.0, c1, c2, emoji
        self.set_size_request(-1, 64)

    def set(self, frac, val):
        self.frac, self.val = max(0.0, min(1.0, frac)), val; self.queue_draw()

    def do_draw(self, cr):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        cr.arc(24, 24, 18, 0, 6.2832); cr.set_source_rgba(0.05, 0.05, 0.05, 1); cr.fill_preserve(); cr.set_source_rgba(0.94, 0.94, 0.94, 0.9); cr.set_line_width(1.6); cr.stroke()
        cr.select_font_face('Noto Sans', 0, 1); cr.set_font_size(18); cr.set_source_rgb(1, 1, 1)
        e = cr.text_extents(self.emoji or self.title[:1]); cr.move_to(24 - e.width / 2 - e.x_bearing, 24 - e.height / 2 - e.y_bearing); cr.show_text(self.emoji or self.title[:1])
        cr.select_font_face('Noto Sans', 0, 1); cr.set_font_size(15); cr.set_source_rgb(0.97, 0.95, 1); cr.move_to(54, 20); cr.show_text(self.title)
        cr.select_font_face('Noto Sans', 0, 0); cr.set_font_size(14); cr.set_source_rgb(0.82, 0.77, 0.97)
        e = cr.text_extents(self.val); cr.move_to(w - e.width - 4, 20); cr.show_text(self.val)
        bx, by, bw, bh = 54, 32, w - 58, 14
        rrect(cr, bx, by, bw, bh, 7); cr.set_source_rgba(1, 1, 1, 0.12); cr.fill()
        if self.frac > 0:
            fw = max(bh, bw * self.frac); rrect(cr, bx, by, fw, bh, 7)
            g = cairo.LinearGradient(bx, 0, bx + bw, 0); g.add_color_stop_rgb(0, *self.c1); g.add_color_stop_rgb(1, *self.c2); cr.set_source(g); cr.fill()


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
