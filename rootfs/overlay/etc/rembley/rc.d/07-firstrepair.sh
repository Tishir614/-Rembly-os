#!/bin/sh
# First start after flashing: find files that did not arrive (or arrived damaged) and download them. Background, low priority, never delays boot.
# Repeats at the next starts until a full check passes (flag /var/lib/rembley/repair-firstboot-done).
[ -e /var/lib/rembley/repair-firstboot-done ] && exit 0
setsid nice -n 10 /usr/local/bin/rembley-repair firstboot >>/var/log/rembley-repair.log 2>&1 </dev/null &
