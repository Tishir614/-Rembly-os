#!/bin/sh
# Bring up Wi-Fi/Bluetooth in the background (needs android blobs, see docs). Never blocks boot.
setsid /usr/local/bin/rembly-net auto >/var/log/rembly-net.log 2>&1 </dev/null &
