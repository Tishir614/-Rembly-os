#!/bin/sh
# First boot (and every boot until it succeeds once): if the Wi-Fi helper files are missing, take them from the tablet's own
# Android partitions (read-only). Runs in the background, never delays boot, retried after a failed attempt only by hand or on the next boot
# when the Android partitions appeared. Network start is done by rembley-drivers itself when it succeeds.
[ -x /system/bin/wmt_launcher ] && exit 0
[ -e /var/lib/rembley/drivers-tried ] && exit 0
setsid /usr/local/bin/rembley-drivers install --auto >/var/log/rembley-drivers.log 2>&1 </dev/null &
