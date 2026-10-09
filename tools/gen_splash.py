#!/usr/bin/env python3
"""Boot splash for stage 1 (portrait 800x1280, the panel's native orientation). Writes raw framebuffer images,
gzip-compressed: initramfs/splash.32.gz (BGRA, 32 bpp) and initramfs/splash.16.gz (RGB565)."""
import glob, gzip, math, os, random, struct, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 800, 1280
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'initramfs')
LOGO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'rootfs', 'overlay', 'usr', 'share', 'rembly', 'logo.png')   # fox + REMBLY OS wordmark (tools/gen_brand.py)
def font(sz, bold=True):
    for p in glob.glob('/usr/share/fonts/**/NotoSans-%s.*tf' % ('Bold' if bold else 'Regular'), recursive=True) + glob.glob('/usr/share/fonts/**/DejaVuSans%s.ttf' % ('-Bold' if bold else ''), recursive=True):
        return ImageFont.truetype(p, sz)
    return ImageFont.load_default()
logo = Image.open(LOGO).convert('RGB')
bg = (0, 0, 0)                                           # pure black, like the logo
img = Image.new('RGB', (W, H), bg)
side = 800
lg = logo.resize((side, side), Image.LANCZOS)
mask = Image.new('L', (side, side), 255)
# the logo itself is drawn by the boot animation (tools/gen_bootanim.py); this base picture only carries the caption and the progress track
dr = ImageDraw.Draw(img)
def centered(text, yy, f, fill):
    w = dr.textlength(text, font=f); dr.text(((W - w) / 2, yy), text, font=f, fill=fill)
centered('запуск системы…', 1040, font(26, False), (150, 150, 150))
TX0, TX1, TY, TH = 140, 660, 1112, 14                    # progress track (stage 2 fills it step by step, see usr/sbin/init)
def track(d, filled):
    d.rounded_rectangle([TX0, TY, TX1, TY + TH], radius=2, fill=(38, 38, 38))
    if filled > 0:
        x = TX0 + int((TX1 - TX0) * filled)
        for i in range(TX0, x):                          # purple -> pink gradient
            t = (i - TX0) / (TX1 - TX0); c = (int(255 - 100 * t),) * 3
            d.line([i, TY + 2, i, TY + TH - 2], fill=c)
        d.rectangle([x - 2, TY, x, TY + TH], fill=(int(255 - 100 * filled),) * 3)
        pass
track(dr, 0)
img = img.convert('RGBA')
rgb = np.asarray(img.convert('RGB'))
bgra = np.dstack([rgb[..., 2], rgb[..., 1], rgb[..., 0], np.full((H, W), 255, np.uint8)]).tobytes()
r5, g6, b5 = (rgb[..., 0] >> 3).astype(np.uint16), (rgb[..., 1] >> 2).astype(np.uint16), (rgb[..., 2] >> 3).astype(np.uint16)
rgb565 = ((r5 << 11) | (g6 << 5) | b5).astype('<u2').tobytes()
for name, data in (('splash.32.gz', bgra), ('splash.16.gz', rgb565)):
    with gzip.GzipFile(os.path.join(OUT, name), 'wb', 9, mtime=0) as f: f.write(data)
    print(name, os.path.getsize(os.path.join(OUT, name)), 'bytes (raw %d)' % len(data))
img.convert('RGB').save('/tmp/splash_preview.png') if os.path.isdir('/tmp') else None

# ---- progress strips: rows TY-6 .. TY+TH+6 of the same picture, 9 steps (0..8) in both pixel formats ----
BOOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'rootfs', 'overlay', 'usr', 'share', 'rembly', 'boot')
os.makedirs(BOOT, exist_ok=True)
Y0, Y1 = TY - 6, TY + TH + 6
print('strip rows %d..%d (height %d)' % (Y0, Y1, Y1 - Y0))
for n in range(9):
    im = img.convert('RGB').copy(); track(ImageDraw.Draw(im), n / 8)
    crop = np.asarray(im.crop((0, Y0, W, Y1)))
    b32 = np.dstack([crop[..., 2], crop[..., 1], crop[..., 0], np.full(crop.shape[:2], 255, np.uint8)]).tobytes()
    r5, g6, b5 = (crop[..., 0] >> 3).astype(np.uint16), (crop[..., 1] >> 2).astype(np.uint16), (crop[..., 2] >> 3).astype(np.uint16)
    b16 = ((r5 << 11) | (g6 << 5) | b5).astype('<u2').tobytes()
    for bpp, data in ((32, b32), (16, b16)):
        with gzip.GzipFile(os.path.join(BOOT, 'bar-%d.%d.gz' % (n, bpp)), 'wb', 9, mtime=0) as f: f.write(data)
open(os.path.join(BOOT, 'row'), 'w').write('%d\n' % Y0)
