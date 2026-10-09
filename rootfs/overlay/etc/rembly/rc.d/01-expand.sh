#!/bin/sh
# First boot after a raw flash (fastboot flash userdata rembly-rootfs.img): the ext4 image is smaller than the partition.
# Grow it once, online. Skipped for loop/file-based roots and when nothing to do.
MOUNTS=${MOUNTS:-/proc/mounts}
rd=$(awk '$2=="/" && $1 ~ /^\/dev\// {d=$1} END{print d}' "$MOUNTS")
case "$rd" in /dev/mmcblk*|/dev/sd*) ;; *) [ "$EXPAND_ANY" = 1 ] || exit 0 ;; esac   # EXPAND_ANY is for tests only
STATE=${STATE:-/var/lib/rembly}; mkdir -p "$STATE"; stamp=$STATE/expanded
part_kb=$(( $(cat "/sys/class/block/$(basename "$rd")/size" 2>/dev/null || echo 0) / 2 )); [ "$part_kb" -gt 0 ] || exit 0
[ "$(cat $stamp 2>/dev/null)" = "$part_kb" ] && exit 0
if resize2fs "$rd" 2>&1; then echo "$part_kb" > $stamp; echo "root filesystem now fills $rd (${part_kb} KiB)"; fi
