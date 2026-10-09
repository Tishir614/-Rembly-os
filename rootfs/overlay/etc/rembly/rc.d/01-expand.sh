#!/bin/sh
# First boot after a raw flash (fastboot flash userdata rembly-rootfs.img): the ext4 image is smaller than the partition. Grow it once, ONLINE,
# in the BACKGROUND at low priority (on slow eMMC a big resize takes minutes: it must never hold the boot on the logo). Skipped for loop/file roots.
# Disable: touch /etc/rembly/noexpand.   Log: /var/log/rembly-expand.log
[ -e /etc/rembly/noexpand ] && exit 0
MOUNTS=${MOUNTS:-/proc/mounts}
rd=$(awk '$2=="/" && $1 ~ /^\/dev\// {d=$1} END{print d}' "$MOUNTS")
case "$rd" in /dev/mmcblk*|/dev/sd*) ;; *) [ "$EXPAND_ANY" = 1 ] || exit 0 ;; esac   # EXPAND_ANY is for tests only
STATE=${STATE:-/var/lib/rembly}; mkdir -p "$STATE"; stamp=$STATE/expanded
part_kb=$(( $(cat "/sys/class/block/$(basename "$rd")/size" 2>/dev/null || echo 0) / 2 )); [ "$part_kb" -gt 0 ] || exit 0
[ "$(cat $stamp 2>/dev/null)" = "$part_kb" ] && exit 0
if [ "$EXPAND_FOREGROUND" = 1 ]; then
  resize2fs "$rd" 2>&1 && echo "$part_kb" > $stamp && echo "root filesystem now fills $rd (${part_kb} KiB)"
else
  echo "growing the root filesystem in the background (log: /var/log/rembly-expand.log)"
  ( echo "$(date) start $rd -> ${part_kb} KiB"; nice -n 15 ionice -c3 resize2fs "$rd" 2>&1 && echo "$part_kb" > $stamp && echo "$(date) done"; echo "rc=$?" ) >>/var/log/rembly-expand.log 2>&1 </dev/null &
fi
