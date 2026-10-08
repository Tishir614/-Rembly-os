#!/bin/sh
# Strict first-boot setup in the background (never delays boot). Runs while any step is unverified (see: rembley-autosetup status).
/usr/local/bin/rembley-autosetup --pending || exit 0
setsid /usr/local/bin/rembley-autosetup >>/var/log/rembley-autosetup.log 2>&1 </dev/null &
