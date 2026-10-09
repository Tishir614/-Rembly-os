#!/bin/sh
# Smoothness tuning for the A73 (MT6737M, 2 GB, eMMC). Every write is best-effort: a missing knob is simply skipped.
TMP_MB=128; [ -r /etc/rembly/device.conf ] && . /etc/rembly/device.conf
w() { [ -w "$2" ] && echo "$1" > "$2" 2>/dev/null; }
for q in /sys/block/mmcblk*/queue /sys/block/sd*/queue; do          # eMMC/SD: no seek penalty -> cheapest scheduler, modest read-ahead
  [ -d "$q" ] || continue
  for s in mq-deadline deadline noop none; do grep -qw "$s" "$q/scheduler" 2>/dev/null && { w $s "$q/scheduler"; break; }; done
  w 256 "$q/read_ahead_kb"; w 0 "$q/add_random"; w 0 "$q/iostats"
done
w never /sys/kernel/mm/transparent_hugepage/enabled
w 0 /proc/sys/kernel/sched_autogroup_enabled
w 0 /proc/sys/vm/oom_kill_allocating_task
w 1 /proc/sys/vm/overcommit_memory
w 262144 /proc/sys/fs/inotify/max_user_watches
w 65536 /proc/sys/net/core/rmem_max; w 65536 /proc/sys/net/core/wmem_max
# keep the UI cores awake while the tablet is in use (stock governor stays; only the floor is raised if the kernel allows it)
for c in /sys/devices/system/cpu/cpu[0-9]*/cpufreq; do
  [ -r "$c/scaling_available_governors" ] && grep -qw interactive "$c/scaling_available_governors" && w interactive "$c/scaling_governor"
done
mount -o remount,noatime / 2>/dev/null                                # fewer writes to eMMC
mountpoint -q /tmp || mount -t tmpfs -o size=${TMP_MB}m,mode=1777,noatime tmpfs /tmp 2>/dev/null
echo "tune: scheduler=$(cat /sys/block/mmcblk0/queue/scheduler 2>/dev/null) governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
