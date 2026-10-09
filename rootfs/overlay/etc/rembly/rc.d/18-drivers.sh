#!/bin/sh
# First boot (and every boot until it succeeds once): if the Wi-Fi helper files are missing, take them from the tablet's own
# Android partitions (read-only). Runs in the background, never delays boot, retried after a failed attempt only by hand or on the next boot
# when the Android partitions appeared. Network start is done by rembly-drivers itself when it succeeds.
[ -x /system/bin/wmt_launcher ] && exit 0
[ -e /var/lib/rembly/drivers-tried ] && exit 0
setsid /usr/local/bin/rembly-drivers install --auto >/var/log/rembly-drivers.log 2>&1 </dev/null &
