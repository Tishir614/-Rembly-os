#!/bin/sh
# No usable RTC: never let the clock go before the last known time (TLS/apt break otherwise).
mkdir -p /var/lib/rembly
last=$(cat /var/lib/rembly/lasttime 2>/dev/null || echo 0); built=$(cat /etc/rembly/buildtime 2>/dev/null || echo 0)
base=$last; [ "$built" -gt "$base" ] && base=$built
now=$(date +%s); [ "$now" -lt "$base" ] && date -s "@$base" >/dev/null && echo "clock set from stamp: $(date)"
[ -f /etc/rembly/timezone ] && ln -sf "/usr/share/zoneinfo/$(cat /etc/rembly/timezone)" /etc/localtime
