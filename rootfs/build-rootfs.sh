#!/usr/bin/env bash
# Stage 2: Rembly OS rootfs (Ubuntu 20.04 focal armhf, no systemd as PID 1) -> ext4 image labelled REMBLY.
# Run as root on an x86-64 Ubuntu/Debian PC: sudo rootfs/build-rootfs.sh [size_MiB] [minimal|desktop]
# Needs: debootstrap qemu-user-static e2fsprogs (binfmt_misc enabled).
set -euo pipefail
SIZE=${1:-3584}; PROFILE=${2:-desktop}
HERE=$(cd "$(dirname "$0")/.." && pwd); OUT=$HERE/out; R=${ROOTFS_DIR:-/var/rembly/rootfs}
MIRROR=${MIRROR:-https://ports.ubuntu.com/ubuntu-ports}
IMAGE_ID=${REMBLY_IMAGE_ID:-unknown}
mkdir -p "$OUT" "$(dirname "$R")"

# Wi-Fi/BT helper files: if you point ANDROID_DUMP at your backup folder (system.bin + vendor.bin) they are extracted automatically.
if [ -n "${ANDROID_DUMP:-}" ] && { [ ! -f "$OUT/android-blobs.tar.gz" ] || [ -n "${REFRESH_BLOBS:-}" ]; }; then
  [ -f "$ANDROID_DUMP/system.bin" ] || { echo "ANDROID_DUMP=$ANDROID_DUMP has no system.bin" >&2; exit 1; }
  vend=(); [ -f "$ANDROID_DUMP/vendor.bin" ] && vend=("$ANDROID_DUMP/vendor.bin")
  echo "== extracting Wi-Fi/BT files from $ANDROID_DUMP"
  python3 "$HERE/tools/extract_android_blobs.py" "$ANDROID_DUMP/system.bin" "${vend[@]}" -o "$OUT/android-blobs.tar.gz"
fi

# Register qemu-arm without assuming a distro-specific /usr/lib/binfmt.d file.
if [ ! -e /proc/sys/fs/binfmt_misc/qemu-arm ]; then
  mountpoint -q /proc/sys/fs/binfmt_misc || mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
  if command -v update-binfmts >/dev/null 2>&1; then
    update-binfmts --import qemu-arm >/dev/null 2>&1 || true
    update-binfmts --enable qemu-arm >/dev/null 2>&1 || true
  fi
  if [ ! -e /proc/sys/fs/binfmt_misc/qemu-arm ] && command -v service >/dev/null 2>&1; then
    service binfmt-support restart >/dev/null 2>&1 || true
  fi
fi
[ -e /proc/sys/fs/binfmt_misc/qemu-arm ] || {
  echo "ERROR: qemu-arm binfmt registration failed" >&2
  exit 1
}

if [ ! -f "$R/etc/os-release" ]; then
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
printf '#!/bin/sh\nexit 101\n' > "$R/usr/sbin/policy-rc.d"; chmod +x "$R/usr/sbin/policy-rc.d"

PKGS_MIN="git python3 python3-pip python3-venv build-essential cmake make gdb nodejs wget curl htop tmux vim-tiny rsync zip unzip \
 openssh-client neofetch bluez usbutils net-tools wpasupplicant iw rfkill ppp wireless-tools earlyoom \
 tzdata locales ncdu mc alsa-utils strace"
PKGS_DESK="xserver-xorg-core xdotool ntfs-3g exfat-fuse exfat-utils xserver-xorg-video-fbdev xserver-xorg-input-libinput xinit x11-xserver-utils x11-utils xinput unclutter \
 xfwm4 xfce4-settings xfce4-terminal xfce4-taskmanager xfce4-appfinder thunar mousepad dbus-x11 \
 python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-pil wmctrl playerctl onboard \
 fonts-noto-core fonts-dejavu-core papirus-icon-theme adwaita-icon-theme gtk2-engines-pixbuf \
 libglib2.0-bin qt5-gtk-platformtheme libfuse2 squashfs-tools desktop-file-utils shared-mime-info netsurf-gtk geany galculator mpv atril file-roller \
 gir1.2-gtksource-4 gir1.2-vte-2.91 python3-mutagen \
 sshfs picocom freerdp2-x11 xtightvncviewer telnet \
 dunst libnotify-bin xprintidle scrot x11-xkb-utils xdg-utils fonts-firacode"

chroot "$R" /usr/bin/env DEBIAN_FRONTEND=noninteractive sh -ec "
  apt-get -o Acquire::Retries=8 -o Acquire::https::Timeout=60 -o Acquire::http::Timeout=60 update
  apt-get -o Acquire::Retries=8 -o Acquire::https::Timeout=60 -o Acquire::http::Timeout=60 \
    install -y --fix-missing --no-install-recommends $PKGS_MIN $( [ "$PROFILE" = desktop ] && echo "$PKGS_DESK" )
  apt-get purge -y audacious gpicview >/dev/null 2>&1 || true
  apt-get autoremove --purge -y >/dev/null 2>&1 || true
  for l in ru_RU.UTF-8 en_US.UTF-8; do locale-gen \$l >/dev/null 2>&1 || true; done
  update-locale LANG=ru_RU.UTF-8 2>/dev/null || true
  ln -sf /usr/share/zoneinfo/UTC /etc/localtime; echo UTC > /etc/timezone
  echo root:rembly | chpasswd
  ssh-keygen -A
  apt-get clean; rm -rf /var/lib/apt/lists/*"
rm -f "$R/usr/sbin/policy-rc.d"

# Overlay LAST so our /sbin/init replaces systemd's.
find "$HERE/rootfs/overlay" -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null
rm -f "$R/usr/sbin/init" "$R/sbin/init"
cp -a --remove-destination "$HERE/rootfs/overlay/." "$R/"
chroot "$R" glib-compile-schemas --strict /usr/share/glib-2.0/schemas
chroot "$R" sh -c "update-desktop-database /usr/share/applications; update-mime-database /usr/share/mime" >/dev/null 2>&1 || true
rm -f "$R/etc/X11/xorg.conf.d/20-touch.conf" "$R/etc/X11/xorg.conf.d/10-fbdev.conf"
mkdir -p "$R/system/bin" "$R/var/log" "$R/run/user" "$R/root/Projects" "$R/etc/rembly"
ln -sf /bin/busybox "$R/sbin/mdev"
if [ -f "$OUT/android-blobs.tar.gz" ]; then
  echo "== adding android blobs"; tar -xzf "$OUT/android-blobs.tar.gz" -C "$R"
else
  echo "NOTE: no android-blobs.tar.gz in the image; first boot will try system/vendor."
fi
ln -sf /bin/sh "$R/system/bin/sh"
chroot "$R" python3 -m compileall -q /usr/local/lib/rembly
BUILD_TIME=$(date +%s)
printf '%s\n' "$BUILD_TIME" > "$R/etc/rembly/buildtime"
printf '%s\n' "$IMAGE_ID" > "$R/etc/rembly/image-id"
printf '%s\n' "$BUILD_TIME" > "$OUT/rembly-rootfs.buildtime"
printf '%s\n' "$IMAGE_ID" > "$OUT/rembly-rootfs.image-id"
python3 "$HERE/rootfs/overlay/usr/local/bin/rembly-repair" manifest "$HERE/rootfs/overlay" > "$R/usr/share/rembly/MANIFEST.sha256"
printf '%s\n' $PKGS_MIN $( [ "$PROFILE" = desktop ] && echo "$PKGS_DESK" ) | sort -u > "$R/usr/share/rembly/packages.txt"
chmod +x "$R/usr/sbin/init" "$R"/usr/local/bin/rembly-* "$R"/etc/rembly/rc.d/*.sh "$R/etc/rembly/udhcpc.script"
[ -e "$R/sbin/init" ] || ln -s /usr/sbin/init "$R/sbin/init"
cleanup; trap - EXIT

echo "== packing ext4 image (${SIZE} MiB, label REMBLY)"
IMG=$OUT/rembly-rootfs.img
rm -f "$IMG"; truncate -s "${SIZE}M" "$IMG"
mke2fs -q -t ext4 -L REMBLY -d "$R" -F "$IMG"
du -sh "$R"; ls -lh "$IMG"; sha256sum "$IMG" | tee "$IMG.sha256"
if command -v img2simg >/dev/null; then
  img2simg "$IMG" "$OUT/rembly-rootfs.sparse.img"
  ls -lh "$OUT/rembly-rootfs.sparse.img"
else
  echo "note: img2simg not found -> no sparse image"
fi
echo "Rembly rootfs image complete"
