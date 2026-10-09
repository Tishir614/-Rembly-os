#!/usr/bin/env python3
"""Extract the Android bits Rembly needs for MediaTek Wi-Fi / Bluetooth / modem from YOUR firmware dump (on a PC).

    python3 tools/extract_android_blobs.py system.bin vendor.bin [-o out/android-blobs.tar.gz] [--list]

Needs `debugfs` (e2fsprogs); nothing is mounted or modified. Sparse images need `simg2img`.
(The tablet can also do this by itself from its own Android partitions: `rembly-drivers install`.)
The logic lives in rootfs/overlay/usr/local/lib/rembly/rembly_blobs.py (shared with the on-device tool)."""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'rootfs', 'overlay', 'usr', 'local', 'lib', 'rembly'))
import rembly_blobs

ap = argparse.ArgumentParser(); ap.add_argument('images', nargs='+'); ap.add_argument('-o', default='out/android-blobs.tar.gz')
ap.add_argument('--list', action='store_true', help='only print what was found (writes no tarball)')
ap.add_argument('--max-mb', type=int, default=40, help='skip data files bigger than this (modem images exempt)')
a = ap.parse_args()
imgs = [('vendor' if 'vendor' in os.path.basename(p).lower() else 'system', p) for p in a.images]
try:
    s = rembly_blobs.run(imgs, out=a.o, list_only=a.list, max_mb=a.max_mb)
except RuntimeError as e:
    sys.exit(str(e))
if a.list: print('\n--list: nothing written. Found %d connectivity binaries.' % len(s['binaries']))
else: print('wrote %s (%d files, %.1f MB unpacked)' % (a.o, s['files'], s['bytes'] / 1e6))
