#!/bin/sh
# Automatic first-boot setup in the background (never delays boot). Done = every step marked in /var/lib/rembley/auto-*.
[ -e /var/lib/rembley/auto-update ] && exit 0
setsid /usr/local/bin/rembley-autosetup >>/var/log/rembley-autosetup.log 2>&1 </dev/null &
