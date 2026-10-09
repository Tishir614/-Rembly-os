#!/bin/sh
# systemd-udevd as a plain daemon (no systemd): gives Xorg/libinput device detection + USB hotplug.
mkdir -p /run/udev
ln -sf /bin/busybox /sbin/mdev 2>/dev/null
/lib/systemd/systemd-udevd --daemon 2>&1 || echo "udevd failed (X falls back to static input)"
udevadm trigger --type=subsystems --action=add 2>&1
udevadm trigger --type=devices --action=add 2>&1
udevadm settle --timeout=8 2>&1
