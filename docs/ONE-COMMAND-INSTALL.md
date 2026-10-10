# Установка Rembly OS одной командой

Для A73 / `K37MV1_BSP` основной установщик теперь работает напрямую через Fastboot. Временная stage-1 среда больше не используется.

После обновления репозитория запускается одна команда:

```bash
bash rembly-install.sh
```

Установщик работает автоматически:

1. Проверяет `adb`, `fastboot`, Python и инструменты сборки. На Arch/Ubuntu недостающие пакеты пытается установить сам.
2. Скачивает и кеширует исходники Linux 3.18 для `K37MV1_BSP` и ARM EABI GCC 4.8.
3. Берёт `kernel_config.txt` с реального планшета и включает `CONFIG_VT`, `CONFIG_VT_CONSOLE`, `CONFIG_HW_CONSOLE` и `CONFIG_FRAMEBUFFER_CONSOLE`.
4. Собирает новый `zImage`, затем объединяет его с точным DTB из проверенного stock `boot.bin`. Поэтому device tree планшета не заменяется чужим.
5. Собирает `A73-linux-test.img` и актуальный `rembly-rootfs.img`.
6. Если планшет уже работает по ADB, сравнивает текущий Rembly rootfs и boot с новыми данными. Совпадающие разделы не прошиваются повторно.
7. Если планшет уже находится в Fastboot, используется локальная запись последней успешной установки для этого серийного номера. Если хэши совпадают, повторная запись пропускается.
8. Проверяет `product = K37MV1_BSP` и `unlocked = yes`.
9. Если rootfs изменился, стирает только `userdata` и прошивает sparse-образ частями по 32 MiB. Известное ошибочное значение `partition-size:userdata` старого LK не используется.
10. `boot` прошивается последним и только если его SHA-256 изменился.
11. `preloader`, `lk`, `gpt`, `nvram`, `nvdata`, `protect*`, `secro`, `system` и `vendor` не записываются.

## Почему повторная установка не нужна

Новые rootfs содержат `/etc/rembly/image-id` и `/etc/rembly/buildtime`. Если Rembly уже загружена и доступна по ADB, установщик сравнивает эти значения и SHA-256 текущего boot.

Для запуска прямо из Fastboot успешные установки сохраняются локально в:

```text
~/.cache/rembly/install-state/<FASTBOOT_SERIAL>.state
```

Если на этом же ПК те же `userdata` и `boot` уже были успешно записаны, установщик не стирает и не пишет их ещё раз.

Если устройство было изменено вручную вне установщика, для гарантированной полной повторной записи можно использовать:

```bash
bash rembly-install.sh --force
```

## Сборка ядра

Исходники кешируются в:

```text
~/.cache/rembly-kernel/orangepi-bsp
~/.cache/rembly-kernel/arm-eabi-4.8
```

Собранное VT-ядро сохраняется как:

```text
out/rembly-kernel-vt.zImage
```

Boot image:

```text
out/A73-linux-test.img
```

Полная пересборка ядра, boot и rootfs:

```bash
bash rembly-install.sh --rebuild
```

Использовать существующий rootfs, не пересобирая его из-за изменения исходников:

```bash
bash rembly-install.sh --reuse-images
```

## Защита при ошибке

`boot` всегда записывается после `userdata`. Если большая Fastboot-запись `userdata` упадёт, в том числе с `low power, need battery charging`, новый boot не записывается.

Если до перехода в Fastboot планшет доступен по root ADB, установщик также пытается сохранить текущие `boot` и `recovery` в:

```text
backups/YYYYMMDD-HHMMSS/
```

Прямой Fastboot сам по себе не умеет надёжно читать эти разделы на старом LK, поэтому при запуске уже из Fastboot live-backup может быть недоступен.
