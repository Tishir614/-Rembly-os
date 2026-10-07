#!/usr/bin/env bash
# Stage 2: Rembley OS rootfs (Ubuntu 20.04 "focal" armhf, no systemd as PID 1) -> ext4 image labelled REMBLEY.
# Run as root on an x86-64 Ubuntu/Debian PC:  sudo rootfs/build-rootfs.sh [size_MiB] [minimal|desktop]
# Needs: debootstrap qemu-user-static e2fsprogs (binfmt_misc enabled).
set -euo pipefail
SIZE=${1:-3584}; PROFILE=${2:-desktop}
HERE=$(cd "$(dirname "$0")/.." && pwd); OUT=$HERE/out; R=${ROOTFS_DIR:-/var/rembley/rootfs}
MIRROR=${MIRROR:-https://ports.ubuntu.com/ubuntu-ports}
mkdir -p "$OUT" "$(dirname "$R")"

if [ ! -f "$R/etc/os-release" ]; then
  [ -e /proc/sys/fs/binfmt_misc/qemu-arm ] || { mountpoint -q /proc/sys/fs/binfmt_misc || mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
    head -1 /usr/lib/binfmt.d/qemu-arm.conf > /proc/sys/fs/binfmt_misc/register; }
  debootstrap --arch=armhf --variant=minbase --components=main,universe \
    --include=ca-certificates,iproute2,openssh-server,nano,less,kmod,udev,sudo,busybox-static,dbus,locales \
    focal "$R" "$MIRROR" /usr/share/debootstrap/scripts/gutsy
fi

cleanup() { for m in dev/pts dev proc sys; do umount "$R/$m" 2>/dev/null || true; done; }
trap cleanup EXIT
mount --bind /dev "$R/dev"; mount -t devpts devpts "$R/dev/pts" 2>/dev/null || true
mount -t proc proc "$R/proc"; mount -t sysfs sys "$R/sys"
cp /etc/resolv.conf "$R/etc/resolv.conf"
cat > "$R/etc/apt/sources.list" <<L
deb $MIRROR focal main universe
deb $MIRROR focal-updates main universe
deb $MIRROR focal-security main universe
L
# keep maintainer scripts from trying to start services in the chroot
printf '#!/bin/sh\nexit 101\n' > "$R/usr/sbin/policy-rc.d"; chmod +x "$R/usr/sbin/policy-rc.d"

PKGS_MIN="git python3 python3-pip python3-venv build-essential cmake make gdb nodejs wget curl htop tmux vim-tiny rsync zip unzip \
 openssh-client neofetch bluez usbutils net-tools wpasupplicant iw rfkill ppp wireless-tools earlyoom"
# Light desktop: Xorg + xfwm4 (no compositor) + our own GTK shell instead of full XFCE session/panel/xfdesktop.
PKGS_DESK="xserver-xorg-core xserver-xorg-video-fbdev xserver-xorg-input-libinput xinit x11-xserver-utils x11-utils xinput unclutter \
 xfwm4 xfce4-settings xfce4-terminal xfce4-taskmanager xfce4-appfinder thunar mousepad dbus-x11 \
 python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-pil wmctrl playerctl onboard \
 fonts-noto-core fonts-dejavu-core papirus-icon-theme adwaita-icon-theme gtk2-engines-pixbuf \
 netsurf-gtk geany galculator mpv gpicview atril audacious file-roller"
chroot "$R" /usr/bin/env DEBIAN_FRONTEND=noninteractive sh -ec "
  apt-get update
  apt-get install -y --no-install-recommends $PKGS_MIN $( [ "$PROFILE" = desktop ] && echo "$PKGS_DESK" )
  locale-gen C.UTF-8 >/dev/null 2>&1 || true
  echo root:rembley | chpasswd
  ssh-keygen -A
  apt-get clean; rm -rf /var/lib/apt/lists/*"
rm -f "$R/usr/sbin/policy-rc.d"

# overlay LAST so our /sbin/init replaces systemd's
rm -f "$R/usr/sbin/init" "$R/sbin/init"   # was a symlink to systemd; never write through it
cp -a --remove-destination "$HERE/rootfs/overlay/." "$R/"
rm -f "$R/etc/X11/xorg.conf.d/20-touch.conf" "$R/etc/X11/xorg.conf.d/10-fbdev.conf"   # superseded by files generated at session start
mkdir -p "$R/system/bin" "$R/var/log" "$R/run/user" "$R/root/Projects"
ln -sf /bin/busybox "$R/sbin/mdev"
if [ -f "$OUT/android-blobs.tar.gz" ]; then      # Wi-Fi/BT/modem blobs from the user's own firmware (tools/extract_android_blobs.py)
  echo "== adding android blobs"; tar -xzf "$OUT/android-blobs.tar.gz" -C "$R"
else echo "NOTE: out/android-blobs.tar.gz not found -> no Wi-Fi/BT/SIM (see docs/NETWORK.md)"; fi
ln -sf /bin/sh "$R/system/bin/sh"        # adbd (started by stage 1) expects /system/bin/sh
chmod +x "$R/usr/sbin/init"; [ -e "$R/sbin/init" ] || ln -s /usr/sbin/init "$R/sbin/init"
cleanup; trap - EXIT

echo "== packing ext4 image (${SIZE} MiB, label REMBLEY)"
IMG=$OUT/rembley-rootfs.img
rm -f "$IMG"; truncate -s "${SIZE}M" "$IMG"
mke2fs -q -t ext4 -L REMBLEY -d "$R" -F "$IMG"
du -sh "$R"; ls -lh "$IMG"; sha256sum "$IMG" | tee "$IMG.sha256"
echo "Copy to SD/USB as a REMBLEY-labelled ext4 partition, or put on any fs as /rembley-rootfs.img"
