#!/usr/bin/env python3
"""Black-and-white wallpaper in the language of the fox logo: near-black ground, a huge ghost of the fox, thin concentric rings, a few razor lines.
usage: tools/gen_wallpaper.py [OUT.png] [W H]    (put your own picture at ~/.config/rembly/wallpaper.png to replace it)"""
import os, sys, math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'rootfs/overlay/usr/share/rembly/wallpaper.png')
W, H = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (1920, 1200)
rnd = random.Random(11)
y, x = np.mgrid[0:H, 0:W].astype(np.float32)
d = np.sqrt(((x - W * 0.62) / W) ** 2 + ((y - H * 0.5) / H) ** 2)
base = np.clip(30 - d * 46, 6, 30)                                     # soft grey glow behind the fox, black at the edges
img = Image.fromarray(np.dstack([base] * 3).astype(np.uint8)).convert('RGBA')
ring = Image.new('RGBA', (W, H), (255, 255, 255, 0)); dr = ImageDraw.Draw(ring)
cx, cy = int(W * 0.62), int(H * 0.5)
for r, a in ((260, 26), (420, 20), (620, 14), (860, 9)): dr.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, a), width=3)
for _ in range(9):                                                      # razor lines like the whiskers
    x0, y0 = rnd.randrange(0, W), rnd.randrange(0, H); L = rnd.randrange(260, 900); ang = rnd.choice((-0.18, -0.12, 0.12, 0.18, 0.55, -0.55))
    dr.line([(x0, y0), (x0 + L * math.cos(ang), y0 + L * math.sin(ang))], fill=(255, 255, 255, rnd.randrange(14, 34)), width=2)
img = Image.alpha_composite(img, ring)
mark = Image.open(os.path.join(ROOT, 'assets/logo-mark.png')); s = 0.92 * H / mark.height
m = mark.resize((int(mark.width * s), int(mark.height * s)), Image.LANCZOS)
a = m.getchannel('A').point(lambda v: int(v * 0.10)); m.putalpha(a)                # the ghost: 10% white
ghost = Image.new('RGBA', (W, H), (255, 255, 255, 0)); ghost.alpha_composite(m, (cx - m.width // 2, cy - m.height // 2)); img = Image.alpha_composite(img, ghost)
arr = np.asarray(img.convert('RGB')).astype(np.float32) + np.random.default_rng(5).normal(0, 1.6, (H, W, 3))
os.makedirs(os.path.dirname(OUT), exist_ok=True); Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(OUT, optimize=True); print('wrote', OUT, os.path.getsize(OUT) // 1024, 'KiB')
