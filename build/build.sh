#!/usr/bin/env bash
# Build A73-linux-test.img from the STOCK boot.bin. Does NOT flash anything.
# Usage: build/build.sh /path/boot.bin [/path/recovery.bin]
# Needs: python3, cpio, gzip, curl, tar, mkbootimg + unpack_bootimg (AOSP python tools)
set -euo pipefail
BOOT=${1:?usage: build.sh boot.bin [recovery.bin]}
RECOVERY=${2:-}
EXPECT_SHA=a94d3f8a18d626d0e12c3c1fe0848076a5c7754f2f108f727a9a21249a3483f4
HERE=$(cd "$(dirname "$0")/.." && pwd)
OUT=$HERE/out; WORK=$OUT/work
ALPINE=${ALPINE_BRANCH:-v3.20}; MIRROR=${ALPINE_MIRROR:-https://dl-cdn.alpinelinux.org/alpine}
MAXSIZE=$((16*1024*1024))

got=$(sha256sum "$BOOT" | cut -d' ' -f1)
[ "$got" = "$EXPECT_SHA" ] || { echo "boot.bin sha256 mismatch ($got) - refusing, wrong device image?" >&2; exit 1; }
rm -rf "$WORK"; mkdir -p "$WORK"/{boot,rec,fetch,ramfs}

echo "== unpack stock boot"
unpack_bootimg --boot_img "$BOOT" --out "$WORK/boot" > "$WORK/boot/args.txt"
KERNEL=$WORK/boot/kernel
[ -s "$KERNEL" ] || { echo "no kernel extracted" >&2; exit 1; }
# the DTB must still be appended inside the kernel; we never touch the kernel bytes
python3 - "$KERNEL" <<'PY'
import sys; d=open(sys.argv[1],'rb').read()
i=d.find(b'\xd0\x0d\xfe\xed'); print("appended DTB at", i, "(expected 6716608)")
sys.exit(0 if i>0 else "no DTB magic in kernel")
PY

echo "== fetch busybox-static (armv7) from Alpine $ALPINE"
IDX=$MIRROR/$ALPINE/main/armv7
curl -fsSL "$IDX/APKINDEX.tar.gz" | tar -xz -C "$WORK/fetch" APKINDEX
VER=$(awk '/^P:busybox-static$/{f=1} f&&/^V:/{print substr($0,3); exit}' "$WORK/fetch/APKINDEX")
[ -n "$VER" ] || { echo "busybox-static not in index" >&2; exit 1; }
curl -fsSL "$IDX/busybox-static-$VER.apk" | tar -xz -C "$WORK/fetch" 2>/dev/null || true
BB=$WORK/fetch/bin/busybox.static
[ -x "$BB" ] || { echo "busybox.static missing" >&2; exit 1; }

echo "== assemble initramfs"
R=$WORK/ramfs
mkdir -p "$R"/{bin,sbin,etc,proc,sys,dev,mnt,newroot,tmp,run,lib}
cp "$BB" "$R/bin/busybox"
cp "$HERE/initramfs/init" "$R/init"; chmod +x "$R/init"
cp "$HERE/initramfs/etc/mdev.conf" "$R/etc/"
if [ -n "$RECOVERY" ]; then
  echo "== adbd from recovery"
  unpack_bootimg --boot_img "$RECOVERY" --out "$WORK/rec" >/dev/null
  mkdir -p "$WORK/rec/rd"
  (cd "$WORK/rec/rd" && gzip -dc ../ramdisk | cpio -idm --quiet) || true
  if [ -f "$WORK/rec/rd/sbin/adbd" ]; then
    cp "$WORK/rec/rd/sbin/adbd" "$R/sbin/adbd"
    echo "adbd copied; check deps with: readelf -d $R/sbin/adbd | grep NEEDED"
    [ -d "$WORK/rec/rd/system/lib" ] && cp -a "$WORK/rec/rd/system/lib/." "$R/lib/" 2>/dev/null || true
  else echo "WARN: no sbin/adbd in recovery ramdisk"; fi
fi
(cd "$R" && find . | cpio -o -H newc --quiet | gzip -9 > "$OUT/rembley-initramfs.cpio.gz")

echo "== mkbootimg"
mkbootimg --header_version 0 --os_version 8.1.0 --os_patch_level 2018-01 \
  --kernel "$KERNEL" --ramdisk "$OUT/rembley-initramfs.cpio.gz" \
  --pagesize 0x800 --base 0x0 --kernel_offset 0x40008000 --ramdisk_offset 0x44000000 \
  --second_offset 0x40f00000 --tags_offset 0x4e000000 \
  --cmdline 'bootopt=64S3,32N2,32N2 buildvariant=user' \
  --output "$OUT/A73-linux-test.img"

SZ=$(stat -c %s "$OUT/A73-linux-test.img")
[ "$SZ" -lt "$MAXSIZE" ] || { echo "image $SZ >= 16MiB" >&2; exit 1; }
( cd "$OUT" && sha256sum A73-linux-test.img | tee A73-linux-test.img.sha256 )
(cd "$R" && find . | sort) > "$OUT/initramfs-files.txt"
echo "size: $SZ bytes. Verify: file $OUT/A73-linux-test.img; unpack_bootimg --boot_img $OUT/A73-linux-test.img --out out/test_unpack"
echo "Run (temporary, flashes nothing): fastboot boot $OUT/A73-linux-test.img"
