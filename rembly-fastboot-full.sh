#!/usr/bin/env bash
# Rembly OS non-interactive Fastboot installer for A73 / K37MV1_BSP.
# Replaces userdata with the current Rembly rootfs and flashes the current Rembly boot image.
# No prompts, no countdown, no temporary stage-1 boot.
#
# IMPORTANT: this tablet's old LK is known to misreport userdata size and has previously
# stalled on large writes. We therefore ignore partition-size:userdata and force small
# sparse Fastboot chunks when the host fastboot supports -S.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
OUT="$ROOT/out"
BOOTIMG="$OUT/A73-linux-test.img"
ROOTFS="$OUT/rembly-rootfs.img"
SPARSE="$OUT/rembly-rootfs.sparse.img"
EXPECTED_PRODUCT=K37MV1_BSP

fail() { printf '\n[REMBLY] ERROR: %s\n' "$*" >&2; exit 1; }
msg()  { printf '[REMBLY] %s\n' "$*"; }

command -v fastboot >/dev/null 2>&1 || fail "fastboot not found"
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum not found"
[[ -s "$BOOTIMG" ]] || fail "missing $BOOTIMG"
[[ -s "$ROOTFS" ]] || fail "missing $ROOTFS"

# Rootfs must be the Rembly ext4 image, not an arbitrary file.
label=$(dd if="$ROOTFS" bs=8 skip=143 count=2 2>/dev/null | tr -d '\000')
[[ "$label" == REMBLY ]] || fail "rootfs label is '$label', expected REMBLY"

bootsz=$(stat -c %s "$BOOTIMG")
(( bootsz < 16*1024*1024 )) || fail "boot image does not fit the 16 MiB boot partition"

# Prefer sparse image. It reduces USB traffic and, together with -S, splits a large
# flash into smaller Fastboot transfers which old MediaTek LK handles better.
if [[ ! -s "$SPARSE" || "$ROOTFS" -nt "$SPARSE" ]]; then
  command -v img2simg >/dev/null 2>&1 || fail "rembly-rootfs.sparse.img is missing and img2simg is not installed"
  msg "Creating fresh sparse rootfs image"
  img2simg "$ROOTFS" "$SPARSE"
fi

mapfile -t devices < <(fastboot devices 2>/dev/null | awk 'NF{print $1}')
((${#devices[@]} == 1)) || fail "exactly one Fastboot device must be connected"
SERIAL=${devices[0]}

fbget() {
  fastboot -s "$SERIAL" getvar "$1" 2>&1 | sed -nE "s/^(INFO)?$1:[[:space:]]*//p" | head -n1 | tr -d '\r'
}

product=$(fbget product || true)
unlocked=$(fbget unlocked || true)
[[ "$product" == "$EXPECTED_PRODUCT" ]] || fail "device is '$product', expected $EXPECTED_PRODUCT"
[[ "$unlocked" == yes ]] || fail "bootloader is not unlocked (unlocked=$unlocked)"

msg "Device: $SERIAL / $product"
msg "Boot: $(du -h "$BOOTIMG" | awk '{print $1}')  sha256=$(sha256sum "$BOOTIMG" | awk '{print $1}')"
msg "Rootfs: $(du -h "$ROOTFS" | awk '{print $1}')  label=REMBLY"
msg "Starting automatic Fastboot install. userdata will be replaced."

# Do not trust getvar partition-size:userdata on this LK. It is known to report
# 0x32000000 although the real GPT userdata partition is much larger.
msg "Erasing userdata"
fastboot -s "$SERIAL" erase userdata

# Clean stale Android cache/metadata when these erase commands are supported.
fastboot -s "$SERIAL" erase cache >/dev/null 2>&1 || true
fastboot -s "$SERIAL" erase metadata >/dev/null 2>&1 || true

FB=(-s "$SERIAL")
if fastboot --help 2>&1 | grep -q -- '-S'; then
  FB+=(-S 32M)
  msg "Fastboot sparse limit: 32 MiB"
else
  msg "Host fastboot has no -S option; using its default sparse transfer size"
fi

msg "Flashing complete Rembly rootfs to userdata"
# Never flash boot first. If userdata fails, the currently installed boot remains intact.
timeout --signal=KILL 45m fastboot "${FB[@]}" flash userdata "$SPARSE" || \
  fail "userdata Fastboot flash failed or timed out; boot was not changed"

msg "Flashing Rembly boot"
fastboot -s "$SERIAL" flash boot "$BOOTIMG"

msg "Rebooting"
fastboot -s "$SERIAL" reboot || true

printf '\n[REMBLY] INSTALL COMPLETE\n'
