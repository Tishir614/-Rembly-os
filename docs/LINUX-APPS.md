# Linux-программы на Rembly OS

Под капотом — **Ubuntu 20.04 (focal) для armhf**: это обычный Linux-userland, поэтому подходят любые программы, собранные под
**32-битный ARM (armhf / ARMv7)**. Ядро планшета (стоковое 3.18.79) очень старое и урезанное, поэтому часть современных возможностей недоступна.
Проверить, что именно подойдёт, можно командой **`rembly-compat`** (Настройки → Разработка → «Какие Linux-программы запустятся?»).

## Что работает
| Способ | Как | Примечание |
|---|---|---|
| Репозиторий Ubuntu (десятки тысяч программ) | **Магазин** (`rembly-store`) или `rembly-pkg install ИМЯ` | перед установкой считается размер и проверяется свободное место; `--no-install-recommends` по умолчанию |
| Скачанный **.deb** | двойное нажатие в файловом менеджере или `rembly-install файл.deb` | зависимости подтягиваются сами; пакет для другой архитектуры отклоняется с объяснением |
| **AppImage** для ARM | двойное нажатие или `rembly-install файл.AppImage` | запускается без FUSE (распаковка «на лету»), появляется в «Приложениях» |
| Python / Node / GCC / Git / SSH | уже установлены | `pip install --user`, `python3 -m venv`, `cmake`, `make` (по умолчанию `-j2`) |
| GTK и Qt программы | через apt | Qt-программы подхватывают тёмную GTK-тему (`qt5-gtk-platformtheme`), масштаб берётся из DPI (140) |
| Java | `rembly-pkg install default-jre` | лимит кучи 768 МБ, чтобы не съесть ОЗУ |
| OpenGL | программно (Mesa llvmpipe, 2 потока) | 2D и лёгкая 3D — нормально; игры и Blender — нет |

Запуск из меню/дока/лаунчера идёт с **пониженным приоритетом** (nice +10, низкий приоритет диска): интерфейс (Xorg, оконный менеджер, оболочка,
клавиатура) всегда впереди, поэтому тяжёлая программа не «вешает» планшет. Если памяти меньше 200 МБ, появится предупреждение; `earlyoom`
закроет самую «жирную» программу до зависания, zram-swap сжимает память в 2–3 раза.

## Что НЕ работает (и почему)
* **Flatpak, Snap, Docker** — в ядре нет user/mount-namespaces (и overlayfs): `rembly-compat` покажет `[FAIL]`. Ставьте из apt.
* **Chromium / Electron** (VS Code, Discord, Chrome…) — песочница требует namespaces. Если очень нужно: `rembly-nosandbox ИМЯ` создаст запуск с `--no-sandbox`
  (без защиты браузера; программа тяжёлая для 2 ГБ). Firefox в Ubuntu 20.04 — snap-пакет, поэтому как обычный `apt install firefox` не подходит;
  из лёгких браузеров доступны NetSurf (в системе) и Epiphany (`rembly-pkg install epiphany-browser`).
* **Программы x86 / x86-64 / AArch64, Windows (Wine)** — процессор 32-битный ARM; в ядре нет `binfmt_misc`, поэтому прозрачная эмуляция (qemu-user) невозможна.
* **3D-игры, видеомонтаж, Blender, Steam** — нет GPU-ускорения (используется простой framebuffer), 2 ГБ ОЗУ.
* AppImage/Deb для **другой архитектуры** — `rembly-install` сразу скажет, какая нужна.

## Как найти программу под ARM
В Магазине есть поиск по всему Ubuntu. В интернете ищите «armhf», «ARMv7», «Raspberry Pi 32-bit» (Raspberry Pi OS 32-bit совместим по архитектуре).
Пакеты для **arm64** не подойдут: ядро и userland здесь 32-битные.

## Команды
`rembly-pkg search|info|size|install|remove|update|upgrade|list|which|clean`, `rembly-install FILE`, `rembly-appimage FILE`, `rembly-nosandbox ИМЯ`, `rembly-compat`.
Ассоциации файлов (`~/.config/mimeapps.list`): текст → Mousepad, код → Geany, PDF → Atril, фото → GPicView, видео → mpv, музыка → Audacious,
ссылки → NetSurf, `.deb`/`.AppImage` → установщик.
