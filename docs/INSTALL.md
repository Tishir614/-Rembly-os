# Установка Rembly OS на A73

## Рекомендуемый способ: одна команда

После `git pull` подключите A73 к ПК по USB и запустите:

```bash
bash rembly-install.sh
```

Откроется цветная консоль Rembly OS. Установщик сам проверит или соберёт образы, найдёт планшет через ADB/Fastboot, проверит `K37MV1_BSP` и разблокированный bootloader, временно загрузит безопасную stage-1 среду, определит настоящие разделы по GPT, сделает резервную копию boot/recovery, запишет rootfs напрямую в настоящий `userdata`, проверит ext4/метку `REMBLY`, только после этого запишет boot и перезагрузит планшет. На первом запуске встроенный `rembly-autosetup` сам настраивает железо, память, экран, тач, драйверы, сеть и оптимизацию.

Этот путь специально не использует большой `fastboot flash userdata`: старый LK A73 неверно сообщает размер userdata и на большой sparse-записи может зависнуть. Размер раздела берётся из реальной GPT уже в stage-1. Старые установочные скрипты ниже сохранены без изменений. Подробности: `docs/ONE-COMMAND-INSTALL.md`.

Полная установка стирает `userdata`, но не пишет `preloader`, `lk`, `gpt`, `nvram`, `nvdata`, `protect*`, `secro`, `system` или `vendor`.

---

Три старых способа, от самого безопасного к постоянной установке. Прошивать вы начинаете **сами**; скрипты ничего не делают без проверок и подтверждения.

## 0. Подготовка (один раз)
* Резервная копия у вас уже есть (папка с `boot.bin`, `recovery.bin`, `system.bin`…). Скрипты установки **требуют** её и сверяют `boot.bin` с оригиналом.
* Загрузчик разблокирован (`fastboot getvar unlocked` → `yes`), планшет заряжен (иначе LK отвечает `low power, need battery charging`).
* На ПК: `sudo apt install android-tools-fastboot e2fsprogs android-sdk-libsparse-utils`.
* Образы: `python3 build/build.py boot.bin recovery.bin` (загрузочный) и `sudo rootfs/build-rootfs.sh` (rootfs). Результат в `out/`.

## 1. Только проверить — ничего не пишется
```
tools/flash-rembly.sh test --dir out
```
Делает `fastboot boot` и всё. Выключили питание — вернулся Android. Rootfs берётся с USB/SD (метка `REMBLY` или файл `/rembly-rootfs.img`).

## 2. Установка прямо на планшете (самый простой способ, без fastboot-прошивки 3,5 ГБ)
Загрузитесь способом 1 с флешки, затем **Настройки → Установка на планшет → «Установить во внутреннюю память»** (или `rembly-install-internal`).
Копируется работающая система в раздел `userdata` (ext4, метка `REMBLY`, на весь раздел сразу). Затёрт будет только `userdata`;
`system`, `vendor`, `boot`, `nvram`, `nvdata`, `protect*`, `secro` не затрагиваются. Прогресс виден в окне; ~10–30 минут, держите зарядку.
После этого флешка не нужна: `fastboot boot out/A73-linux-test.img` сам найдёт rootfs во внутренней памяти (внешние носители проверяются первыми).

## 3. Автоматическая прошивка (rootfs ставится сам)
```
# Linux рядом с Android (двойная загрузка): образ в recovery, rootfs в userdata. Android грузится как раньше.
tools/flash-rembly.sh install-recovery --dir out --backup-dir /home/tishir645/планшет

# Linux вместо Android по умолчанию: образ в boot, rootfs в userdata (Android вернуть командой restore-android.sh)
tools/flash-rembly.sh install-boot --dir out --backup-dir /home/tishir645/планшет
```
Скрипт сам: проверяет контрольные суммы образов и что это ext4 с меткой `REMBLY`; проверяет оригинальный `boot.bin` в вашей копии;
проверяет что `product = K37MV1_BSP`, загрузчик разблокирован и rootfs помещается в `userdata`; показывает план и просит набрать `INSTALL`;
затем `fastboot flash` и (для `install-boot`) перезагрузка. При первой загрузке файловая система сама **расширяется на весь раздел** (`01-expand.sh`).
`--dry-run` покажет все команды, ничего не выполняя.

**Жёсткая защита:** скрипт технически не умеет писать ничего, кроме `boot`, `recovery`, `userdata`
(`preloader`, `lk`, `gpt`, `nvram`, `nvdata`, `protect1/2`, `secro`, `proinfo`, `system`, `vendor` отклоняются кодом).

Как запускать Linux в режиме `install-recovery`: через вход в recovery (обычно Vol+ и Power при включении, либо меню LK). Точную комбинацию для этого
планшета я не знаю — проверьте. Если не выходит, `fastboot boot out/A73-linux-test.img` работает всегда и rootfs уже будет во внутренней памяти.

## Драйверы Wi-Fi при установке
Отдельно скачивать ничего не нужно: при первом запуске (и перед установкой во внутреннюю память) система сама берёт файлы Wi-Fi из разделов Android на планшете
(`rembly-drivers`, только чтение). Хотите вшить их в образ заранее: `ANDROID_DUMP=/home/tishir645/планшет sudo -E rootfs/build-rootfs.sh`.
Скрипт прошивки скажет, есть ли они в образе. Подробнее: `docs/NETWORK.md`.

## Откат на Android
```
tools/restore-android.sh --backup-dir /home/tishir645/планшет                    # вернуть boot и recovery
tools/restore-android.sh --backup-dir /home/tishir645/планшет --format-userdata  # + стереть userdata (Android сам отформатирует)
```
Если планшет вообще не стартует: `fastboot flash boot boot.bin`, `fastboot flash recovery recovery.bin` вручную, либо через mtkclient (preloader не трогаем, он цел).

## Что я проверил, а что нет
Проверено на подставном `fastboot`: последовательность команд, отказы (чужое устройство, закрытый загрузчик, нет бэкапа, чужой `boot.bin`,
rootfs больше раздела, неверное подтверждение, запрещённые разделы), `--dry-run`. Установщик во внутреннюю память проверен на блочном
(loop) устройстве: форматирование, копирование, `e2fsck`, метка. **Не проверено на самом планшете:** реальная запись `fastboot flash`,
как LK обрабатывает большой образ, комбинация клавиш входа в recovery, онлайн-расширение ext4 на ядре планшета.

## Важно: метка раздела теперь REMBLY (0.25)
После переименования проекта в **Rembly OS** метка файловой системы с ОС — `REMBLY`, команды называются `rembly-*`, каталоги — `/etc/rembly`, `/usr/share/rembly` и т. д. Образы, собранные раньше (метка `REMBLEY`), новым загрузочным образом не находятся: пересоберите и загрузочный образ, и rootfs (`python3 build/build.py boot.bin recovery.bin`, затем `sudo rootfs/build-rootfs.sh`) или поменяйте метку: `e2label /dev/XXX REMBLY`.
