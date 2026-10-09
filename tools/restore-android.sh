#!/usr/bin/env bash
# restore-android.sh - put the ORIGINAL Android boot/recovery images back (undo flash-rembly.sh install modes).
#   tools/restore-android.sh --backup-dir DIR [--format-userdata] [--serial SN] [--dry-run] [--yes]
# DIR must contain your original boot.bin and recovery.bin. Only the partitions boot and recovery are written.
# --format-userdata also erases userdata (needed after Linux lived there: Android then formats it itself on first start).
set -euo pipefail
BACKUP=""; SERIAL=""; DRY=0; YES=0; FMT=0
EXPECT_PRODUCT=K37MV1_BSP; ORIG_BOOT_SHA=a94d3f8a18d626d0e12c3c1fe0848076a5c7754f2f108f727a9a21249a3483f4
while [ $# -gt 0 ]; do case "$1" in
  --backup-dir) BACKUP=$2; shift ;; --serial) SERIAL=$2; shift ;; --dry-run) DRY=1 ;; --yes) YES=1 ;; --format-userdata) FMT=1 ;;
  -h|--help) sed -n '2,6p' "$0"; exit 0 ;; *) echo "unknown argument: $1" >&2; exit 2 ;; esac; shift; done
die() { echo "ERROR: $*" >&2; exit 1; }
FB=(fastboot); [ -n "$SERIAL" ] && FB+=(-s "$SERIAL")
run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else echo "+ $*"; "$@"; fi; }
fbget() { "${FB[@]}" getvar "$1" 2>&1 | awk -F': +' -v k="$1" '$1==k {print $2; exit}'; }
command -v fastboot >/dev/null || die "fastboot not found"
[ -n "$BACKUP" ] && [ -f "$BACKUP/boot.bin" ] && [ -f "$BACKUP/recovery.bin" ] || die "need --backup-dir with boot.bin and recovery.bin"
[ "$(sha256sum "$BACKUP/boot.bin" | cut -d' ' -f1)" = "$ORIG_BOOT_SHA" ] || die "boot.bin in $BACKUP is not this tablet's original (sha256 differs)"
if [ "$DRY" = 0 ]; then
  [ -n "$("${FB[@]}" devices 2>/dev/null)" ] || die "no fastboot device"
  [ "$(fbget product)" = "$EXPECT_PRODUCT" ] || die "wrong device (product != $EXPECT_PRODUCT)"
  [ "$(fbget unlocked)" = yes ] || die "bootloader locked"
fi
echo "Will write: boot <- $BACKUP/boot.bin, recovery <- $BACKUP/recovery.bin$([ $FMT = 1 ] && echo ', and ERASE userdata')"
if [ "$YES" = 0 ] && [ "$DRY" = 0 ]; then printf 'Type RESTORE to continue: '; read -r a; [ "$a" = RESTORE ] || die "aborted"; fi
run "${FB[@]}" flash boot "$BACKUP/boot.bin"
run "${FB[@]}" flash recovery "$BACKUP/recovery.bin"
[ "$FMT" = 1 ] && run "${FB[@]}" erase userdata
run "${FB[@]}" reboot
echo "Original Android images restored."
