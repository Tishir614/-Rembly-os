#!/bin/sh
# Measure THIS tablet at every boot and derive its settings from the measurements (RAM -> zram/tmp/min_free, panel -> DPI, backlight, governor ...).
# Result: /etc/rembley/device.conf, read by 10-perf.sh and 12-tune.sh. Takes well under a second.
/usr/local/bin/rembley-hwprobe --apply 2>&1 | head -5
