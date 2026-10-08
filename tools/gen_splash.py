#!/usr/bin/env python3
"""Boot splash for stage 1 (portrait 800x1280, the panel's native orientation). Writes raw framebuffer images,
gzip-compressed: initramfs/splash.32.gz (BGRA, 32 bpp) and initramfs/splash.16.gz (RGB565)."""
import glob, gzip, math, os, random, struct, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 800, 1280
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'initramfs')
LOGO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'logo-original.png')
def font(sz, bold=True):
    for p in glob.glob('/usr/share/fonts/**/NotoSans-%s.*tf' % ('Bold' if bold else 'Regular'), recursive=True) + glob.glob('/usr/share/fonts/**/DejaVuSans%s.ttf' % ('-Bold' if bold else ''), recursive=True):
        return ImageFont.truetype(p, sz)
    return ImageFont.load_default()
logo = Image.open(LOGO).convert('RGB')
bg = logo.getpixel((6, 6))                               # the logo's own near-black background colour
img = Image.new('RGB', (W, H), bg)
side = 780
lg = logo.resize((side, side), Image.LANCZOS)
mask = Image.new('L', (side, side), 0); ImageDraw.Draw(mask).rectangle([70, 70, side - 70, side - 70], fill=255)
mask = mask.filter(ImageFilter.GaussianBlur(45))             # feather the edges so the logo melts into the background
img.paste(lg, ((W - side) // 2, 190), mask)
dr = ImageDraw.Draw(img)
def centered(text, yy, f, fill):
    w = dr.textlength(text, font=f); dr.text(((W - w) / 2, yy), text, font=f, fill=fill)
centered('планшет A73 · запуск системы…', 1030, font(28, False), (190, 182, 225))
for i in range(5):                                       # progress dots
    r = 7 if i != 2 else 10; x = W / 2 + (i - 2) * 38; dr.ellipse([x - r, 1110 - r, x + r, 1110 + r], fill=(200, 180, 255) if i == 2 else (120, 100, 190))
img = img.convert('RGBA')
rgb = np.asarray(img.convert('RGB'))
bgra = np.dstack([rgb[..., 2], rgb[..., 1], rgb[..., 0], np.full((H, W), 255, np.uint8)]).tobytes()
r5, g6, b5 = (rgb[..., 0] >> 3).astype(np.uint16), (rgb[..., 1] >> 2).astype(np.uint16), (rgb[..., 2] >> 3).astype(np.uint16)
rgb565 = ((r5 << 11) | (g6 << 5) | b5).astype('<u2').tobytes()
for name, data in (('splash.32.gz', bgra), ('splash.16.gz', rgb565)):
    with gzip.GzipFile(os.path.join(OUT, name), 'wb', 9, mtime=0) as f: f.write(data)
    print(name, os.path.getsize(os.path.join(OUT, name)), 'bytes (raw %d)' % len(data))
img.convert('RGB').save('/tmp/splash_preview.png') if os.path.isdir('/tmp') else None
