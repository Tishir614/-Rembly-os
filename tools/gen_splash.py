#!/usr/bin/env python3
"""Boot splash for stage 1 (portrait 800x1280, the panel's native orientation). Writes raw framebuffer images,
gzip-compressed: initramfs/splash.32.gz (BGRA, 32 bpp) and initramfs/splash.16.gz (RGB565)."""
import glob, gzip, math, os, random, struct, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 800, 1280
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'initramfs')
rnd = random.Random(7)
y = np.mgrid[0:H, 0:W][0].astype(np.float32) / H
top, mid, low = np.array([8, 6, 30]), np.array([44, 26, 94]), np.array([120, 66, 160])
col = np.where(y[..., None] < .62, top + (mid - top) * (y[..., None] / .62), mid + (low - mid) * ((y[..., None] - .62) / .38))
img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).convert('RGBA')
st = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(st)
for _ in range(260):
    x, yy, r = rnd.randrange(W), rnd.randrange(int(H * .8)), rnd.choice([.7, 1, 1, 1.5, 2])
    d.ellipse([x - r, yy - r, x + r, yy + r], fill=(235, 230, 255, rnd.randrange(90, 255)))
img = Image.alpha_composite(img, st)
cx, cy, R = W / 2, H * .40, 190                                        # portal ring + crescent
ring = Image.new('RGBA', (W, H), (0, 0, 0, 0)); rd = ImageDraw.Draw(ring)
rd.ellipse([cx - R, cy - R, cx + R, cy + R], outline=(205, 195, 255, 230), width=10)
rd.ellipse([cx - R - 26, cy - R - 26, cx + R + 26, cy + R + 26], outline=(180, 165, 255, 110), width=3)
img = Image.alpha_composite(img, ring.filter(ImageFilter.GaussianBlur(12))); img = Image.alpha_composite(img, ring)
mask = Image.new('L', (W, H), 0); md = ImageDraw.Draw(mask)
md.ellipse([cx - 90, cy - 90, cx + 90, cy + 90], fill=255); md.ellipse([cx - 52, cy - 104, cx + 128, cy + 76], fill=0)
moon = Image.new('RGBA', (W, H), (226, 218, 255, 255)); moon.putalpha(mask); img = Image.alpha_composite(img, moon)
def font(sz, bold=True):
    for p in glob.glob('/usr/share/fonts/**/NotoSans-%s.*tf' % ('Bold' if bold else 'Regular'), recursive=True) + glob.glob('/usr/share/fonts/**/DejaVuSans%s.ttf' % ('-Bold' if bold else ''), recursive=True):
        return ImageFont.truetype(p, sz)
    return ImageFont.load_default()
dr = ImageDraw.Draw(img)
def centered(text, yy, f, fill):
    w = dr.textlength(text, font=f); dr.text(((W - w) / 2, yy), text, font=f, fill=fill)
glow = Image.new('RGBA', (W, H), (0, 0, 0, 0)); gd = ImageDraw.Draw(glow)
w = gd.textlength('Rembley OS', font=font(84)); gd.text(((W - w) / 2, 700), 'Rembley OS', font=font(84), fill=(160, 130, 255, 255))
img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(14))); dr = ImageDraw.Draw(img)
centered('Rembley OS', 700, font(84), (246, 242, 255, 255))
centered('планшет A73 · запуск системы…', 820, font(30, False), (206, 198, 238, 255))
for i in range(5):                                                       # progress dots
    r = 7 if i != 2 else 10; x = W / 2 + (i - 2) * 38; dr.ellipse([x - r, 950 - r, x + r, 950 + r], fill=(200, 180, 255, 255 if i == 2 else 150))
rgb = np.asarray(img.convert('RGB'))
bgra = np.dstack([rgb[..., 2], rgb[..., 1], rgb[..., 0], np.full((H, W), 255, np.uint8)]).tobytes()
r5, g6, b5 = (rgb[..., 0] >> 3).astype(np.uint16), (rgb[..., 1] >> 2).astype(np.uint16), (rgb[..., 2] >> 3).astype(np.uint16)
rgb565 = ((r5 << 11) | (g6 << 5) | b5).astype('<u2').tobytes()
for name, data in (('splash.32.gz', bgra), ('splash.16.gz', rgb565)):
    with gzip.GzipFile(os.path.join(OUT, name), 'wb', 9, mtime=0) as f: f.write(data)
    print(name, os.path.getsize(os.path.join(OUT, name)), 'bytes (raw %d)' % len(data))
img.convert('RGB').save('/tmp/splash_preview.png') if os.path.isdir('/tmp') else None
