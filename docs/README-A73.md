# Rembley OS for A73 (K37MV1_BSP, MT6737M)

Stock kernel 3.18.79 + appended DTB are untouched. Nothing here flashes the device.

| Stage | What | Built by |
|---|---|---|
| 1 | BusyBox initramfs in the boot image: builds `/dev` (no devtmpfs), framebuffer test, adb (functionfs), finds rootfs, `switch_root` | `python3 build/build.py boot.bin recovery.bin` -> `out/A73-linux-test.img` |
| 2 | Ubuntu 20.04 armhf rootfs, own PID 1 (no systemd: no cgroups/devtmpfs on 3.18), Xorg fbdev + XFCE, onboard keyboard, Python/GCC/CMake/Git, NetSurf | `sudo rootfs/build-rootfs.sh` -> `out/rembley-rootfs.img` (3 GiB ext4, label `REMBLEY`) |

## Run
1. Charge the tablet. Sanity check: `fastboot boot boot.bin` (stock must start Android).
2. Put `rembley-rootfs.img` on a USB stick / microSD, either as a partition labelled `REMBLEY` or as a file
   `/rembley-rootfs.img` on a FAT32/ext4/f2fs volume (3 GiB fits FAT32). Use OTG for USB.
3. `fastboot boot out/A73-linux-test.img`  (temporary, power-off returns to Android).
4. Stage 1 prints noise on the panel, exposes `adb shell`; `hw` and `touchtest` give diagnostics. With the rootfs
   present it switches to stage 2, which starts Xorg on `/dev/graphics/fb0` and XFCE. root password: `rembley`.

## Kernel facts (from kernel_config.txt)
No DEVTMPFS/VT/namespaces/configfs-gadget, no USB ethernet/RNDIS drivers, `USB_G_ANDROID` only (adb through
functionfs), HID + USB storage + vfat/ext4/f2fs present, Wi-Fi/BT are the MTK CONSYS combo chip (needs vendor
firmware + userspace launcher, not done), GPU is Mali Midgard (userspace blobs from Android vendor, not used: fbdev).
So there is no network in this version; use USB keyboard/mouse via OTG.

## NOT verified on hardware
Everything in the initramfs/rootfs boot path has only been checked offline (image structure, sizes, armhf
binaries under qemu-user, script syntax, input-config generator). Unknowns: mdev creating fb0/event2, adb enumeration,
Xorg fbdev without VT (flags `-novtswitch -sharevts -keeptty`), fb colour depth, touch calibration/rotation, battery/charging.
