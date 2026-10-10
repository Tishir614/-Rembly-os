#!/usr/bin/env bash
# Rembly OS installer entry point.
# The core owns build/Fastboot logic. This wrapper also adopts an already-built
# legacy rootfs once and provides an automatic MediaTek boot-only fallback when
# this tablet powers down into MT65xx Preloader instead of entering Fastboot.
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CORE="$ROOT/rembly-install-core.sh"
OUT="$ROOT/out"
MTK_FALLBACK="$ROOT/tools/rembly-mtk-boot.sh"
CORE_LOG="$OUT/rembly-install-core.log"
[[ -f "$CORE" ]] || { echo "Rembly installer core not found: $CORE" >&2; exit 1; }
mkdir -p "$OUT"

want_rebuild=0
for a in "$@"; do [[ "$a" == --rebuild ]] && want_rebuild=1; done

# Adopt a legacy rootfs marker without rebuilding 3.5 GiB just because the
# installer gained source IDs after that image was originally created.
if (( ! want_rebuild )) && [[ -s "$OUT/rembly-rootfs.img" && ! -f "$OUT/rembly-rootfs.source-id" ]]; then
  tree_hash=$(
    cd "$ROOT"
    while IFS= read -r -d '' f; do sha256sum "$f"; done < <(find rootfs -type f -print0 | sort -z)
  )
  tree_hash=$(printf '%s\n' "$tree_hash" | sha256sum | awk '{print $1}')
  rid=$(printf 'rootfs-tree=%s\nprofile=desktop\nsize=3584\n' "$tree_hash" | sha256sum | awk '{print $1}')
  printf '%s\n' "$rid" > "$OUT/rembly-rootfs.source-id"
  printf '[REMBLY] Existing rootfs adopted. It will be compared before any userdata flash.\n'
fi

# Before asking Rembly to reboot, remember whether the currently running tablet
# already has the same rootfs. This lets us safely fall back to MTK boot-only
# flashing if `adb reboot bootloader` lands in Preloader instead of Fastboot.
ROOTFS_CONFIRMED=0
if command -v adb >/dev/null 2>&1; then
  mapfile -t adb_serials < <(adb devices 2>/dev/null | awk '$2=="device" || $2=="recovery"{print $1}')
  if ((${#adb_serials[@]} == 1)); then
    serial=${adb_serials[0]}
    product=$(timeout 5s adb -s "$serial" shell getprop ro.product.device 2>/dev/null | tr -d '\r\n' || true)
    if [[ "${product,,}" == "k37mv1_bsp" ]]; then
      local_id=$(cat "$OUT/rembly-rootfs.source-id" 2>/dev/null || true)
      remote_id=$(timeout 10s adb -s "$serial" shell 'cat /etc/rembly/image-id 2>/dev/null' 2>/dev/null | tr -d '\r\n' || true)
      if [[ -n "$local_id" && -n "$remote_id" && "$local_id" == "$remote_id" ]]; then
        ROOTFS_CONFIRMED=1
      else
        local_time=$(tr -dc '0-9' < "$OUT/rembly-rootfs.buildtime" 2>/dev/null || true)
        if [[ -z "$local_time" && -s "$OUT/rembly-rootfs.img" ]] && command -v debugfs >/dev/null 2>&1; then
          local_time=$(debugfs -R 'cat /etc/rembly/buildtime' "$OUT/rembly-rootfs.img" 2>/dev/null | tr -dc '0-9\n' | head -n1 || true)
        fi
        remote_time=$(timeout 10s adb -s "$serial" shell 'cat /etc/rembly/buildtime 2>/dev/null' 2>/dev/null | tr -dc '0-9' || true)
        [[ -n "$local_time" && -n "$remote_time" && "$local_time" == "$remote_time" ]] && ROOTFS_CONFIRMED=1
      fi
      (( ROOTFS_CONFIRMED )) && printf '[REMBLY] Existing userdata/rootfs confirmed before reboot.\n'
    fi
  fi
fi

# Normal path: core builds everything, detects ADB/Fastboot, compares images,
# flashes only changed partitions and writes boot last. For a confirmed existing
# Rembly rootfs, use a finite default wait so we can automatically switch to
# MediaTek Preloader if this old LK never exposes Fastboot.
if [[ -v REMBLY_WAIT_SECONDS ]]; then
  core_wait=$REMBLY_WAIT_SECONDS
elif (( ROOTFS_CONFIRMED )); then
  core_wait=25
else
  core_wait=0
fi

set +e
REMBLY_WAIT_SECONDS="$core_wait" bash "$CORE" "$@" 2>&1 | tee "$CORE_LOG"
core_rc=${PIPESTATUS[0]}
set -e

(( core_rc == 0 )) && exit 0

# Never hide build/rootfs/validation errors behind the MTK fallback. It is used
# only after the core successfully got as far as waiting for Fastboot, and only
# if userdata was positively confirmed beforehand.
if (( ROOTFS_CONFIRMED )) && \
   grep -q 'не появился в Fastboot' "$CORE_LOG" 2>/dev/null && \
   [[ -f "$MTK_FALLBACK" ]]; then
  printf '\n[REMBLY] Fastboot не появился, но rootfs уже подтверждён. Пробую MT65xx Preloader автоматически.\n'
  bash "$MTK_FALLBACK"
  exit $?
fi

exit "$core_rc"
