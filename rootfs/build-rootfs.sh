#!/usr/bin/env bash
# Stage 2: Alpine armv7 rootfs image (label REMBLEY). Run as root on an x86 PC with qemu-user-static.
# Usage: sudo rootfs/build-rootfs.sh [size_MiB]   -> out/rembley-rootfs.img
set -euo pipefail
SIZE=${1:-3072}; ALPINE=${ALPINE_BRANCH:-v3.20}; REL=${ALPINE_REL:-3.20.3}
HERE=$(cd "$(dirname "$0")/.." && pwd); OUT=$HERE/out; M=$OUT/mnt
mkdir -p "$OUT" "$M"
TAR=$OUT/alpine-minirootfs-$REL-armv7.tar.gz
[ -f "$TAR" ] || curl -fsSL -o "$TAR" "https://dl-cdn.alpinelinux.org/alpine/$ALPINE/releases/armv7/alpine-minirootfs-$REL-armv7.tar.gz"
truncate -s "${SIZE}M" "$OUT/rembley-rootfs.img"
mkfs.ext4 -F -L REMBLEY "$OUT/rembley-rootfs.img"
mount -o loop "$OUT/rembley-rootfs.img" "$M"; trap 'umount "$M/dev" "$M/proc" "$M/sys" 2>/dev/null; umount "$M"' EXIT
tar -xzf "$TAR" -C "$M"
cp "$(command -v qemu-arm-static)" "$M/usr/bin/"
mount --bind /dev "$M/dev"; mount -t proc proc "$M/proc"; mount -t sysfs sys "$M/sys"
cp /etc/resolv.conf "$M/etc/resolv.conf"
cp -a "$HERE/rootfs/overlay/." "$M/"
chroot "$M" /bin/sh -e <<'CH'
echo "https://dl-cdn.alpinelinux.org/alpine/v3.20/main
https://dl-cdn.alpinelinux.org/alpine/v3.20/community" > /etc/apk/repositories
apk update
# base + dev tools
apk add alpine-base openrc openssh git python3 gcc g++ make cmake musl-dev nano htop
# graphics: Xorg on plain fbdev, touch via libinput, XFCE, on-screen keyboard
apk add xorg-server xf86-video-fbdev xf86-input-libinput xf86-input-evdev xinit \
        xfce4 xfce4-terminal thunar onboard-or-fallback 2>/dev/null || \
apk add xorg-server xf86-video-fbdev xf86-input-libinput xinit xfce4 xfce4-terminal thunar
apk add bluez firefox-esr 2>/dev/null || true
echo rembley > /etc/hostname
echo 'root:rembley' | chpasswd
rc-update add devfs sysinit; rc-update add sshd default; rc-update add bluetooth default 2>/dev/null || true
CH
echo "done: $OUT/rembley-rootfs.img  (copy to SD/USB as a partition labelled REMBLEY, or as /rembley-rootfs.img on any fs)"
