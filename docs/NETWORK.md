# Сеть на A73: Wi-Fi, USB, Bluetooth, SIM

Порядок работ (как вы задали): **1) Wi-Fi → 2) Bluetooth → 3) Ethernet/USB-сеть → 4) только потом сотовая сеть.**

## Что на самом деле в ядре (по `kernel_config.txt`)
| | Факт | Следствие |
|---|---|---|
| Wi-Fi | `MTK_COMBO_WIFI=y`, `CFG80211=y`, комбо-чип в конфиге **`CONSYS_6735`** (встроен в SoC) | драйвер есть, оживает после загрузки прошивки через `wmt_launcher` |
| Чип | в конфиге MT6625 упомянут только как **FM** (`MT6625_FM`) | имена прошивок ждём вида `WMT_SOC.cfg`, `ROMv2_*`, `WIFI_RAM_CODE_soc*`, `mt6735*` (инструмент ищет и `mt6625*`) |
| Bluetooth | **`# CONFIG_BT is not set`**, `RFKILL` тоже нет | в ядре **нет Linux-стека Bluetooth** → BlueZ работать не может |
| USB-сеть | gadget: только `acm`, `mass_storage`, `ffs`(adb), `audio_source`; **RNDIS/ECM нет**; USB-Ethernet host-драйверов нет | сеть по USB только как PPP поверх виртуального COM-порта |
| Модем | `MTK_ECCCI/CCCI`, `MD1_SUPPORT=5`; PPP, TUN, NAT в ядре есть | сотовая связь — последним этапом, после Wi-Fi |

## Безопасность данных (жёсткие правила)
* `nvdata` монтируется **только на чтение** (`ro,noload` — без повторного проигрывания журнала): драйвер Wi-Fi читает стоковую
  калибровку и MAC из `/data/nvram/APCFG/APRDEB/WIFI` (симлинк на `/nvdata`).
* `nvram`, `protect1`, `protect2`, `secro`, `proinfo` не монтируются и не пишутся. **MAC/IMEI не генерируются и не хардкодятся.**
* `rembley-net mac` сравнивает MAC драйвера и запись в NVRAM; `rembley-report` сохраняет только **имена** файлов в `/nvdata`, не содержимое.
* Раздел nvdata находится по `PARTNAME=nvdata` в sysfs, а не по номеру.

## Шаг 1. Достать файлы из вашего `system.bin`/`vendor.bin` (на ПК, без root)
```
sudo apt install e2fsprogs android-sdk-libsparse-utils
tools/make-blobs.sh /home/tishir645/планшет           # папка с system.bin (+ vendor.bin)
git add -f out/android-blobs*; git commit -m "android blobs"; git push
```
Инструмент сначала печатает найденное (`--list`), затем собирает `out/android-blobs.tar.gz`: демоны `wmt_*`/`conn*`/`ccci*`..., прошивки,
**`.rc`-файлы запуска из `/vendor/etc/init` и `/system/etc/init`** (из них `rembley-net` берёт настоящую командную строку
`wmt_launcher`), fstab, и нужные bionic-библиотеки. Содержимое `nvram`/`nvdata` в архив **не** попадает.

## Шаг 2. Собрать образ
`sudo rootfs/build-rootfs.sh` (архив подхватывается сам).

## Шаг 3. На планшете
`rembley-net auto` при загрузке: подключает nvdata на чтение → линкует прошивки в `/etc/firmware` → запускает `wmt_loader`/`wmt_launcher`
(аргументы из stock `.rc`, иначе перебор `-p DIR`, `-m 1`, `-m 3`) → `echo 1 > /dev/wmtWifi` → `wlan0` → `wpa_supplicant` + DHCP.
Подключение: иконка Wi-Fi в трее (`rembley-netui`) или `rembley-net wifi-connect SSID ПАРОЛЬ`.
Диагностика: `rembley-net diag`, `rembley-net mac`, `/var/log/rembley-net.log`, `/var/log/wmt_launcher.log`, `rembley-report`.
Переопределения: `/etc/rembley/net.conf` (`WMT_ARGS="-p /vendor/firmware/ -m 3"`, `COUNTRY=RU`).

## USB-сеть к ПК (работает без Android-файлов)
Планшет: `rembley-net usb-ppp on` (или вкладка «USB» в окне сети; adb на секунду отключится). На ПК:
```
sudo pppd /dev/ttyACM0 115200 192.168.7.1:192.168.7.2 noauth local nodetach
ssh root@192.168.7.2
# интернет планшету через ПК (по желанию):
sudo sysctl net.ipv4.ip_forward=1; sudo iptables -t nat -A POSTROUTING -s 192.168.7.0/24 -j MASQUERADE
```
Альтернатива без PPP: `adb forward tcp:2222 tcp:22` и `adb reverse tcp:8080 tcp:8080`.

## Bluetooth: честно
Со стоковым ядром BlueZ невозможен. Варианты на будущее: (а) пользовательский стек (например BTstack) поверх `/dev/stpbt` + `uinput`
для клавиатур/мышей — реально, но отдельный проект; (б) собственное ядро с `CONFIG_BT` — вы просили этого пока не делать.
Сейчас клавиатуры/мыши работают по USB через OTG.

## SIM / мобильные данные (этап 4)
Прошивка модема `MOLY.LR9...` загружается Android-помощниками `ccci_*`; раздела `md1img` в вашем списке нет. `rembley-net modem-probe` покажет порты.
Не трогать `nvram/nvdata/protect1/protect2/secro` и не переносить IMEI вручную.
