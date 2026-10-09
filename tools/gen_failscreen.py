#!/usr/bin/env python3
"""Stage-1 'system not found' screen (800x1280 raw, both pixel formats): tells the user what happened and what to do, instead of freezing on the logo.
Output: initramfs/noroot.32.gz, initramfs/noroot.16.gz"""
import glob, gzip, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 800, 1280


def font(sz, bold=False, mono=False):
    pats = ['DejaVuSansMono%s.ttf' % ('-Bold' if bold else '')] if mono else ['NotoSans-%s.ttf' % ('Bold' if bold else 'Regular'), 'DejaVuSans%s.ttf' % ('-Bold' if bold else '')]
    for pat in pats:
        for p in glob.glob('/usr/share/fonts/**/' + pat, recursive=True): return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


img = Image.new('RGB', (W, H), (0, 0, 0)); d = ImageDraw.Draw(img)
mark = Image.open(os.path.join(ROOT, 'assets/logo-mark.png')); mw = 230; mark = mark.resize((mw, int(mark.height * mw / mark.width)), Image.LANCZOS)
img.paste(Image.new('RGB', mark.size, (255, 255, 255)), ((W - mw) // 2, 70), mark.getchannel('A'))
wm = Image.open(os.path.join(ROOT, 'assets/wordmark.png')); ww = 330; wm = wm.resize((ww, int(wm.height * ww / wm.width)), Image.LANCZOS)
img.paste(Image.new('RGB', wm.size, (255, 255, 255)), ((W - ww) // 2, 70 + mark.height + 24), wm.getchannel('A'))
y = 70 + mark.height + 24 + wm.height + 60
d.rectangle([60, y, W - 60, y + 3], fill=(235, 235, 235)); y += 30
d.text((60, y), 'Система не найдена', font=font(44, True), fill=(255, 255, 255)); y += 80
for t in ('Загрузчик и ядро работают, но раздел с системой',
          '(метка REMBLY) не найден ни в памяти планшета,',
          'ни на SD-карте или USB-флешке.'):
    d.text((60, y), t, font=font(27), fill=(215, 215, 215)); y += 40
y += 20
d.text((60, y), 'Что сделать', font=font(31, True), fill=(255, 255, 255)); y += 52
for t in ('1. Подключите планшет к компьютеру по USB.',
          '2. На компьютере:   adb shell',
          '3. В нём:   cat /tmp/rootscan.txt',
          '    (что найдено)       hw   (отчёт)',
          '4. Прошейте rootfs заново (на компьютере):',
          '    tools/flash-rembly.sh install-recovery',
          '    (или install-boot) --backup-dir <копия>'):
    d.text((60, y), t, font=font(25, mono=True) if t.strip().startswith(('adb', 'cat', 'hw', 'tools', '(или')) or t.startswith(('    ', '2.', '3.')) else font(26), fill=(225, 225, 225)); y += 40
y += 24
d.rectangle([60, y, W - 60, y + 3], fill=(120, 120, 120)); y += 24
d.text((60, y), 'Rembly OS · stage 1 · no partition labelled REMBLY found', font=font(20, mono=True), fill=(150, 150, 150))
rgb = np.asarray(img)
bgra = np.dstack([rgb[..., 2], rgb[..., 1], rgb[..., 0], np.full((H, W), 255, np.uint8)]).tobytes()
r5, g6, b5 = (rgb[..., 0] >> 3).astype(np.uint16), (rgb[..., 1] >> 2).astype(np.uint16), (rgb[..., 2] >> 3).astype(np.uint16)
rgb565 = ((r5 << 11) | (g6 << 5) | b5).astype('<u2').tobytes()
for name, data in (('noroot.32.gz', bgra), ('noroot.16.gz', rgb565)):
    with gzip.GzipFile(os.path.join(ROOT, 'initramfs', name), 'wb', 9, mtime=0) as f: f.write(data)
    print(name, os.path.getsize(os.path.join(ROOT, 'initramfs', name)), 'bytes')
img.save('/tmp/claude-0/noroot-preview.png')
