# Rembley OS for A73 (K37MV1_BSP, MT6737M)

Stock kernel 3.18.79 + appended DTB are kept untouched. Stage 1 = BusyBox initramfs in boot image
(`fastboot boot` only). Stage 2 = Alpine armv7 rootfs image found by label `REMBLEY`, or as
`/rembley-rootfs.img` on any mountable fs (SD, USB, f2fs userdata).

1. `build/build.sh boot.bin recovery.bin`  -> `out/A73-linux-test.img` (+ sha256, file list)
2. Test first that stock works: `fastboot boot boot.bin` (charge the battery first).
3. `fastboot boot out/A73-linux-test.img`. Expect noise on the panel, then adb / emergency shell.
   Run `hw` / `touchtest` and send back the report.
4. `sudo rootfs/build-rootfs.sh` -> `out/rembley-rootfs.img`.

Never use `fastboot flash/erase` with these images. Power off -> normal boot returns Android.

## Unverified assumptions (check on real hardware)
- USB gadget via `/sys/class/android_usb/android0` and a recovery `adbd` working outside recovery's init.
- `mdev -s` yields `/dev/fb0`, `/dev/input/event2`, `/dev/mmcblk0p*` on this kernel.
- Xorg fbdev may need the right `bits_per_pixel`; read `fb0.*` in the `hw` report.
- Wi-Fi/BT (MTK consys) are not handled in this stage.
