#!/usr/bin/env bash
# One command on your PC: extract Wi-Fi/BT/modem files from your own system.bin + vendor.bin.
# usage: tools/make-blobs.sh /home/tishir645/планшет     (folder that contains system.bin and vendor.bin)
set -euo pipefail
D=${1:?usage: make-blobs.sh FOLDER_WITH_system.bin_AND_vendor.bin}
HERE=$(cd "$(dirname "$0")/.." && pwd)
[ -f "$D/system.bin" ] || { echo "no $D/system.bin" >&2; exit 1; }
IMGS=("$D/system.bin"); [ -f "$D/vendor.bin" ] && IMGS+=("$D/vendor.bin") || echo "WARNING: no vendor.bin - firmware is often there, include it if you can"
command -v debugfs >/dev/null || { echo "install: sudo apt install e2fsprogs android-sdk-libsparse-utils" >&2; exit 1; }
echo "== what was found (nothing written yet)"
python3 -I "$HERE/tools/extract_android_blobs.py" "${IMGS[@]}" --list | tee "$HERE/out/android-blobs-found.txt"
echo "== extracting"
python3 -I "$HERE/tools/extract_android_blobs.py" "${IMGS[@]}" -o "$HERE/out/android-blobs.tar.gz" | tee "$HERE/out/android-blobs-manifest.txt"
ls -lh "$HERE/out/android-blobs.tar.gz"
cat <<M

Next:
  1) put the small archive into the repo so it can be checked and built into the image:
       cd "$HERE" && git add -f out/android-blobs.tar.gz out/android-blobs-manifest.txt out/android-blobs-found.txt \\
         && git commit -m "Add android blobs from my firmware" && git push
     (if it is over 90 MB, send only out/android-blobs-manifest.txt first)
  2) rebuild the rootfs on the PC: sudo rootfs/build-rootfs.sh
M
