#!/usr/bin/env python3
"""Boot animation frames for Rembly OS (black and white, atmosphere without a GPU):
  INTRO  (stage 1, plays once, ~1.5 s): a thin ring draws itself, the fox is revealed top to bottom, its eyes ignite with a bloom, the letters of
         REMBLY OS appear one after another, dust fades in.
  LOOP   (stage 2, repeats until the desktop starts): eyes breathe, rings ripple out of the fox, a light band sweeps along the wordmark, dust floats.
Frames cover the 800x800 logo area (screen rows 150..949), full width, so the player is just `gunzip | dd` into the framebuffer (busybox only).
Outputs: initramfs/anim/{32,16}/NN.gz  and  rootfs/overlay/usr/share/rembly/boot/loop/{32,16}/NN.gz   (32 = BGRA, 16 = RGB565)
usage: tools/gen_bootanim.py [--sheet OUT.png]"""
import gzip, math, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = Hh = 800
ROW0 = 150
N_INTRO, N_LOOP = 10, 12

mark_img = Image.open(os.path.join(ROOT, 'assets/logo-mark.png')); wm_img = Image.open(os.path.join(ROOT, 'assets/wordmark.png'))
mw = int(W * 0.50); mark = mark_img.resize((mw, int(mark_img.height * mw / mark_img.width)), Image.LANCZOS)
ww = int(W * 0.74); wm = wm_img.resize((ww, int(wm_img.height * ww / wm_img.width)), Image.LANCZOS)
total = mark.height + int(W * 0.07) + wm.height; top = (Hh - total) // 2
MX, MY = (W - mw) // 2, top; WX, WY = (W - ww) // 2, top + mark.height + int(W * 0.07)
CX, CY = W // 2, MY + mark.height // 2


def canvas(img, x, y):
    """alpha channel of img placed on the 800x800 canvas, float 0..1"""
    a = np.zeros((Hh, W), np.float32); arr = np.asarray(img).astype(np.float32) / 255
    a[y:y + arr.shape[0], x:x + arr.shape[1]] = arr[:Hh - y, :W - x]; return a


M = canvas(mark.getchannel('A'), MX, MY); WM = canvas(wm.getchannel('A'), WX, WY)

# eyes of the fox: the two small separate shapes in the middle of the mark (connected components of the original)
al = np.asarray(mark_img.getchannel('A')) > 128
lab = np.zeros(al.shape, int); n = 0; eye_ids = []
for y in range(al.shape[0]):
    for x in range(al.shape[1]):
        if al[y, x] and not lab[y, x]:
            n += 1; st = [(y, x)]; lab[y, x] = n; cnt = 0
            while st:
                cy, cx = st.pop(); cnt += 1
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < al.shape[0] and 0 <= nx < al.shape[1] and al[ny, nx] and not lab[ny, nx]: lab[ny, nx] = n; st.append((ny, nx))
            if 800 < cnt < 3000: eye_ids.append(n)
eyes_img = Image.fromarray((np.isin(lab, eye_ids) * 255).astype(np.uint8)).resize(mark.size, Image.LANCZOS)
EYES = canvas(eyes_img, MX, MY)

# letters of the wordmark: column runs of the original wordmark, scaled
walpha = np.asarray(wm_img.getchannel('A')) > 128; cols = walpha.any(0); runs = []; s0 = None
for i, v in enumerate(cols):
    if v and s0 is None: s0 = i
    if not v and s0 is not None: runs.append((s0, i)); s0 = None
if s0 is not None: runs.append((s0, len(cols)))
sk = ww / wm_img.width
LETTERS = [(int(a * sk) + WX, int(b * sk) + WX + 1) for a, b in runs]
print('eyes found: %d shapes, letters: %d' % (len(eye_ids), len(LETTERS)))

yy, xx = np.mgrid[0:Hh, 0:W].astype(np.float32)


def blur(a, r):
    return np.asarray(Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r))).astype(np.float32) / 255


def ease(x):
    x = min(1.0, max(0.0, x)); return x * x * (3 - 2 * x)


GLOW_M = blur(M, 16); GLOW_EYE = blur(EYES, 12) * 2.2
rng = np.random.default_rng(4)
DUST = [(rng.uniform(40, W - 40), rng.uniform(30, Hh - 30), rng.uniform(0, 6.283), rng.uniform(0.6, 1.8)) for _ in range(30)]


def ring(radius, alpha, width=2.2, frac=1.0):
    s = 3; im = Image.new('L', (W * s, Hh * s), 0); d = ImageDraw.Draw(im)
    box = [(CX - radius) * s, (CY - radius) * s, (CX + radius) * s, (CY + radius) * s]
    if frac >= 0.999: d.ellipse(box, outline=255, width=int(width * s))
    elif frac > 0: d.arc(box, -90, -90 + 360 * frac, fill=255, width=int(width * s))
    return np.asarray(im.resize((W, Hh), Image.LANCZOS)).astype(np.float32) / 255 * alpha


def dust(phase, vis, mode):
    layer = np.zeros((Hh, W), np.float32)
    for x0, y0, ph, sp in DUST:
        a = 0.10 + 0.32 * (0.5 + 0.5 * math.sin(phase * 6.283 * sp + ph)) if mode == 'loop' else 0.30
        x = x0 + 9 * math.sin(phase * 6.283 + ph); y = y0 + 7 * math.cos(phase * 6.283 + ph)
        r = 1.6; layer[int(max(0, y - r)):int(min(Hh, y + r + 1)), int(max(0, x - r)):int(min(W, x + r + 1))] += a * vis
    return np.clip(layer, 0, 1)


BASE_WM = 0.84     # wordmark brightness at rest (the travelling light band lifts it to 1.0)
EYE_BASE = 0.25    # eye bloom at rest


def frame_loop(i):
    ph = i / N_LOOP
    f = 0.05 * np.exp(-(((xx - CX) / 300) ** 2 + ((yy - CY) / 300) ** 2))
    f = f + ring(318, 0.30, 2.2)
    for off in (0.0, 0.5):                                                                             # two ripples, half a period apart
        p = (ph + off) % 1.0
        f = f + ring(250 + 170 * p, 0.34 * (1 - p) ** 1.6, 1.8)
    f = f + M + GLOW_M * 0.35
    breath = EYE_BASE + 0.20 * (0.5 - 0.5 * math.cos(ph * 6.283))
    f = f + GLOW_EYE * breath
    xs = -140 + 1080 * ph                                                                              # light band travelling along the wordmark
    band = np.exp(-(((xx - xs) / 70.0) ** 2))
    f = f + WM * (BASE_WM + (1 - BASE_WM) * band) + blur(WM, 6) * band * 0.45
    f = f + dust(ph, 1.0, 'loop')
    return f


def frame_intro(i):
    t = i / (N_INTRO - 1)
    if i == N_INTRO - 1: return frame_loop(0)                                                          # ends exactly on the loop's first picture
    f = 0.05 * np.exp(-(((xx - CX) / 300) ** 2 + ((yy - CY) / 300) ** 2)) * ease(t / 0.6)              # soft light behind the fox
    f = f + ring(318, 0.30 * ease(t / 0.3), 2.2, frac=ease(t / 0.75))                                  # the ring draws itself
    ry = MY - 50 + (mark.height + 100) * ease((t - 0.05) / 0.60)                                       # wipe top -> bottom with a soft edge
    wipe = np.clip((ry - yy) / 50.0, 0, 1)
    eyes_on = ease((t - 0.52) / 0.28)
    body = M * wipe * (1 - EYES * (0.85 * (1 - eyes_on)))                                              # eyes stay dim until they ignite
    f = f + body + GLOW_M * wipe * 0.35 * ease(t / 0.7)
    f = f + GLOW_EYE * (EYE_BASE + 0.65 * math.sin(math.pi * min(1, max(0, (t - 0.52) / 0.48)))) * eyes_on   # bloom flares and settles
    for k, (a, b) in enumerate(LETTERS):                                                               # letters one by one
        e = ease((t - (0.42 + k * 0.055)) / 0.14)
        if e <= 0: continue
        shift = int(round((1 - e) * 12)); sl = slice(max(0, a - 2), min(W, b + 3))
        seg = WM[:, sl]
        if shift: seg = np.roll(seg, shift, axis=0)
        col = np.zeros((Hh, W), np.float32); col[:, sl] = seg; f = f + col * BASE_WM * e
    f = f + dust(0.0, ease((t - 0.3) / 0.6), 'intro')
    return f


def encode(f, bpp):
    g = (np.clip(f, 0, 1) * 255 + 0.5).astype(np.uint8)
    if bpp == 32: return np.dstack([g, g, g, np.full_like(g, 255)]).tobytes()
    r5 = (g >> 3).astype(np.uint16); g6 = (g >> 2).astype(np.uint16)
    return ((r5 << 11) | (g6 << 5) | r5).astype('<u2').tobytes()


def write(frames, outdir):
    total = 0
    for bpp in (32, 16):
        d = os.path.join(outdir, str(bpp)); os.makedirs(d, exist_ok=True)
        for old in os.listdir(d):
            if old.endswith('.gz'): os.remove(os.path.join(d, old))
        for i, f in enumerate(frames):
            p = os.path.join(d, '%02d.gz' % i)
            with gzip.GzipFile(p, 'wb', 9, mtime=0) as fh: fh.write(encode(f, bpp))
            total += os.path.getsize(p)
    return total


intro = [frame_intro(i) for i in range(N_INTRO)]; loop = [frame_loop(i) for i in range(N_LOOP)]
t1 = write(intro, os.path.join(ROOT, 'initramfs', 'anim'))
t2 = write(loop, os.path.join(ROOT, 'rootfs', 'overlay', 'usr', 'share', 'rembly', 'boot', 'loop'))
print('intro: %d frames x2 formats, %d KiB (boot image) | loop: %d frames x2, %d KiB (rootfs) | rows %d..%d' % (N_INTRO, t1 // 1024, N_LOOP, t2 // 1024, ROW0, ROW0 + Hh - 1))
if '--sheet' in sys.argv:
    out = sys.argv[sys.argv.index('--sheet') + 1]; allf = intro + loop[::3]; cols = 7; tw = 200
    sheet = Image.new('L', (cols * tw, ((len(allf) + cols - 1) // cols) * tw))
    for k, f in enumerate(allf): sheet.paste(Image.fromarray((np.clip(f, 0, 1) * 255).astype(np.uint8)).resize((tw, tw)), ((k % cols) * tw, (k // cols) * tw))
    sheet.save(out)
