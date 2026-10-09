#!/usr/bin/env bash
# verify-images.sh - offline pre-flight check of everything that will be flashed. Run by flash-rembly.sh automatically.
#   tools/verify-images.sh [DIR] [--stock-boot boot.bin] [--quick] [--boot-only]
# Exit code 0 = every check passed. It never talks to the tablet and never writes anything.
set -u
DIR=out; STOCK=""; QUICK=0; BONLY=0
while [ $# -gt 0 ]; do case $1 in --stock-boot) STOCK=$2; shift;; --quick) QUICK=1;; --boot-only) BONLY=1;; -*) echo "unknown $1"; exit 2;; *) DIR=$1;; esac; shift; done
BOOT=$DIR/A73-linux-test.img; RAW=$DIR/rembly-rootfs.img; SP=$DIR/rembly-rootfs.sparse.img
fail=0; ok() { echo "  OK    $*"; }; bad() { echo "  FAIL  $*"; fail=1; }; warn() { echo "  warn  $*"; }
le32() { od -An -tu4 -j"$2" -N4 "$1" | tr -d ' '; }

echo "== boot image ($BOOT)"
if [ ! -f "$BOOT" ]; then bad "missing"; else
  [ "$(head -c 8 "$BOOT")" = "ANDROID!" ] && ok "Android boot magic" || bad "no ANDROID! magic"
  sz=$(stat -c %s "$BOOT"); [ "$sz" -lt $((16*1024*1024)) ] && ok "size $((sz/1024)) KiB < 16 MiB" || bad "size $sz >= 16 MiB (LK/partition limit)"
  [ "$(le32 "$BOOT" 12)" = $((0x40008000)) ] && ok "kernel load address 0x40008000 (stock)" || bad "kernel address differs from stock"
  [ "$(le32 "$BOOT" 36)" = 2048 ] && ok "page size 2048 (stock)" || bad "page size differs from stock"
  ks=$(le32 "$BOOT" 8); rs=$(le32 "$BOOT" 16); [ "$ks" -gt 1000000 ] && ok "kernel $ks bytes, ramdisk $rs bytes" || bad "kernel looks too small"
  [ -n "$STOCK" ] && { if [ -f "$STOCK" ]; then
      a=$(dd if="$BOOT" bs=2048 skip=1 count=$(((ks+2047)/2048)) 2>/dev/null | head -c "$ks" | sha256sum | cut -d' ' -f1)
      b=$(dd if="$STOCK" bs=2048 skip=1 count=$(((ks+2047)/2048)) 2>/dev/null | head -c "$ks" | sha256sum | cut -d' ' -f1)
      [ "$(le32 "$STOCK" 8)" = "$ks" ] && [ "$a" = "$b" ] && ok "kernel + DTB are byte-identical to your stock boot.bin" || bad "kernel differs from stock boot.bin"
    else bad "stock boot $STOCK not found"; fi; }
  if [ -f "$DIR/initramfs-files.txt" ]; then
    for f in bin/rembly-bootanim anim/32/09.gz anim/16/09.gz splash.32.gz noroot.32.gz noroot.16.gz; do grep -q " $f\$" "$DIR/initramfs-files.txt" && ok "initramfs contains $f" || bad "initramfs lacks $f (boot animation)"; done
  fi
  [ -f "$BOOT.sha256" ] && { (cd "$DIR" && sha256sum -c "$(basename "$BOOT").sha256" >/dev/null 2>&1) && ok "sha256 matches" || bad "sha256 mismatch"; }
fi

echo "== rootfs ($RAW)"
if [ $BONLY = 1 ]; then warn "skipped (--boot-only)"; elif [ ! -f "$RAW" ]; then bad "missing"; else
  [ "$(od -An -tx1 -j1080 -N2 "$RAW" | tr -d ' ')" = 53ef ] && ok "ext4 magic" || bad "not ext4"
  [ "$(dd if="$RAW" bs=1 skip=1144 count=16 2>/dev/null | tr -d '\0')" = REMBLY ] && ok "label REMBLY (stage 1 finds it)" || bad "label is not REMBLY"
  if command -v e2fsck >/dev/null; then
    if [ $QUICK = 1 ]; then warn "e2fsck skipped (--quick)"; else e2fsck -fn "$RAW" >/dev/null 2>&1 && ok "e2fsck: filesystem is clean" || bad "e2fsck reports errors"; fi
  else warn "e2fsck not installed, filesystem not checked"; fi
  if command -v debugfs >/dev/null; then
    for f in /usr/sbin/init /usr/local/bin/rembly-shell /usr/local/bin/rembly-update /etc/rembly/update.conf /usr/local/bin/rembly-autosetup; do
      debugfs -R "stat $f" "$RAW" 2>&1 | grep -q 'Inode:' && ok "contains $f" || bad "missing inside image: $f"; done
  fi
  echo "  size: $(( $(stat -c %s "$RAW") / 1048576 )) MiB (the flash script compares this with the tablet's userdata)"
fi

echo "== sparse image ($SP)"
if [ $BONLY = 1 ]; then warn "skipped (--boot-only)"; elif [ -f "$SP" ]; then
  [ "$(le32 "$SP" 0)" = $((0xED26FF3A)) ] && ok "sparse magic" || bad "not an Android sparse image"
  if command -v simg2img >/dev/null && [ $QUICK = 0 ] && [ -f "$RAW" ]; then
    TMP=$(mktemp "${TMPDIR:-/tmp}/rembly-verify.XXXXXX"); need=$(stat -c %s "$RAW"); have=$(df --output=avail -B1 "$(dirname "$TMP")" | tail -1)
    if [ "$have" -gt "$need" ]; then
      simg2img "$SP" "$TMP" 2>/dev/null && cmp -s "$TMP" "$RAW" && ok "sparse image expands to exactly the raw image" || bad "sparse image differs from raw image"
    else warn "not enough temp space to compare sparse with raw (set TMPDIR)"; fi
    rm -f "$TMP"
  fi
else warn "no sparse image (flash will use the raw one: slower but valid)"; fi

echo; [ $fail = 0 ] && echo "ALL CHECKS PASSED" || echo "CHECKS FAILED - do not flash"
exit $fail
