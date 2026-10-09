#!/usr/bin/env bash
# Stage 2: Rembly OS rootfs (Ubuntu 20.04 "focal" armhf, no systemd as PID 1) -> ext4 image labelled REMBLY.
# Run as root on an x86-64 Ubuntu/Debian PC:  sudo rootfs/build-rootfs.sh [size_MiB] [minimal|desktop]
# Needs: debootstrap qemu-user-static e2fsprogs (binfmt_misc enabled).
set -euo pipefail
SIZE=${1:-3584}; PROFILE=${2:-desktop}
HERE=$(cd "$(dirname "$0")/.." && pwd); OUT=$HERE/out; R=${ROOTFS_DIR:-/var/rembly/rootfs}
MIRROR=${MIRROR:-https://ports.ubuntu.com/ubuntu-ports}
mkdir -p "$OUT" "$(dirname "$R")"

# Wi-Fi/BT helper files: if you point ANDROID_DUMP at your backup folder (system.bin + vendor.bin) they are extracted automatically.
#   ANDROID_DUMP=/home/you/backup sudo -E rootfs/build-rootfs.sh        (REFRESH_BLOBS=1 to redo it)
# Without it the image still works: on first boot the tablet takes them from its OWN Android partitions (rembly-drivers).
if [ -n "${ANDROID_DUMP:-}" ] && { [ ! -f "$OUT/android-blobs.tar.gz" ] || [ -n "${REFRESH_BLOBS:-}" ]; }; then
  [ -f "$ANDROID_DUMP/system.bin" ] || { echo "ANDROID_DUMP=$ANDROID_DUMP has no system.bin" >&2; exit 1; }
  vend=(); [ -f "$ANDROID_DUMP/vendor.bin" ] && vend=("$ANDROID_DUMP/vendor.bin")
  echo "== extracting Wi-Fi/BT files from $ANDROID_DUMP"
  python3 "$HERE/tools/extract_android_blobs.py" "$ANDROID_DUMP/system.bin" "${vend[@]}" -o "$OUT/android-blobs.tar.gz"
fi
# qemu-user must be registered for armhf binaries on every run (it is lost after reboot)
[ -e /proc/sys/fs/binfmt_misc/qemu-arm ] || { mountpoint -q /proc/sys/fs/binfmt_misc || mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
  head -1 /usr/lib/binfmt.d/qemu-arm.conf > /proc/sys/fs/binfmt_misc/register; }
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
# keep maintainer scripts from trying to start services in the chroot
printf '#!/bin/sh\nexit 101\n' > "$R/usr/sbin/policy-rc.d"; chmod +x "$R/usr/sbin/policy-rc.d"

PKGS_MIN="git python3 python3-pip python3-venv build-essential cmake make gdb nodejs wget curl htop tmux vim-tiny rsync zip unzip \
 openssh-client neofetch bluez usbutils net-tools wpasupplicant iw rfkill ppp wireless-tools earlyoom \
 tzdata locales ncdu mc alsa-utils strace"
# Light desktop: Xorg + xfwm4 (no compositor) + our own GTK shell instead of full XFCE session/panel/xfdesktop.
PKGS_DESK="xserver-xorg-core xdotool ntfs-3g exfat-fuse exfat-utils xserver-xorg-video-fbdev xserver-xorg-input-libinput xinit x11-xserver-utils x11-utils xinput unclutter \
 xfwm4 xfce4-settings xfce4-terminal xfce4-taskmanager xfce4-appfinder thunar mousepad dbus-x11 \
 python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-pil wmctrl playerctl onboard \
 fonts-noto-core fonts-dejavu-core papirus-icon-theme adwaita-icon-theme gtk2-engines-pixbuf \
 libglib2.0-bin qt5-gtk-platformtheme libfuse2 squashfs-tools desktop-file-utils shared-mime-info netsurf-gtk geany galculator mpv atril file-roller \
 gir1.2-gtksource-4 gir1.2-vte-2.91 python3-mutagen \
 dunst libnotify-bin xprintidle scrot x11-xkb-utils xdg-utils fonts-firacode"
chroot "$R" /usr/bin/env DEBIAN_FRONTEND=noninteractive sh -ec "
  apt-get update
  apt-get install -y --no-install-recommends $PKGS_MIN $( [ "$PROFILE" = desktop ] && echo "$PKGS_DESK" )
  # 0.28: Rembly Player replaced audacious and gpicview; a tree built by an older version still has them (and their libraries)
  apt-get purge -y audacious gpicview >/dev/null 2>&1 || true; apt-get autoremove --purge -y >/dev/null 2>&1 || true
  for l in ru_RU.UTF-8 en_US.UTF-8; do locale-gen \$l >/dev/null 2>&1 || true; done; update-locale LANG=ru_RU.UTF-8 2>/dev/null || true
  ln -sf /usr/share/zoneinfo/UTC /etc/localtime; echo UTC > /etc/timezone
  echo root:rembly | chpasswd
  ssh-keygen -A
  apt-get clean; rm -rf /var/lib/apt/lists/*"
rm -f "$R/usr/sbin/policy-rc.d"

# overlay LAST so our /sbin/init replaces systemd's
find "$HERE/rootfs/overlay" -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null   # never ship the host's bytecode
rm -f "$R/usr/sbin/init" "$R/sbin/init"   # was a symlink to systemd; never write through it
cp -a --remove-destination "$HERE/rootfs/overlay/." "$R/"
chroot "$R" glib-compile-schemas --strict /usr/share/glib-2.0/schemas
chroot "$R" sh -c "update-desktop-database /usr/share/applications; update-mime-database /usr/share/mime" >/dev/null 2>&1 || true   # Onboard auto-show + docking defaults (99_rembly override)
rm -f "$R/etc/X11/xorg.conf.d/20-touch.conf" "$R/etc/X11/xorg.conf.d/10-fbdev.conf"   # superseded by files generated at session start
mkdir -p "$R/system/bin" "$R/var/log" "$R/run/user" "$R/root/Projects"
ln -sf /bin/busybox "$R/sbin/mdev"
if [ -f "$OUT/android-blobs.tar.gz" ]; then      # Wi-Fi/BT/modem blobs from the user's own firmware (tools/extract_android_blobs.py)
  echo "== adding android blobs"; tar -xzf "$OUT/android-blobs.tar.gz" -C "$R"
else echo "NOTE: no android-blobs.tar.gz in the image: on first boot the tablet fetches the Wi-Fi/BT files from its own Android partitions (rembly-drivers). To bake them in: ANDROID_DUMP=<backup folder> sudo -E rootfs/build-rootfs.sh"; fi
ln -sf /bin/sh "$R/system/bin/sh"        # adbd (started by stage 1) expects /system/bin/sh
chroot "$R" python3 -m compileall -q /usr/local/lib/rembly     # cached .pyc: faster desktop start on the slow CPU
date +%s > "$R/etc/rembly/buildtime"
# what a COMPLETE install looks like: rembly-repair compares the running system with this at every login and fetches what is missing
python3 "$HERE/rootfs/overlay/usr/local/bin/rembly-repair" manifest "$HERE/rootfs/overlay" > "$R/usr/share/rembly/MANIFEST.sha256"
printf '%s\n' $PKGS_MIN $( [ "$PROFILE" = desktop ] && echo "$PKGS_DESK" ) | sort -u > "$R/usr/share/rembly/packages.txt"
chmod +x "$R/usr/sbin/init" "$R"/usr/local/bin/rembly-* "$R"/etc/rembly/rc.d/*.sh "$R/etc/rembly/udhcpc.script"; [ -e "$R/sbin/init" ] || ln -s /usr/sbin/init "$R/sbin/init"
cleanup; trap - EXIT

echo "== packing ext4 image (${SIZE} MiB, label REMBLY)"
IMG=$OUT/rembly-rootfs.img
rm -f "$IMG"; truncate -s "${SIZE}M" "$IMG"
mke2fs -q -t ext4 -L REMBLY -d "$R" -F "$IMG"
du -sh "$R"; ls -lh "$IMG"; sha256sum "$IMG" | tee "$IMG.sha256"
# sparse copy: fastboot flashes it much faster (only the used blocks are sent)
if command -v img2simg >/dev/null; then img2simg "$IMG" "$OUT/rembly-rootfs.sparse.img" && ls -lh "$OUT/rembly-rootfs.sparse.img"; else echo "note: img2simg not found (sudo apt install android-sdk-libsparse-utils) -> no sparse image, fastboot will use the raw one"; fi
echo "Copy to SD/USB as a REMBLY-labelled ext4 partition, or put on any fs as /rembly-rootfs.img"
