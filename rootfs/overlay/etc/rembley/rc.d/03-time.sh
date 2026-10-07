#!/bin/sh
# No usable RTC: never let the clock go before the last known time (TLS/apt break otherwise).
mkdir -p /var/lib/rembley
last=$(cat /var/lib/rembley/lasttime 2>/dev/null || echo 0); built=$(cat /etc/rembley/buildtime 2>/dev/null || echo 0)
base=$last; [ "$built" -gt "$base" ] && base=$built
now=$(date +%s); [ "$now" -lt "$base" ] && date -s "@$base" >/dev/null && echo "clock set from stamp: $(date)"
[ -f /etc/rembley/timezone ] && ln -sf "/usr/share/zoneinfo/$(cat /etc/rembley/timezone)" /etc/localtime
