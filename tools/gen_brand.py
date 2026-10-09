#!/usr/bin/env python3
"""Black-and-white brand assets from the fox logo (assets/logo-fox-source.jpg):
  logo-mark.png        the fox, white on transparent             logo-mark-small.png   same, 128 px (bar)
  wordmark.png         "REMBLY OS", hand-built angular lettering: mitred corners, pointed cut terminals - the same language as the fox's ears and whiskers
  logo.png             mark above wordmark on black (1024 sq)    logo-small.png        same, 520 px (about / lock)
  avatar.png           mark in a black frame (256 px)
usage: tools/gen_brand.py [OUTDIR]  (default rootfs/overlay/usr/share/rembly; assets/ gets logo-mark.png + wordmark.png too)"""
import math, os, sys
import cairo
import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'rootfs/overlay/usr/share/rembly')
os.makedirs(OUT, exist_ok=True)


# ---------- the fox: luminance -> alpha, cropped ----------
src = Image.open(os.path.join(ROOT, 'assets/logo-fox-source.jpg')).convert('L'); a = np.asarray(src).astype(np.float32)
alpha = np.clip((a - 40) / 170, 0, 1); alpha = alpha * alpha * (3 - 2 * alpha)             # smoothstep: kills JPEG noise, keeps clean edges
ys, xs = np.where(alpha > 0.25); x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
pad = int(0.04 * max(x1 - x0, y1 - y0))
box = (max(0, x0 - pad), max(0, y0 - pad), min(alpha.shape[1], x1 + pad), min(alpha.shape[0], y1 + pad))
al = Image.fromarray((alpha * 255).astype(np.uint8)).crop(box)
mark = Image.new('RGBA', al.size, (255, 255, 255, 0)); mark.putalpha(al)
mark.save(os.path.join(ROOT, 'assets/logo-mark.png')); mark.save(os.path.join(OUT, 'logo-mark.png'))
s = 128 / max(mark.size); mark.resize((int(mark.width * s), int(mark.height * s)), Image.LANCZOS).save(os.path.join(OUT, 'logo-mark-small.png'))


# ---------- wordmark: strokes on a 0..100 grid (x, y), mitred joins, butt caps ----------
LET = {
    'R': [[(0, 100), (0, 0), (56, 0), (72, 14), (72, 36), (56, 50), (0, 50)], [(34, 50), (74, 100)]],
    'E': [[(72, 0), (0, 0), (0, 100), (72, 100)], [(0, 50), (56, 50)]],
    'M': [[(0, 100), (0, 0), (42, 58), (84, 0), (84, 100)]],
    'B': [[(0, 100), (0, 0), (50, 0), (64, 12), (64, 38), (50, 50), (0, 50)], [(0, 50), (56, 50), (70, 63), (70, 88), (56, 100), (0, 100)]],
    'L': [[(0, 0), (0, 100), (64, 100)]],
    'Y': [[(0, 0), (38, 52), (76, 0)], [(38, 52), (38, 100)]],
    'O': [[(22, 0), (54, 0), (76, 22), (76, 78), (54, 100), (22, 100), (0, 78), (0, 22), (22, 0)]],
    'S': [[(72, 0), (12, 0), (0, 12), (0, 38), (12, 50), (64, 50), (76, 62), (76, 88), (64, 100), (4, 100)]],
}
ADV = {'R': 74, 'E': 72, 'M': 84, 'B': 70, 'L': 64, 'Y': 76, 'O': 76, 'S': 76, ' ': 40}


def wordmark(text='REMBLY OS', cap=180, stroke=21, gap=30, ss=3):
    scale = cap / 100.0; w = int(sum(ADV[c] * scale + gap for c in text) + 40); h = int(cap + 40)
    sf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * ss, h * ss); cr = cairo.Context(sf); cr.scale(ss * scale, ss * scale)
    cr.set_source_rgba(1, 1, 1, 1); cr.set_line_width(stroke / scale); cr.set_line_join(cairo.LINE_JOIN_MITER); cr.set_miter_limit(8); cr.set_line_cap(cairo.LINE_CAP_BUTT)
    x = 20 / scale
    for ch in text:
        for path in LET.get(ch, []):
            cr.move_to(x + path[0][0], 10 / scale + path[0][1])
            for px, py in path[1:]: cr.line_to(x + px, 10 / scale + py)
            cr.stroke()
        x += ADV[ch] + gap / scale
    im = Image.frombuffer('RGBA', (w * ss, h * ss), bytes(sf.get_data()), 'raw', 'BGRA', 0, 1).resize((w, h), Image.LANCZOS)
    bb = im.getchannel('A').point(lambda v: 255 if v > 20 else 0).getbbox(); return im.crop(bb)


wm = wordmark(); wm.save(os.path.join(ROOT, 'assets/wordmark.png')); wm.save(os.path.join(OUT, 'wordmark.png'))


def stacked(size):
    """mark above wordmark, centred on black"""
    can = Image.new('RGBA', (size, size), (0, 0, 0, 255))
    mw = int(size * 0.50); m = mark.resize((mw, int(mark.height * mw / mark.width)), Image.LANCZOS)
    ww = int(size * 0.74); wmk = wm.resize((ww, int(wm.height * ww / wm.width)), Image.LANCZOS)
    total = m.height + int(size * 0.07) + wmk.height; top = (size - total) // 2
    can.alpha_composite(m, ((size - m.width) // 2, top)); can.alpha_composite(wmk, ((size - ww) // 2, top + m.height + int(size * 0.07)))
    return can


stacked(1024).convert('RGB').save(os.path.join(OUT, 'logo.png')); stacked(520).convert('RGB').save(os.path.join(OUT, 'logo-small.png'))
av = Image.new('RGBA', (256, 256), (0, 0, 0, 255)); mm = mark.resize((176, int(mark.height * 176 / mark.width)), Image.LANCZOS); av.alpha_composite(mm, (40, (256 - mm.height) // 2))
av.convert('RGB').save(os.path.join(OUT, 'avatar.png'))
print('brand assets ->', OUT, '| wordmark', wm.size, '| mark', mark.size)
