#!/usr/bin/env python3
"""Generates the 'Rembley' xfwm4 window-frame theme (colourful purple/pink frame instead of the plain grey one).
Frame geometry matches Default-xhdpi (title 58 px, borders 12 px), so every window of the desktop gets the same look.
usage: tools/gen_wmtheme.py [OUTDIR]   (default rootfs/overlay/usr/share/themes/Rembley/xfwm4)"""
import os, shutil, sys
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'rootfs/overlay/usr/share/themes/Rembley/xfwm4')
os.makedirs(OUT, exist_ok=True)
TH, BW, W, H, R = 58, 12, 400, 300, 16
S = 4                                                       # supersampling for smooth corners


def lerp(a, b, t): return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


PAL = {
    'active':   dict(t0=(150, 105, 245), t1=(78, 46, 168), b0=(66, 40, 150), b1=(44, 26, 104), line=(236, 160, 255), glow=(255, 122, 198)),
    'inactive': dict(t0=(58, 46, 100), t1=(40, 31, 74), b0=(36, 28, 68), b1=(28, 22, 54), line=(96, 84, 150), glow=(80, 70, 130)),
}


def frame(state):
    p = PAL[state]; w, h = W * S, H * S
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0)); px = img.load()
    for y in range(h):
        for x in range(w):
            X, Y = x / S, y / S; col = None
            if Y < TH:
                col = lerp(p['t0'], p['t1'], Y / TH)
                if Y < 2.5: col = lerp(p['line'], col, Y / 2.5 * 0.6)
                if X < 2 or X > W - 2: col = lerp(p['line'], col, 0.4)
            elif X < BW or X >= W - BW or Y >= H - BW:
                d = min(X, W - 1 - X, H - 1 - Y)                    # distance from the outer edge
                col = lerp(p['b0'], p['b1'], min(1, d / BW))
                if d < 2: col = lerp(p['line'], col, d / 2 * 0.7)
                if Y >= H - 3: col = lerp(p['glow'], col, (H - Y) / 3 * 0.55 + 0.1) if state == 'active' else col   # pink glow along the bottom edge
            if col: px[x, y] = col + (255,)
    mask = Image.new('L', (w, h), 0); d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=R * S, fill=255)
    img.putalpha(Image.composite(img.getchannel('A'), Image.new('L', (w, h), 0), mask))
    return img.resize((W, H), Image.LANCZOS)


def crop(img, box, name):
    img.crop(box).save(os.path.join(OUT, name + '.png'))


for st in ('active', 'inactive'):
    f = frame(st)
    for i in range(1, 6): crop(f, (120, 0, 136, TH), 'title-%d-%s' % (i, st))
    crop(f, (0, 0, 16, TH), 'top-left-' + st); crop(f, (W - 16, 0, W, TH), 'top-right-' + st)
    crop(f, (0, 120, BW, 168), 'left-' + st); crop(f, (W - BW, 120, W, 168), 'right-' + st)
    crop(f, (120, H - BW, 168, H), 'bottom-' + st)
    crop(f, (0, H - 32, 32, H), 'bottom-left-' + st); crop(f, (W - 32, H - 32, W, H), 'bottom-right-' + st)

# ---- buttons: coloured discs with a glyph ----
BW_, BH_ = 44, 58
COL = {'close': ((255, 120, 150), (255, 79, 154)), 'maximize': ((90, 224, 196), (60, 170, 220)), 'hide': ((255, 214, 100), (255, 160, 80)),
       'menu': ((190, 160, 255), (140, 110, 235)), 'shade': ((190, 160, 255), (140, 110, 235)), 'stick': ((255, 160, 220), (200, 120, 255))}


def glyph(d, kind, toggled, cx, cy, c, k=4):
    w3 = 3 * k; w2 = 2 * k
    if kind == 'close': d.line([cx - 5 * k, cy - 5 * k, cx + 5 * k, cy + 5 * k], fill=c, width=w3); d.line([cx - 5 * k, cy + 5 * k, cx + 5 * k, cy - 5 * k], fill=c, width=w3)
    elif kind == 'maximize':
        if toggled: d.rectangle([cx - 5 * k, cy - 2 * k, cx + 2 * k, cy + 5 * k], outline=c, width=w2); d.rectangle([cx - 2 * k, cy - 5 * k, cx + 5 * k, cy + 2 * k], outline=c, width=w2)
        else: d.rectangle([cx - 5 * k, cy - 5 * k, cx + 5 * k, cy + 5 * k], outline=c, width=w2)
    elif kind == 'hide': d.line([cx - 5 * k, cy + 4 * k, cx + 5 * k, cy + 4 * k], fill=c, width=w3)
    elif kind == 'shade': d.line([cx - 5 * k, cy - 4 * k, cx + 5 * k, cy - 4 * k], fill=c, width=w3); d.polygon([(cx - 5 * k, cy), (cx + 5 * k, cy), (cx, cy + 6 * k)], fill=c)
    elif kind == 'stick': d.ellipse([cx - 4 * k, cy - 4 * k, cx + 4 * k, cy + 4 * k], fill=c if toggled else None, outline=c, width=w2)
    elif kind == 'menu': d.polygon([(cx - 5 * k, cy - 3 * k), (cx + 5 * k, cy - 3 * k), (cx, cy + 5 * k)], fill=c)


def button(kind, state, toggled=False):
    s = 4; im = Image.new('RGBA', (BW_ * s, BH_ * s), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    cx, cy, r = BW_ * s // 2, BH_ * s // 2 + 1 * s, 15 * s
    c0, c1 = COL[kind]
    if state in ('inactive',): c0, c1 = (92, 80, 140), (70, 60, 112)
    if state == 'prelight': c0, c1 = lerp(c0, (255, 255, 255), .30), lerp(c1, (255, 255, 255), .25)
    if state == 'pressed': c0, c1 = lerp(c0, (0, 0, 0), .30), lerp(c1, (0, 0, 0), .30)
    if state in ('active', 'prelight'):                                        # soft glow
        gl = Image.new('RGBA', im.size, (0, 0, 0, 0)); ImageDraw.Draw(gl).ellipse([cx - r - 4 * s, cy - r - 4 * s, cx + r + 4 * s, cy + r + 4 * s], fill=c1 + (90 if state == 'active' else 150,))
        im = Image.alpha_composite(im, gl.filter(ImageFilter.GaussianBlur(4 * s))); d = ImageDraw.Draw(im)
    disc = Image.new('RGBA', im.size, (0, 0, 0, 0)); dd = ImageDraw.Draw(disc)
    for i in range(2 * r):                                                   # vertical gradient disc
        y = cy - r + i; t = i / (2 * r); dd.line([cx - r, y, cx + r, y], fill=lerp(c0, c1, t) + (255,))
    m = Image.new('L', im.size, 0); ImageDraw.Draw(m).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    disc.putalpha(m); im = Image.alpha_composite(im, disc); d = ImageDraw.Draw(im)
    glyph(d, kind, toggled, cx, cy, (255, 255, 255, 255) if state != 'inactive' else (200, 190, 230, 255))
    return im.resize((BW_, BH_), Image.LANCZOS)


for kind in ('close', 'maximize', 'hide', 'menu', 'shade', 'stick'):
    for tg in ((False, True) if kind in ('maximize', 'shade', 'stick') else (False,)):
        for st in ('active', 'inactive', 'prelight', 'pressed'):
            button(kind, st, tg).save(os.path.join(OUT, '%s%s-%s.png' % (kind, '-toggled' if tg else '', st)))

open(os.path.join(OUT, 'themerc'), 'w').write('''active_text_color=#ffffff
active_text_shadow_color=#2a1a5e
inactive_text_color=#b8aee3
inactive_text_shadow_color=#1c1438
button_offset=6
button_spacing=2
frame_border_top=9
full_width_title=true
maximized_offset=0
show_app_icon=true
shadow_delta_height=8
shadow_delta_width=-4
shadow_delta_x=-4
shadow_delta_y=-8
shadow_opacity=30
title_horizontal_offset=8
title_shadow_active=frame
title_shadow_inactive=false
title_vertical_offset_active=2
title_vertical_offset_inactive=2
''')
print('wrote', len(os.listdir(OUT)), 'files to', OUT)
