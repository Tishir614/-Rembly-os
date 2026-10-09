#!/usr/bin/env bash
# Rembly OS one-command installer for the A73 (K37MV1_BSP / MT6737M).
# Keeps the existing flash-rembly.sh untouched. It temporarily boots the verified
# stage-1 image, then writes only userdata and boot from stage-1 over ADB.
# This avoids the A73 LK bug that reports userdata incorrectly and can hang on
# multi-gigabyte fastboot writes.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
OUT="$ROOT/out"
BOOTIMG="$OUT/A73-linux-test.img"
ROOTFS="$OUT/rembly-rootfs.img"
EXPECTED_PRODUCT=K37MV1_BSP
EXPECTED_STOCK_BOOT_SHA=a94d3f8a18d626d0e12c3c1fe0848076a5c7754f2f108f727a9a21249a3483f4
REBUILD=0
REUSE=0
WAIT_SECONDS=${REMBLY_WAIT_SECONDS:-180}

for a in "$@"; do
  case "$a" in
    --rebuild) REBUILD=1 ;;
    --reuse-images) REUSE=1 ;;
    -h|--help)
      cat <<'H'
Rembly OS one-command installer

  bash rembly-install.sh
  bash rembly-install.sh --rebuild
  bash rembly-install.sh --reuse-images

Full install erases userdata. Only boot and userdata are written.
H
      exit 0 ;;
    *) printf 'Unknown option: %s\n' "$a" >&2; exit 2 ;;
  esac
done

if [[ -t 1 ]]; then
  R=$'\033[1;31m'; M=$'\033[1;35m'; C=$'\033[1;36m'; G=$'\033[1;32m'; Y=$'\033[1;33m'; W=$'\033[1;37m'; D=$'\033[2m'; N=$'\033[0m'
else R= M= C= G= Y= W= D= N=; fi

printf '\033]0;Rembly OS Installer\007' 2>/dev/null || true
banner() {
  printf '%s\n' "${M}╭────────────────────────────────────────────────────────────╮${N}"
  printf '%s\n' "${M}│${N}   ${W}REMBLY OS${N}  ${C}ONE-TOUCH INSTALLER${N}   ${D}A73 / MT6737M${N}   ${M}│${N}"
  printf '%s\n' "${M}╰────────────────────────────────────────────────────────────╯${N}"
}
step() { printf '\n%s◆ %s%s\n' "$C" "$*" "$N"; }
ok()   { printf '%s✓%s %s\n' "$G" "$N" "$*"; }
warn() { printf '%s!%s %s\n' "$Y" "$N" "$*"; }
die()  { printf '\n%s✗ %s%s\n' "$R" "$*" "$N" >&2; exit 1; }
sub()  { printf '  %s%s%s\n' "$D" "$*" "$N"; }

banner
printf '%s\n' "${W}Полная установка:${N} userdata будет заменён Rembly OS. Android-данные в userdata будут удалены."
printf '%s\n' "${G}Не изменяются:${N} preloader/lk/gpt/nvram/nvdata/protect*/secro/system/vendor."
[[ "$(uname -s)" == Linux ]] || die "Установщик рассчитан на Linux ПК."
mkdir -p "$OUT"

need_host_tools() {
  local missing=() c
  for c in adb fastboot python3 sha256sum git; do command -v "$c" >/dev/null 2>&1 || missing+=("$c"); done
  ((${#missing[@]}==0)) && return 0
  warn "Не хватает: ${missing[*]}. Пытаюсь установить автоматически."
  if command -v pacman >/dev/null 2>&1; then
    sudo -v; sudo pacman -S --needed --noconfirm android-tools python git
  elif command -v apt-get >/dev/null 2>&1; then
    sudo -v; sudo apt-get update; sudo apt-get install -y android-tools-adb android-tools-fastboot python3 git
  else
    die "Не удалось автоматически установить adb/fastboot/python/git."
  fi
  for c in adb fastboot python3 sha256sum git; do command -v "$c" >/dev/null 2>&1 || die "После установки не найден $c"; done
}

find_android_dump() {
  local p
  for p in "${REMBLY_ANDROID_DUMP:-}" "$HOME/планшет" "$HOME/tablet" "$ROOT/backup"; do
    [[ -n "$p" && -f "$p/system.bin" ]] && { printf '%s' "$p"; return 0; }
  done
  return 1
}

current_commit() { git -C "$ROOT" rev-parse HEAD 2>/dev/null || printf unknown; }

build_boot() {
  step "Собираю свежий загрузочный образ"
  [[ -f "$ROOT/boot.bin" && -f "$ROOT/recovery.bin" ]] || die "В репозитории нет boot.bin/recovery.bin"
  local got
  got=$(sha256sum "$ROOT/boot.bin" | awk '{print $1}')
  [[ "$got" == "$EXPECTED_STOCK_BOOT_SHA" ]] || die "boot.bin не совпадает с проверенным A73 stock boot ($got)"
  python3 "$ROOT/build/build.py" "$ROOT/boot.bin" "$ROOT/recovery.bin"
  [[ -s "$BOOTIMG" ]] || die "Сборка не создала $BOOTIMG"
  ok "Boot image готов: $(du -h "$BOOTIMG" | awk '{print $1}')"
}

build_rootfs_container() {
  command -v podman >/dev/null 2>&1 || {
    if command -v pacman >/dev/null 2>&1; then sudo -v; sudo pacman -S --needed --noconfirm podman
    elif command -v apt-get >/dev/null 2>&1; then sudo -v; sudo apt-get update; sudo apt-get install -y podman
    else die "Для автоматической сборки rootfs нужен Podman."; fi
  }
  sudo -v
  sudo mkdir -p /var/tmp/rembly-rootfs
  sudo rm -rf /var/tmp/rembly-rootfs/*
  local dump mount_dump=() env_dump=""
  if dump=$(find_android_dump); then
    mount_dump=(-v "$dump:/android-dump:ro")
    env_dump="ANDROID_DUMP=/android-dump"
    sub "Wi-Fi/BT файлы будут взяты из: $dump"
  else
    sub "Дамп Android не найден: драйверы будут подхвачены с system/vendor на первом запуске."
  fi
  sudo podman run --rm --privileged --network=host --security-opt label=disable \
    -v "$ROOT:/work" -v /var/tmp/rembly-rootfs:/var/rembly/rootfs "${mount_dump[@]}" \
    -w /work ubuntu:22.04 bash -lc "
      set -e
      apt-get update
      DEBIAN_FRONTEND=noninteractive apt-get install -y \
        debootstrap qemu-user-static binfmt-support e2fsprogs android-sdk-libsparse-utils \
        python3 file gzip cpio ca-certificates
      $env_dump rootfs/build-rootfs.sh 3584 desktop
    "
  sudo chown -R "$(id -u):$(id -g)" "$OUT"
}

build_rootfs() {
  step "Собираю Rembly OS rootfs"
  if [[ -f /etc/debian_version ]] && command -v debootstrap >/dev/null 2>&1 && command -v qemu-arm-static >/dev/null 2>&1; then
    local dump=""; dump=$(find_android_dump || true); sudo -v
    if [[ -n "$dump" ]]; then ANDROID_DUMP="$dump" sudo -E "$ROOT/rootfs/build-rootfs.sh" 3584 desktop
    else sudo "$ROOT/rootfs/build-rootfs.sh" 3584 desktop; fi
    sudo chown -R "$(id -u):$(id -g)" "$OUT"
  else
    build_rootfs_container
  fi
  [[ -s "$ROOTFS" ]] || die "Сборка не создала $ROOTFS"
  (cd "$OUT" && sha256sum rembly-rootfs.img > rembly-rootfs.img.sha256)
  current_commit > "$OUT/rembly-rootfs.commit"
  ok "Rootfs готов: $(du -h "$ROOTFS" | awk '{print $1}')"
}

ensure_images() {
  need_host_tools
  local commit marker="" bootmarker=""
  commit=$(current_commit)
  [[ -f "$OUT/rembly-rootfs.commit" ]] && marker=$(cat "$OUT/rembly-rootfs.commit" 2>/dev/null || true)
  [[ -f "$OUT/rembly-boot.commit" ]] && bootmarker=$(cat "$OUT/rembly-boot.commit" 2>/dev/null || true)

  if (( REBUILD )) || [[ ! -s "$BOOTIMG" ]] || { (( ! REUSE )) && [[ "$bootmarker" != "$commit" ]]; }; then
    build_boot; current_commit > "$OUT/rembly-boot.commit"
  else
    ok "Boot image найден"
  fi

  if (( REBUILD )) || [[ ! -s "$ROOTFS" ]]; then
    build_rootfs
  elif (( REUSE )); then
    warn "Использую существующий rootfs по запросу --reuse-images"
  elif [[ "$marker" != "$commit" ]]; then
    warn "Rootfs собран другой версией репозитория. Пересобираю."
    build_rootfs
  else
    ok "Rootfs соответствует текущему commit"
  fi

  local label bootsz rootsz
  label=$(dd if="$ROOTFS" bs=8 skip=143 count=2 2>/dev/null | tr -d '\000')
  [[ "$label" == REMBLY ]] || die "rootfs имеет метку '$label', ожидалась REMBLY"
  bootsz=$(stat -c %s "$BOOTIMG"); rootsz=$(stat -c %s "$ROOTFS")
  (( bootsz < 16*1024*1024 )) || die "boot image больше раздела boot"
  (( rootsz > 512*1024*1024 )) || die "rootfs выглядит подозрительно маленьким"
  ok "Образы проверены"
}

list_fastboot() { fastboot devices 2>/dev/null | awk 'NF{print $1}'; }
list_adb() { adb devices 2>/dev/null | awk '$2=="device"{print $1}'; }

wait_for_fastboot() {
  step "Ищу A73 по USB"
  adb start-server >/dev/null 2>&1 || true
  local start now adbdev
  start=$(date +%s)
  while :; do
    mapfile -t fbs < <(list_fastboot)
    if ((${#fbs[@]}==1)); then FB_SERIAL=${fbs[0]}; ok "Найден Fastboot: $FB_SERIAL"; return 0; fi
    ((${#fbs[@]}>1)) && die "Подключено несколько Fastboot-устройств. Оставь только A73."

    mapfile -t ads < <(list_adb)
    if ((${#ads[@]}==1)); then
      adbdev=${ads[0]}; ok "Найден Android по ADB: $adbdev"
      sub "Перевожу планшет в Fastboot автоматически…"
      adb -s "$adbdev" reboot bootloader || true; sleep 3; continue
    fi
    ((${#ads[@]}>1)) && die "Подключено несколько ADB-устройств. Оставь только A73."

    now=$(date +%s)
    (( now-start >= WAIT_SECONDS )) && die "A73 не появился в ADB/Fastboot за ${WAIT_SECONDS} с."
    if command -v lsusb >/dev/null 2>&1 && lsusb | grep -qiE '0e8d:201c|0e8d:2000|0bb4:0c01'; then
      printf '\r  %sA73 виден на USB, жду ADB/Fastboot…%s   ' "$Y" "$N"
    else
      printf '\r  %sПодключи A73 по USB…%s   ' "$D" "$N"
    fi
    sleep 2
  done
}

fbget() { fastboot -s "$FB_SERIAL" getvar "$1" 2>&1 | awk -F': +' -v k="$1" '$1==k {print $2; exit}'; }
verify_fastboot_device() {
  local prod unl; prod=$(fbget product); unl=$(fbget unlocked)
  [[ "$prod" == "$EXPECTED_PRODUCT" ]] || die "Найден '$prod', а нужен $EXPECTED_PRODUCT. Ничего не записано."
  [[ "$unl" == yes ]] || die "Bootloader закрыт (unlocked=$unl). Ничего не записано."
  ok "Устройство подтверждено: $prod, bootloader unlocked"
}

find_rembly_adb() {
  local start now s; start=$(date +%s)
  while :; do
    mapfile -t ads < <(list_adb)
    for s in "${ads[@]:-}"; do
      [[ -n "$s" ]] || continue
      if adb -s "$s" shell 'test -f /tmp/hwreport.txt && echo REMBLY_STAGE1' 2>/dev/null | grep -q REMBLY_STAGE1; then ADB_SERIAL=$s; return 0; fi
    done
    now=$(date +%s); (( now-start >= 60 )) && return 1
    printf '\r  %sЗагрузка временной среды Rembly…%s   ' "$C" "$N"; sleep 1
  done
}

remote_part() {
  local name=$1
  adb -s "$ADB_SERIAL" shell "for u in /sys/class/block/*/uevent; do grep -qx 'PARTNAME=$name' \"\$u\" 2>/dev/null && { d=\${u%/uevent}; echo /dev/\${d##*/}; break; }; done" 2>/dev/null | tr -d '\r'
}
remote_size_bytes() {
  local dev=$1 n=${dev##*/} sectors
  sectors=$(adb -s "$ADB_SERIAL" shell "cat /sys/class/block/$n/size" 2>/dev/null | tr -dc '0-9')
  [[ -n "$sectors" ]] || return 1; printf '%s' $((sectors * 512))
}

make_live_backup() {
  local bootdev=$1 recdev=$2 stamp bdir
  stamp=$(date +%Y%m%d-%H%M%S); bdir="$ROOT/backups/$stamp"; mkdir -p "$bdir"
  step "Делаю аварийную копию boot/recovery"
  adb -s "$ADB_SERIAL" exec-out "dd if=$bootdev bs=4096 2>/dev/null" > "$bdir/boot-current.bin"
  adb -s "$ADB_SERIAL" exec-out "dd if=$recdev bs=4096 2>/dev/null" > "$bdir/recovery-current.bin"
  cp -f "$ROOT/boot.bin" "$bdir/boot-stock.bin"; cp -f "$ROOT/recovery.bin" "$bdir/recovery-stock.bin"
  (cd "$bdir" && sha256sum *.bin > SHA256SUMS)
  printf '%s\n' "$bdir" > "$OUT/last-backup-dir.txt"
  ok "Резервная копия: $bdir"
}

stream_image() {
  local src=$1 dev=$2 title=$3 size; size=$(stat -c %s "$src")
  step "$title"; sub "$(basename "$src") → $dev"
  if command -v pv >/dev/null 2>&1; then
    pv -ptebar -s "$size" "$src" | adb -s "$ADB_SERIAL" shell -T "dd of=$dev bs=4M 2>/tmp/rembly-install-dd.log; rc=\$?; sync; exit \$rc"
  else
    dd if="$src" bs=4M status=progress | adb -s "$ADB_SERIAL" shell -T "dd of=$dev bs=4M 2>/tmp/rembly-install-dd.log; rc=\$?; sync; exit \$rc"
  fi
}

verify_rootfs_remote() {
  local dev=$1 label magic
  label=$(adb -s "$ADB_SERIAL" shell "dd if=$dev bs=8 skip=143 count=2 2>/dev/null | tr -d '\\000\\r\\n'" 2>/dev/null | tr -d '\r\n')
  magic=$(adb -s "$ADB_SERIAL" shell "dd if=$dev bs=1 skip=1080 count=2 2>/dev/null | od -An -tx1" 2>/dev/null | tr -d ' \r\n')
  [[ "$label" == REMBLY ]] || die "После записи userdata метка '$label', ожидалась REMBLY. Boot ещё не записан."
  [[ "$magic" == 53ef ]] || die "После записи userdata ext4 magic '$magic', ожидался 53ef. Boot ещё не записан."
  ok "Rootfs на userdata проверен: ext4 / REMBLY"
}

verify_boot_remote() {
  local dev=$1 size want got
  size=$(stat -c %s "$BOOTIMG"); want=$(sha256sum "$BOOTIMG" | awk '{print $1}')
  if adb -s "$ADB_SERIAL" exec-out "head -c $size $dev" > "$OUT/.boot-readback.bin" 2>/dev/null; then
    got=$(sha256sum "$OUT/.boot-readback.bin" | awk '{print $1}'); rm -f "$OUT/.boot-readback.bin"
    [[ "$got" == "$want" ]] || die "Проверка boot после записи не совпала ($got != $want)"
    ok "Boot проверен побайтно по SHA-256"
  else
    rm -f "$OUT/.boot-readback.bin"; warn "Не удалось прочитать boot обратно; запись завершилась без ошибки."
  fi
}

wait_for_full_os() {
  local start now s; start=$(date +%s)
  while :; do
    mapfile -t ads < <(list_adb)
    for s in "${ads[@]:-}"; do
      [[ -n "$s" ]] || continue
      if adb -s "$s" shell 'test -x /usr/local/bin/rembly-autosetup && echo REMBLY_OS' 2>/dev/null | grep -q REMBLY_OS; then ADB_SERIAL=$s; return 0; fi
    done
    now=$(date +%s); (( now-start >= WAIT_SECONDS )) && return 1
    printf '\r  %sПервый запуск Rembly OS, автонастройка железа…%s   ' "$M" "$N"; sleep 2
  done
}

install_now() {
  wait_for_fastboot; verify_fastboot_device
  printf '\n%s' "$Y"
  for n in 5 4 3 2 1; do printf '\rПолная установка начнётся через %s с. Ctrl+C отменяет… ' "$n"; sleep 1; done
  printf '\r%-72s\r%s' '' "$N"

  step "Запускаю безопасную временную среду Rembly"
  fastboot -s "$FB_SERIAL" boot "$BOOTIMG"
  find_rembly_adb || die "Stage-1 загрузился, но ADB Rembly не появился. Ничего ещё не записано."
  ok "Stage-1 ADB: $ADB_SERIAL"
  adb -s "$ADB_SERIAL" shell 'id' 2>/dev/null | grep -q 'uid=0' || die "Stage-1 ADB не root. Ничего не записано."

  local bootdev recdev userdev bootsize usersize need
  bootdev=$(remote_part boot); recdev=$(remote_part recovery); userdev=$(remote_part userdata)
  [[ -n "$bootdev" && -n "$recdev" && -n "$userdev" ]] || die "Не удалось найти boot/recovery/userdata по GPT. Ничего не записано."
  bootsize=$(remote_size_bytes "$bootdev"); usersize=$(remote_size_bytes "$userdev"); need=$(stat -c %s "$ROOTFS")
  (( bootsize >= $(stat -c %s "$BOOTIMG") )) || die "Boot image не помещается в $bootdev"
  (( usersize >= need )) || die "Rootfs не помещается в userdata: $need > $usersize"
  ok "GPT с планшета: boot=$((bootsize/1024/1024)) MiB, userdata=$((usersize/1024/1024)) MiB"
  sub "Размер берётся из реальной GPT, а не из ошибочного fastboot getvar userdata."

  make_live_backup "$bootdev" "$recdev"
  stream_image "$ROOTFS" "$userdev" "Устанавливаю файловую систему Rembly OS"
  verify_rootfs_remote "$userdev"
  stream_image "$BOOTIMG" "$bootdev" "Устанавливаю загрузчик Rembly OS"
  verify_boot_remote "$bootdev"

  step "Синхронизация и первый запуск"
  adb -s "$ADB_SERIAL" shell 'sync; reboot' >/dev/null 2>&1 || true; sleep 3
  if wait_for_full_os; then
    printf '\r%-72s\r' ''; ok "Rembly OS загрузилась"
    sub "Встроенная автонастройка уже запущена в фоне: железо, RAM, экран, тач, драйверы, сеть и оптимизация."
    adb -s "$ADB_SERIAL" shell 'rembly-autosetup status 2>/dev/null || true' 2>/dev/null | sed 's/^/  /' || true
    printf '\n%s╭──────────────────────────────────────────────╮%s\n' "$G" "$N"
    printf '%s│%s  %sREMBLY OS УСТАНОВЛЕНА И ЗАПУЩЕНА%s          %s│%s\n' "$G" "$N" "$W" "$N" "$G" "$N"
    printf '%s╰──────────────────────────────────────────────╯%s\n' "$G" "$N"
  else
    warn "Запись завершена, но рабочая ОС не появилась по ADB за ${WAIT_SECONDS} с."
    sub "Резервная копия указана в $OUT/last-backup-dir.txt"
  fi
}

ensure_images
install_now
