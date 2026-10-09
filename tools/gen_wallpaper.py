#!/usr/bin/env python3
"""Sakura wallpaper (procedural): hot-pink hair-like flows, soft bokeh, large lilies and drifting petals on a dark mauve ground - the colours of the
reference rice. It is NOT the artist's picture (that file is not available at usable resolution): put your own image at ~/.config/rembley/wallpaper.png
(or Settings) and every panel recolours its glass from it automatically.
usage: tools/gen_wallpaper.py [OUT.png] [W H]"""
import math, os, random, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'rootfs/overlay/usr/share/rembley/wallpaper.png')
W, H = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (1920, 1200)
rnd = random.Random(7)

# 1. ground: dark mauve -> deep magenta -> rose (diagonal)
y, x = np.mgrid[0:H, 0:W].astype(np.float32); t = np.clip((x / W * 0.55 + (1 - y / H) * 0.65) / 1.2, 0, 1)
stops = [(0.0, (26, 10, 26)), (0.3, (96, 22, 74)), (0.62, (214, 60, 132)), (1.0, (255, 150, 196))]
img = np.zeros((H, W, 3), np.float32)
for (a, ca), (b, cb) in zip(stops, stops[1:]):
    m = (t >= a) & (t <= b); k = ((t - a) / (b - a))[..., None]
    img = np.where(m[..., None], np.array(ca, np.float32) * (1 - k) + np.array(cb, np.float32) * k, img)
base = Image.fromarray(img.astype(np.uint8)).convert('RGBA')


TRANS = (255, 205, 228, 0)          # transparent pixels carry a PINK colour, so blurring never creates dark fringes


def layer(): return Image.new('RGBA', (W, H), TRANS)


def blur(im, r): return im.filter(ImageFilter.GaussianBlur(r))


# 2. big soft light blobs
lay = layer(); d = ImageDraw.Draw(lay)
for _ in range(14):
    cx, cy, r = rnd.randrange(W), rnd.randrange(H), rnd.randrange(160, 420)
    col = rnd.choice([(255, 150, 200), (230, 90, 150), (255, 215, 232), (160, 40, 110)]); d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (rnd.randrange(40, 90),))
base = Image.alpha_composite(base, blur(lay, 90))

# 3. flowing "hair" strands: long bezier-like curves, mostly top/centre, soft
lay = layer(); d = ImageDraw.Draw(lay)
for i in range(70):
    x0, y0 = rnd.randrange(-200, W), rnd.randrange(-100, H // 2)
    amp, ph, L = rnd.uniform(80, 260), rnd.uniform(0, 6.28), rnd.randrange(700, 1500)
    pts = [(x0 + s * 0.55 + math.sin(s / 260 + ph) * amp * 0.5, y0 + s * 0.8 + math.cos(s / 310 + ph) * amp * 0.35) for s in range(0, L, 12)]
    col = rnd.choice([(255, 190, 220), (255, 130, 185), (250, 235, 245), (190, 60, 120)])
    d.line(pts, fill=col + (rnd.randrange(25, 70),), width=rnd.randrange(3, 16), joint='curve')
base = Image.alpha_composite(base, blur(lay, 5))
base = Image.alpha_composite(base, blur(lay, 22))


def petal(size, color, alpha):
    p = Image.new('RGBA', (size * 2, size * 2), color + (0,)); dd = ImageDraw.Draw(p)
    dd.ellipse([size * 0.55, size * 0.2, size * 1.45, size * 1.8], fill=color + (alpha,))
    return p


def lily(cx, cy, R, rot):
    """six-petal lily: pointed petals with a pink throat"""
    lay_ = layer(); l = Image.new('RGBA', (R * 3, R * 3), (255, 245, 250, 0)); dd = ImageDraw.Draw(l); c = R * 1.5
    for k in range(6):
        a = rot + k * math.pi / 3
        tip = (c + math.cos(a) * R, c + math.sin(a) * R); l1 = (c + math.cos(a - 0.35) * R * 0.45, c + math.sin(a - 0.35) * R * 0.45); l2 = (c + math.cos(a + 0.35) * R * 0.45, c + math.sin(a + 0.35) * R * 0.45)
        dd.polygon([(c, c), l1, tip, l2], fill=(255, 245, 250, 235))
        dd.line([(c, c), tip], fill=(255, 170, 205, 200), width=max(2, R // 28))
    dd.ellipse([c - R * 0.12, c - R * 0.12, c + R * 0.12, c + R * 0.12], fill=(255, 150, 190, 255))
    l = blur(l, 1.6); lay_.paste(l, (int(cx - c), int(cy - c)), l); return lay_


for (cx, cy, R, rot, bl) in [(1500, 330, 260, 0.4, 2), (1180, 560, 150, 1.1, 5), (1720, 760, 190, 0.1, 9), (330, 180, 120, 0.7, 14)]:
    base = Image.alpha_composite(base, blur(lily(cx, cy, R, rot), bl))

# 4. drifting petals (depth of field: bigger = blurrier)
for _ in range(70):
    s = rnd.choice([10, 14, 20, 30, 46, 70]); p = petal(s, rnd.choice([(255, 215, 232), (255, 160, 200), (255, 245, 250)]), rnd.randrange(120, 230))
    p = p.rotate(rnd.uniform(0, 360), expand=True, fillcolor=None); p = blur(p, s / 14)
    lay = layer(); px, py = int(rnd.gauss(W * 0.62, W * 0.3)), int(rnd.gauss(H * 0.45, H * 0.32)); lay.paste(p, (px, py), p); base = Image.alpha_composite(base, lay)

# 5. bokeh dots + vignette + grain
lay = layer(); d = ImageDraw.Draw(lay)
for _ in range(40):
    cx, cy, r = rnd.randrange(W), rnd.randrange(H), rnd.randrange(8, 38); d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 235, 245, rnd.randrange(25, 70)))
base = Image.alpha_composite(base, blur(lay, 3))
a = np.asarray(base.convert('RGB')).astype(np.float32)
vy, vx = np.mgrid[0:H, 0:W].astype(np.float32); v = 1 - 0.55 * np.clip(((vx / W - 0.55) ** 2 + (vy / H - 0.45) ** 2) * 1.9, 0, 1)
a = a * v[..., None] + np.random.default_rng(3).normal(0, 2.2, a.shape)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(OUT, optimize=True)
print('wrote', OUT, os.path.getsize(OUT) // 1024, 'KiB')
