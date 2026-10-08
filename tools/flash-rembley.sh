#!/usr/bin/env bash
# flash-rembley.sh - put Rembley OS on the A73 (MT6737M / K37MV1_BSP) with safety checks. Run on your PC with the tablet in fastboot.
#
#   tools/flash-rembley.sh [MODE] [options]
#
# MODES
#   test              (default) NOTHING is written: only `fastboot boot` of the Linux image. Power-off returns to Android.
#   install-recovery  Dual boot. Linux image -> RECOVERY partition, rootfs -> USERDATA. Android keeps booting from `boot`.
#   install-boot      Linux image -> BOOT partition, rootfs -> USERDATA. Android will NOT start until restore-android.sh.
#
# OPTIONS
#   --dir DIR         folder with A73-linux-test.img, rembley-rootfs.img and the *.sha256 files   (default: ./out)
#   --backup-dir DIR  folder with YOUR original dump (boot.bin, recovery.bin). REQUIRED for install modes: you must be able to go back.
#   --serial SN       fastboot serial (needed only if several devices are attached)
#   --dry-run         print every fastboot command instead of running it
#   --yes             skip the typed confirmation (for scripts)
#   --no-backup-check skip the backup-dir requirement (NOT recommended)
#
# SAFETY (hard-coded): the only partitions this script can ever write are  boot, recovery, userdata.
# It never touches preloader, lk, gpt, nvram, nvdata, protect1/2, secro, proinfo, seccfg, system, vendor, md*.
set -euo pipefail

MODE=test; DIR=out; BACKUP=""; SERIAL=""; DRY=0; YES=0; NOBK=0
EXPECT_PRODUCT=K37MV1_BSP
ORIG_BOOT_SHA=a94d3f8a18d626d0e12c3c1fe0848076a5c7754f2f108f727a9a21249a3483f4
ALLOWED_PARTS="boot recovery userdata"
MAX_BOOT=$((16 * 1024 * 1024))

while [ $# -gt 0 ]; do
  case "$1" in
    test|install-recovery|install-boot) MODE=$1 ;;
    --dir) DIR=$2; shift ;;
    --backup-dir) BACKUP=$2; shift ;;
    --serial) SERIAL=$2; shift ;;
    --dry-run) DRY=1 ;;
    --yes) YES=1 ;;
    --no-backup-check) NOBK=1 ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1 (see --help)" >&2; exit 2 ;;
  esac; shift
done

die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo "== $*"; }
FB=(fastboot); [ -n "$SERIAL" ] && FB+=(-s "$SERIAL")
run()  { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else echo "+ $*"; "$@"; fi; }
fbget(){ "${FB[@]}" getvar "$1" 2>&1 | awk -F': +' -v k="$1" '$1==k {print $2; exit}'; }
sha()  { sha256sum "$1" | cut -d' ' -f1; }
flash() {   # flash PARTITION FILE : refuses anything outside the allow-list
  case " $ALLOWED_PARTS " in *" $1 "*) ;; *) die "refusing to flash partition '$1' (allowed: $ALLOWED_PARTS)";; esac
  run "${FB[@]}" flash "$1" "$2"
}

command -v fastboot >/dev/null || die "fastboot not found (sudo apt install android-tools-fastboot)"
BOOTIMG=$DIR/A73-linux-test.img; ROOTFS=$DIR/rembley-rootfs.img
FLASHROOT=$ROOTFS; [ "$DIR/rembley-rootfs.sparse.img" -nt "$ROOTFS" ] && FLASHROOT=$DIR/rembley-rootfs.sparse.img   # sparse = much faster to flash
[ -f "$BOOTIMG" ] || die "$BOOTIMG not found (run: python3 build/build.py boot.bin recovery.bin)"

info "Checking the images"
[ "$(stat -c %s "$BOOTIMG")" -lt "$MAX_BOOT" ] || die "boot image is not smaller than 16 MiB"
file "$BOOTIMG" 2>/dev/null | grep -q 'Android bootimg' || die "$BOOTIMG is not an Android boot image"
[ -f "$BOOTIMG.sha256" ] && { (cd "$DIR" && sha256sum -c "$(basename "$BOOTIMG").sha256" >/dev/null) || die "boot image checksum mismatch"; echo "boot image checksum OK"; }
if [ "$MODE" != test ]; then
  [ -f "$ROOTFS" ] || die "$ROOTFS not found (run: sudo rootfs/build-rootfs.sh)"
  [ -f "$ROOTFS.sha256" ] && { (cd "$DIR" && sha256sum -c "$(basename "$ROOTFS").sha256" >/dev/null) || die "rootfs checksum mismatch"; echo "rootfs checksum OK"; }
  [ "$(od -An -tx1 -j1080 -N2 "$ROOTFS" | tr -d ' ')" = 53ef ] || die "$ROOTFS is not an ext4 image"
  [ "$(dd if="$ROOTFS" bs=1 skip=1144 count=16 2>/dev/null | tr -d '\0')" = REMBLEY ] || die "$ROOTFS has no REMBLEY label (stage 1 would not find it)"
  if command -v debugfs >/dev/null; then
    if debugfs -R "stat /system/bin/wmt_launcher" "$ROOTFS" 2>&1 | grep -q 'Inode:'; then echo "Wi-Fi drivers: included in this rootfs image"
    else echo "Wi-Fi drivers: not baked into this image -> on first boot the tablet takes them from its OWN Android partitions automatically (rembley-drivers)"; fi
  fi
fi

if [ "$MODE" != test ] && [ "$NOBK" = 0 ]; then
  info "Checking your backup (you must be able to go back to Android)"
  [ -n "$BACKUP" ] || die "install modes need --backup-dir <folder with your original boot.bin and recovery.bin>"
  [ -f "$BACKUP/boot.bin" ] && [ -f "$BACKUP/recovery.bin" ] || die "$BACKUP must contain boot.bin and recovery.bin"
  [ "$(sha "$BACKUP/boot.bin")" = "$ORIG_BOOT_SHA" ] || die "$BACKUP/boot.bin is not the original boot image of this tablet (sha256 differs)"
  echo "backup OK: original boot.bin and recovery.bin found"
fi

info "Checking the tablet (fastboot)"
if [ "$DRY" = 0 ]; then
  [ -n "$("${FB[@]}" devices 2>/dev/null)" ] || die "no fastboot device. Power off, hold Vol- + Power (or run: adb reboot bootloader)"
  prod=$(fbget product); [ "$prod" = "$EXPECT_PRODUCT" ] || die "product is '$prod', expected $EXPECT_PRODUCT - wrong device, refusing"
  unl=$(fbget unlocked);  [ "$unl" = yes ] || die "bootloader is locked (unlocked: '$unl'). Not touching anything."
  echo "device OK: product=$prod unlocked=$unl"
  if [ "$MODE" != test ]; then
    ps=$(fbget partition-size:userdata); [ -z "$ps" ] && echo "note: tablet does not report partition-size:userdata; fastboot will fail cleanly if the image is too big" || {
      need=$(stat -c %s "$ROOTFS"); have=$((ps)); [ "$need" -le "$have" ] || die "rootfs ($need bytes) is bigger than userdata ($have bytes)"; echo "userdata fits: $need <= $have bytes"; }
  fi
else echo "[dry-run] skipping the live device checks (product=$EXPECT_PRODUCT, unlocked=yes, userdata size)"; fi

# ---- the plan, shown before anything happens ----
echo; info "PLAN ($MODE)"
case "$MODE" in
  test) echo "  fastboot boot $BOOTIMG        (temporary, nothing is written to the tablet)" ;;
  install-recovery)
    echo "  1. fastboot flash recovery  $BOOTIMG   <- Linux lives in the recovery slot"
    echo "  2. fastboot flash userdata  $FLASHROOT    <- ERASES whatever is in userdata (Android data; you already wiped it)"
    echo "  Android keeps booting from 'boot'. Boot Linux through the recovery entry (usually Vol+ & Power, or the LK boot menu)." ;;
  install-boot)
    echo "  1. fastboot flash boot      $BOOTIMG   <- REPLACES the Android boot image (your backup stays in $BACKUP)"
    echo "  2. fastboot flash userdata  $FLASHROOT    <- ERASES whatever is in userdata"
    echo "  Android will not start until you run tools/restore-android.sh" ;;
esac
echo "  Never written: preloader, lk, gpt, nvram, nvdata, protect1/2, secro, proinfo, system, vendor."
echo "  Undo: tools/restore-android.sh --backup-dir $BACKUP"
if [ "$MODE" != test ] && [ "$YES" = 0 ] && [ "$DRY" = 0 ]; then
  printf '\nType INSTALL (capital letters) to continue, anything else aborts: '; read -r a; [ "$a" = INSTALL ] || die "aborted, nothing was written"
fi

case "$MODE" in
  test) run "${FB[@]}" boot "$BOOTIMG"; echo "Booted temporarily. To leave: power off -> normal start = Android." ;;
  install-recovery) flash recovery "$BOOTIMG"; flash userdata "$FLASHROOT"
    echo; echo "DONE. Rootfs installed in userdata; on first start Rembley expands it to fill the partition automatically."
    echo "Boot Linux via the recovery entry. Android still starts normally." ;;
  install-boot) flash boot "$BOOTIMG"; flash userdata "$FLASHROOT"; run "${FB[@]}" reboot
    echo; echo "DONE. Rembley is the default system now. To return to Android: tools/restore-android.sh --backup-dir $BACKUP" ;;
esac
