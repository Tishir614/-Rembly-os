#!/bin/sh
# Best effort: unmute common ALSA controls (the MediaTek sound card may need Android libs, see docs).
command -v amixer >/dev/null || exit 0
[ -e /dev/snd/controlC0 ] || mdev -s
for c in Master Speaker Headphone PCM Playback; do amixer -q sset "$c" 70% unmute 2>/dev/null; done
cat /proc/asound/cards 2>/dev/null || echo "no ALSA cards"
