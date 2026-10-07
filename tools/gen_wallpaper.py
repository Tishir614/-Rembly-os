#!/usr/bin/env python3
"""Procedural 'night portal' wallpaper for Rembley OS (original artwork, no external assets).
usage: gen_wallpaper.py OUT.png [W H]   default 1280x800"""
import math, random, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W = int(sys.argv[2]) if len(sys.argv) > 3 else 1280
H = int(sys.argv[3]) if len(sys.argv) > 3 else 800
rnd = random.Random(73)
y, x = np.mgrid[0:H, 0:W].astype(np.float32)
# sky gradient: deep indigo top -> violet -> magenta haze at the floor
t = y / H
top, mid, low = np.array([10, 8, 38]), np.array([46, 28, 98]), np.array([118, 62, 150])
col = np.where(t[..., None] < .6, top + (mid - top) * (t[..., None] / .6),
               mid + (low - mid) * ((t[..., None] - .6) / .4))
# portal glow (right of centre)
cx, cy, R = W * .55, H * .52, H * .36
d = np.hypot(x - cx, y - cy)
glow = np.exp(-((d - R) / (R * .55)) ** 2)[..., None]
col += glow * np.array([70, 55, 120])
inside = (d < R)[..., None]
col = np.where(inside, col * .55 + np.array([95, 80, 175]) * (1 - d[..., None] / R) * .55 + 30, col)
img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).convert('RGB')

def layer(): return Image.new('RGBA', (W, H), (0, 0, 0, 0))
# stars
st = layer(); sd = ImageDraw.Draw(st)
for _ in range(420):
    sx, sy = rnd.randrange(W), rnd.randrange(int(H * .75)); r = rnd.choice([.6, .8, 1, 1, 1.4, 2])
    a = rnd.randrange(90, 255); sd.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(235, 230, 255, a))
for _ in range(14):                         # sparkle stars
    sx, sy = rnd.randrange(W), rnd.randrange(int(H * .6)); L = rnd.randrange(6, 14)
    sd.line([sx - L, sy, sx + L, sy], fill=(255, 255, 255, 200), width=1)
    sd.line([sx, sy - L, sx, sy + L], fill=(255, 255, 255, 200), width=1)
img = Image.alpha_composite(img.convert('RGBA'), st.filter(ImageFilter.GaussianBlur(.6)))

# portal ring
ring = layer(); rd = ImageDraw.Draw(ring)
for i, (rr, w, a) in enumerate([(R + 18, 14, 200), (R + 42, 5, 120), (R - 12, 4, 160)]):
    rd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(200, 190, 255, a), width=w)
img = Image.alpha_composite(img, ring.filter(ImageFilter.GaussianBlur(1.2)))
img = Image.alpha_composite(img, ring.filter(ImageFilter.GaussianBlur(14)))

# crescent moon (top-left of centre)
mx, my, mr = W * .30, H * .17, 46
moon = layer(); md = ImageDraw.Draw(moon)
md.ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=(222, 214, 255, 255))
md.ellipse([mx - mr + 24, my - mr - 6, mx + mr + 24, my + mr - 6], fill=(0, 0, 0, 0))
mask = Image.new('L', (W, H), 0); ImageDraw.Draw(mask).ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=255)
ImageDraw.Draw(mask).ellipse([mx - mr + 24, my - mr - 6, mx + mr + 24, my + mr - 6], fill=0)
moon.putalpha(mask)
img = Image.alpha_composite(img, moon.filter(ImageFilter.GaussianBlur(14)))
img = Image.alpha_composite(img, moon)

# floating islands inside the portal (castle silhouette on the biggest)
isl = layer(); idr = ImageDraw.Draw(isl)
def island(px, py, w, h, c):
    pts = [(px - w / 2, py)]
    for k in range(1, 9): pts.append((px - w / 2 + w * k / 9, py + rnd.uniform(-h * .06, h * .06)))
    pts += [(px + w / 2, py), (px + w * .28, py + h * .5), (px + w * .06, py + h), (px - w * .12, py + h * .62), (px - w * .34, py + h * .38)]
    idr.polygon(pts, fill=c)
c = (22, 16, 52, 255)
island(cx, cy + R * .25, R * 1.1, R * .42, c)
bx = cx                                    # castle towers
for dx, hh, ww in [(-60, 80, 22), (-25, 140, 26), (10, 190, 30), (45, 120, 24), (78, 70, 20)]:
    idr.rectangle([bx + dx - ww / 2, cy + R * .25 - hh, bx + dx + ww / 2, cy + R * .25], fill=c)
    idr.polygon([(bx + dx - ww / 2 - 3, cy + R * .25 - hh), (bx + dx, cy + R * .25 - hh - ww * 1.8), (bx + dx + ww / 2 + 3, cy + R * .25 - hh)], fill=c)
island(cx - R * .62, cy - R * .12, R * .30, R * .16, (30, 22, 66, 255))
island(cx + R * .66, cy - R * .30, R * .24, R * .13, (30, 22, 66, 255))
island(cx + R * .30, cy + R * .62, R * .20, R * .10, (26, 19, 58, 255))
# clip islands to the portal disc for a "window" feel, keep a few outside as debris
clip = Image.new('L', (W, H), 0); ImageDraw.Draw(clip).ellipse([cx - R, cy - R, cx + R, cy + R], fill=255)
a = isl.split()[3]; isl.putalpha(Image.composite(a, Image.new('L', (W, H), 0), clip))
img = Image.alpha_composite(img, isl)

# ground fog + floating crystals at bottom
fog = layer(); fd = ImageDraw.Draw(fog)
for _ in range(60):
    fx, fy, fr = rnd.randrange(W), rnd.randrange(int(H * .78), H), rnd.randrange(60, 200)
    fd.ellipse([fx - fr, fy - fr * .3, fx + fr, fy + fr * .3], fill=(150, 110, 210, 22))
img = Image.alpha_composite(img, fog.filter(ImageFilter.GaussianBlur(26)))
cr = layer(); cd = ImageDraw.Draw(cr)
for px, py, s in [(W * .08, H * .84, 46), (W * .86, H * .88, 36), (W * .93, H * .58, 24), (W * .05, H * .30, 22)]:
    cd.polygon([(px, py - s), (px + s * .45, py - s * .1), (px + s * .3, py + s * .6), (px - s * .3, py + s * .6), (px - s * .45, py - s * .1)], fill=(120, 150, 255, 210))
    cd.line([(px, py - s), (px, py + s * .6)], fill=(210, 225, 255, 220), width=2)
img = Image.alpha_composite(img, cr.filter(ImageFilter.GaussianBlur(14)))
img = Image.alpha_composite(img, cr)
img.convert('RGB').save(sys.argv[1], optimize=True)
print('wrote', sys.argv[1], img.size)
