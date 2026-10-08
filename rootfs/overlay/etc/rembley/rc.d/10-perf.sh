#!/bin/sh
# Anti-lag tuning for 2 GB RAM / slow eMMC: zram swap (lz4), sane VM sysctls, OOM guard.
MEM_KB=$(awk '/MemTotal/{print $2}' /proc/meminfo)
ZRAM_PCT=70; MIN_FREE_KB=16384; [ -r /etc/rembley/device.conf ] && . /etc/rembley/device.conf     # measured values (rc.d/04-device.sh)
if [ -e /sys/block/zram0 ] || [ -e /dev/zram0 ]; then
  [ -e /dev/zram0 ] || mdev -s
  echo lz4 > /sys/block/zram0/comp_algorithm 2>/dev/null || echo lzo > /sys/block/zram0/comp_algorithm 2>/dev/null
  echo $((MEM_KB * 1024 * ZRAM_PCT / 100)) > /sys/block/zram0/disksize 2>/dev/null
  mkswap /dev/zram0 >/dev/null 2>&1 && swapon -p 100 /dev/zram0 && echo "zram swap on ($((MEM_KB * ZRAM_PCT / 100 / 1024)) MiB)"
else echo "no zram device"; fi
S=/proc/sys/vm
echo 100 > $S/swappiness; echo 0 > $S/page-cluster; echo 5 > $S/dirty_background_ratio; echo 15 > $S/dirty_ratio
echo 3000 > $S/dirty_expire_centisecs 2>/dev/null; echo $MIN_FREE_KB > $S/min_free_kbytes 2>/dev/null
echo 100 > $S/vfs_cache_pressure
# earlyoom kills the biggest hog before the tablet freezes under memory pressure
command -v earlyoom >/dev/null && setsid earlyoom -m 6 -s 90 -r 0 -n --prefer '(chrome|firefox|netsurf|epiphany|python3)' --avoid '(Xorg|rembley-shell|xfwm4|dbus-daemon|adbd)' >/var/log/earlyoom.log 2>&1 </dev/null &
# keep the scheduler responsive: interactive governor is the stock default; just report it
echo "cpufreq: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
