#!/bin/sh
# Strict first-boot setup in the background (never delays boot). Runs while any step is unverified (see: rembly-autosetup status).
/usr/local/bin/rembly-autosetup --pending || exit 0
setsid /usr/local/bin/rembly-autosetup >>/var/log/rembly-autosetup.log 2>&1 </dev/null &
