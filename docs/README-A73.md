# Rembly OS for A73 (K37MV1_BSP, MT6737M)

Stock kernel 3.18.79 + appended DTB are untouched. Nothing here flashes the device.

| Stage | What | Built by |
|---|---|---|
| 1 | BusyBox initramfs in the boot image: builds `/dev` (no devtmpfs), framebuffer test, adb (functionfs), finds rootfs, `switch_root` | `python3 build/build.py boot.bin recovery.bin` -> `out/A73-linux-test.img` |
| 2 | Ubuntu 20.04 armhf rootfs, own PID 1 (no systemd), Rembly desktop, dev tools | `sudo rootfs/build-rootfs.sh` -> `out/rembly-rootfs.img` (3.5 GiB ext4, label `REMBLY`) |
| 3 (optional) | Wi-Fi / BT / SIM blobs from your own firmware | `python3 tools/extract_android_blobs.py system.bin vendor.bin` (see `docs/NETWORK.md`) |

## Install (new)
Three ways, from safest: `tools/flash-rembly.sh test` (nothing written) → install from inside the running system (Settings → Установка на планшет) → automatic fastboot install `tools/flash-rembly.sh install-recovery|install-boot`. Full guide, rollback and what was/was not verified: **`docs/INSTALL.md`**.

## Run
1. Charge the tablet. Sanity check: `fastboot boot boot.bin` (stock must start Android).
2. Put `rembly-rootfs.img` on a USB stick / microSD, either as a partition labelled `REMBLY` or as a file
   `/rembly-rootfs.img` on a FAT32/ext4/f2fs volume (3.5 GiB fits FAT32). Use OTG for USB.
3. `fastboot boot out/A73-linux-test.img`  (temporary, power-off returns to Android).
4. Stage 1 prints noise on the panel, exposes `adb shell`; `hw` and `touchtest` give diagnostics. With the rootfs
   present it switches to stage 2. root password: `rembly`.

## The desktop (Rembly Shell, `rootfs/overlay/usr/local/bin/rembly-shell`)
Dark glass look modelled on the reference screenshot: left sidebar, app grid, projects, big clock, weather
(wttr.in, needs network), now-playing (playerctl), CPU/RAM/disk rings, sticky notes (opens the on-screen keyboard),
dock, 4 workspaces, tray with Wi-Fi/BT/SIM/battery/clock, power menu, full app launcher with search.
Replace the wallpaper by putting `wallpaper.png`/`.jpg` into `~/.config/rembly/` (the glass blur follows it);
city for weather in `~/.config/rembly/city`.
Landscape 1280x800 by default (panel is portrait). `rembly-rotate cw|ccw|ud|none` rotates screen + touch.
Apps: NetSurf, Thunar, terminal, Geany (IDE), Mousepad, calculator, mpv, audacious, image/PDF viewers,
task manager; dev: Python 3.8, GCC 9, G++, CMake, Make, GDB, Git, Node.js, SSH.

## Full user guide
`docs/USER-GUIDE.md` (Russian): quick settings, power key, lock PIN, store, console commands, troubleshooting. Missing features: `docs/ROADMAP.md`.

## Why it should stay smooth (2 GB RAM, Cortex-A53, software rendering)
No compositor and no animations; the "glass" is a blurred wallpaper copy painted once. Only xfwm4 + one
Python/GTK process run besides Xorg. zram swap (lz4, 70 % of RAM), tuned VM sysctls, `earlyoom` so memory
pressure kills a hog instead of freezing the tablet, interactive CPU governor (stock). Not installed on
purpose because this hardware cannot run them well: Blender, Steam, GIMP, VS Code, Firefox (snap-only on 20.04).

## Touch
`mtk-tpd` is handled by libinput with a transformation matrix matching the rotation; GTK scrolls with finger
drag (kinetic); buttons are >= 44 px; the on-screen keyboard (Onboard) pops up from notes/search/Wi-Fi password
fields or the dock keyboard button; the mouse cursor hides when idle. udev is started so USB keyboards/mice
hot-plug via OTG; if udev detection fails X restarts once in a static-input mode (no hot-plug).

## Kernel facts (from kernel_config.txt)
No DEVTMPFS/VT/namespaces/configfs-gadget, no USB ethernet/RNDIS, `USB_G_ANDROID` only (adb through functionfs),
HID + USB storage + vfat/ext4/f2fs present, ZRAM present, Mali GPU userspace blobs not used (fbdev).

## NOT verified on hardware
All of stage 2 was checked offline only: rootfs builds, armhf binaries run under qemu-user, the shell was rendered
and screenshotted on x86 Xvfb with the same GTK3 stack, scripts pass syntax checks. Unknown until a real boot:
`mdev`/udev producing `fb0`+`event2`, adb enumeration, Xorg fbdev without VT, framebuffer depth/rotation direction
(fix with `rembly-rotate`), touch feel, Wi-Fi/BT blobs (see docs/NETWORK.md), SIM.
