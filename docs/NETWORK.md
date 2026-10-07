# Wi-Fi, Bluetooth and SIM on the A73

The tablet's radios are a MediaTek MT6735 "CONSYS" combo chip (Wi-Fi + BT + GPS) and a MediaTek modem.
The Linux kernel 3.18.79 on the device already contains the drivers (`MTK_COMBO_WIFI/BT=y`, `CCCI/ECCCI`),
but they only come alive after Android userspace helpers load the firmware: `wmt_loader`, `wmt_launcher`,
(for the modem `ccci_*`/`rild`-style helpers). Those helpers and firmware are proprietary files that live in
**your** `system.bin` / `vendor.bin`, so they are not shipped here.

## 1. Extract them from your own dump (on your PC, no root, nothing is modified)
```
sudo apt install e2fsprogs android-sdk-libsparse-utils      # debugfs, simg2img
python3 tools/extract_android_blobs.py /home/tishir645/планшет/system.bin /home/tishir645/планшет/vendor.bin
# -> out/android-blobs.tar.gz   (binaries, firmware, bionic libs they need; typically 5-30 MB)
```
## 2. Build the rootfs (it picks the tarball up automatically)
`sudo rootfs/build-rootfs.sh`

## 3. On the tablet
`rembley-net auto` runs at boot: loads firmware, creates `wlan0` (`echo 1 > /dev/wmtWifi`), starts
`wpa_supplicant`, DHCP for saved networks, and `btattach /dev/stpbt` + `bluetoothd`.
Tap the Wi-Fi / Bluetooth / SIM icons in the bottom-right tray (`rembley-netui`) to scan and connect.
Logs: `/var/log/rembley-net.log`, `/var/log/wmt_launcher.log`, `dmesg | grep -i -E 'wmt|wlan|conn'`.
Advanced overrides go in `/etc/rembley/net.conf` (`WMT_ARGS="-p /vendor/firmware -m 1"`, `COUNTRY=RU`, `WIFI_IF=wlan0`).

## Honest status
* Nothing in this chain has run on the real tablet yet. The Android helpers run on glibc Linux through
  `/system/bin/linker` plus the extracted bionic libs - that normally works for simple daemons but is the
  most likely place to need a fix (send `/var/log/*` and `dmesg` back).
* Wi-Fi MAC comes from the `nvdata`/`nvram` partitions on Android; without the nvram daemon the driver uses a
  default/random MAC. Fine for normal networks.
* **SIM / mobile data:** the kernel has the modem driver, but the modem firmware is normally loaded by
  Android's `ccci_*` helpers, and there is **no `md1img` partition in your list**, so I cannot tell whether
  this unit has a working modem at all. `rembley-net modem-probe` shows what exists. If an AT port appears,
  `rembley-net modem-up` (APN from `/etc/rembley/modem.conf`) tries PPP data. Treat this as experimental;
  do not count on it until probe output shows a port.
* USB tethering / USB Ethernet are impossible: the kernel has no RNDIS/CDC-ethernet host drivers.
