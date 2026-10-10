#!/usr/bin/env bash
# Rembly OS one-command installer for A73 / K37MV1_BSP / MT6737M.
# Direct install only: no temporary fastboot boot and no stage-1 installer mode.
# It builds a VT-capable kernel, compares what is already installed when possible,
# and flashes only partitions whose desired data changed.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
OUT="$ROOT/out"
BOOTIMG="$OUT/A73-linux-test.img"
ROOTFS="$OUT/rembly-rootfs.img"
SPARSE="$OUT/rembly-rootfs.sparse.img"
KERNEL_IMG="$OUT/rembly-kernel-vt.zImage"
EXPECTED_PRODUCT=K37MV1_BSP
EXPECTED_STOCK_BOOT_SHA=a94d3f8a18d626d0e12c3c1fe0848076a5c7754f2f108f727a9a21249a3483f4
WAIT_SECONDS=${REMBLY_WAIT_SECONDS:-0}
[[ "$WAIT_SECONDS" =~ ^[0-9]+$ ]] || { echo "REMBLY_WAIT_SECONDS must be a nonnegative integer" >&2; exit 2; }
WAIT_SECONDS=$((10#$WAIT_SECONDS))
REBUILD=0
REUSE=0
FORCE=0

for a in "$@"; do
  case "$a" in
    --rebuild) REBUILD=1 ;;
    --reuse-images) REUSE=1 ;;
    --force) FORCE=1 ;;
    -h|--help)
      cat <<'H'
Rembly OS direct Fastboot installer

  bash rembly-install.sh
  bash rembly-install.sh --rebuild
  bash rembly-install.sh --reuse-images
  bash rembly-install.sh --force

Default behaviour:
  * build/check VT-capable boot and current rootfs
  * continuously detect ADB/recovery or Fastboot, including late USB connections
  * automatically request bootloader mode from an identified A73
  * wait without questions (REMBLY_WAIT_SECONDS=0 means no deadline)
  * compare installed Rembly build when ADB is available
  * use the local successful-install record when the tablet is already in Fastboot
  * skip userdata or boot when the same data is already installed
  * flash changed userdata directly through Fastboot sparse chunks
  * flash boot last

No temporary stage-1 boot is used.
H
      exit 0 ;;
    *) printf 'Unknown option: %s\n' "$a" >&2; exit 2 ;;
  esac
done

if [[ -f "$ROOT/tools/rembly-installer-ui.sh" ]]; then
  # shellcheck source=/dev/null
  . "$ROOT/tools/rembly-installer-ui.sh"
  rembly_ui_start
else
  R= M= C= G= Y= W= D= N=
  banner() { printf 'REMBLY OS DIRECT FASTBOOT INSTALLER\n'; }
  step() { printf '\n== %s ==\n' "$*"; }
  ok() { printf '[OK] %s\n' "$*"; }
  warn() { printf '[WARN] %s\n' "$*"; }
  sub() { printf '  %s\n' "$*"; }
  die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }
  banner
fi

[[ "$(uname -s)" == Linux ]] || die "Установщик рассчитан на Linux ПК."
mkdir -p "$OUT"

need_host_tools() {
  local missing=() c
  for c in adb fastboot timeout python3 sha256sum git make bc perl flex bison; do
    command -v "$c" >/dev/null 2>&1 || missing+=("$c")
  done
  if ((${#missing[@]})); then
    warn "Не хватает инструментов: ${missing[*]}. Устанавливаю автоматически."
    if command -v pacman >/dev/null 2>&1; then
      sudo -v
      sudo pacman -S --needed --noconfirm android-tools python git base-devel bc perl flex bison openssl ncurses e2fsprogs
    elif command -v apt-get >/dev/null 2>&1; then
      sudo -v
      sudo apt-get update
      sudo apt-get install -y android-tools-adb android-tools-fastboot python3 git build-essential bc perl flex bison libssl-dev libncurses-dev e2fsprogs
    else
      die "Не удалось автоматически установить инструменты сборки."
    fi
  fi
  for c in adb fastboot timeout python3 sha256sum git make bc perl flex bison; do
    command -v "$c" >/dev/null 2>&1 || die "После установки не найден $c"
  done
}

find_android_dump() {
  local p
  for p in "${REMBLY_ANDROID_DUMP:-}" "$HOME/планшет" "$HOME/tablet" "$ROOT/backup"; do
    [[ -n "$p" && -f "$p/system.bin" ]] && { printf '%s' "$p"; return 0; }
  done
  return 1
}

hash_tree() {
  local dir=$1
  (
    cd "$ROOT"
    if [[ -d "$dir" ]]; then
      while IFS= read -r -d '' f; do sha256sum "$f"; done < <(find "$dir" -type f -print0 | sort -z)
    fi
  ) | sha256sum | awk '{print $1}'
}

rootfs_source_id() {
  {
    printf 'rootfs-tree=%s\n' "$(hash_tree rootfs)"
    printf 'profile=desktop\nsize=3584\n'
  } | sha256sum | awk '{print $1}'
}

boot_source_id() {
  {
    printf 'kernel=%s\n' "$(sha256sum "$KERNEL_IMG" | awk '{print $1}')"
    printf 'initramfs=%s\n' "$(hash_tree initramfs)"
    printf 'builder=%s\n' "$(sha256sum "$ROOT/build/build.py" | awk '{print $1}')"
    printf 'boot=%s\n' "$(sha256sum "$ROOT/boot.bin" | awk '{print $1}')"
    printf 'recovery=%s\n' "$(sha256sum "$ROOT/recovery.bin" | awk '{print $1}')"
  } | sha256sum | awk '{print $1}'
}

build_kernel() {
  step "Проверяю VT-ядро K37MV1_BSP"
  local args=()
  (( REBUILD )) && args+=(--rebuild)
  bash "$ROOT/build/build-kernel-vt.sh" "${args[@]}"
  [[ -s "$KERNEL_IMG" ]] || die "Сборка ядра не создала $KERNEL_IMG"
  ok "VT-ядро готово: $(du -h "$KERNEL_IMG" | awk '{print $1}')"
}

build_boot() {
  step "Собираю загрузочный образ Rembly"
  [[ -f "$ROOT/boot.bin" && -f "$ROOT/recovery.bin" ]] || die "В репозитории нет boot.bin/recovery.bin"
  local got wanted marker=""
  got=$(sha256sum "$ROOT/boot.bin" | awk '{print $1}')
  [[ "$got" == "$EXPECTED_STOCK_BOOT_SHA" ]] || die "boot.bin не совпадает с проверенным A73 stock boot ($got)"
  wanted=$(boot_source_id)
  [[ -f "$OUT/rembly-boot.source-id" ]] && marker=$(cat "$OUT/rembly-boot.source-id" 2>/dev/null || true)
  if (( ! REBUILD )) && [[ -s "$BOOTIMG" && "$marker" == "$wanted" ]]; then
    ok "Boot уже собран из этих же данных"
    return 0
  fi
  python3 "$ROOT/build/build.py" "$ROOT/boot.bin" "$ROOT/recovery.bin" --kernel-zimage "$KERNEL_IMG"
  [[ -s "$BOOTIMG" ]] || die "Сборка не создала $BOOTIMG"
  printf '%s\n' "$wanted" > "$OUT/rembly-boot.source-id"
  ok "Boot готов: $(du -h "$BOOTIMG" | awk '{print $1}')"
}

build_rootfs_container() {
  command -v podman >/dev/null 2>&1 || {
    if command -v pacman >/dev/null 2>&1; then sudo -v; sudo pacman -S --needed --noconfirm podman
    elif command -v apt-get >/dev/null 2>&1; then sudo -v; sudo apt-get update; sudo apt-get install -y podman
    else die "Для автоматической сборки rootfs нужен Podman."; fi
  }
  sudo -v
  sudo mkdir -p /var/tmp/rembly-rootfs
  local dump mount_dump=() env_dump="" rid=$1
  if dump=$(find_android_dump); then
    mount_dump=(-v "$dump:/android-dump:ro")
    env_dump="ANDROID_DUMP=/android-dump"
    sub "Wi-Fi/BT файлы: $dump"
  else
    sub "Дамп Android не найден: драйверы будут взяты с system/vendor на первом запуске."
  fi
  sudo podman run --rm --privileged --network=host --security-opt label=disable \
    -v "$ROOT:/work" -v /var/tmp/rembly-rootfs:/var/rembly/rootfs "${mount_dump[@]}" \
    -w /work ubuntu:22.04 bash -lc "
      set -e
      apt-get -o Acquire::Retries=8 update
      DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=8 install -y --fix-missing \
        debootstrap qemu-user-static binfmt-support e2fsprogs android-sdk-libsparse-utils \
        python3 file gzip cpio ca-certificates
      REMBLY_IMAGE_ID='$rid' $env_dump rootfs/build-rootfs.sh 3584 desktop
    "
  sudo chown -R "$(id -u):$(id -g)" "$OUT"
}

build_rootfs() {
  local rid=$1 dump=""
  step "Собираю Rembly OS rootfs"
  if [[ -f /etc/debian_version ]] && command -v debootstrap >/dev/null 2>&1 && command -v qemu-arm-static >/dev/null 2>&1; then
    dump=$(find_android_dump || true); sudo -v
    if [[ -n "$dump" ]]; then
      REMBLY_IMAGE_ID="$rid" ANDROID_DUMP="$dump" sudo -E "$ROOT/rootfs/build-rootfs.sh" 3584 desktop
    else
      REMBLY_IMAGE_ID="$rid" sudo -E "$ROOT/rootfs/build-rootfs.sh" 3584 desktop
    fi
    sudo chown -R "$(id -u):$(id -g)" "$OUT"
  else
    build_rootfs_container "$rid"
  fi
  [[ -s "$ROOTFS" ]] || die "Сборка не создала $ROOTFS"
  (cd "$OUT" && sha256sum rembly-rootfs.img > rembly-rootfs.img.sha256)
  printf '%s\n' "$rid" > "$OUT/rembly-rootfs.source-id"
  ok "Rootfs готов: $(du -h "$ROOTFS" | awk '{print $1}')"
}

ensure_sparse() {
  [[ -s "$SPARSE" && "$SPARSE" -nt "$ROOTFS" ]] && return 0
  command -v img2simg >/dev/null 2>&1 || die "Нет img2simg, а sparse rootfs требуется для старого MediaTek Fastboot."
  step "Создаю sparse rootfs для Fastboot"
  img2simg "$ROOTFS" "$SPARSE"
  [[ -s "$SPARSE" ]] || die "Не удалось создать $SPARSE"
  ok "Sparse rootfs готов: $(du -h "$SPARSE" | awk '{print $1}')"
}

ensure_images() {
  need_host_tools
  build_kernel
  build_boot

  ROOTFS_ID=$(rootfs_source_id)
  local marker=""
  [[ -f "$OUT/rembly-rootfs.source-id" ]] && marker=$(cat "$OUT/rembly-rootfs.source-id" 2>/dev/null || true)
  if (( REBUILD )) || [[ ! -s "$ROOTFS" ]]; then
    build_rootfs "$ROOTFS_ID"
  elif (( REUSE )); then
    warn "Использую существующий rootfs по --reuse-images"
    [[ -f "$OUT/rembly-rootfs.image-id" ]] && ROOTFS_ID=$(cat "$OUT/rembly-rootfs.image-id" 2>/dev/null || printf '%s' "$ROOTFS_ID")
  elif [[ "$marker" != "$ROOTFS_ID" ]]; then
    build_rootfs "$ROOTFS_ID"
  else
    ok "Rootfs уже собран из этих же данных"
  fi

  local label bootsz rootsz
  label=$(dd if="$ROOTFS" bs=8 skip=143 count=2 2>/dev/null | tr -d '\000')
  [[ "$label" == REMBLY ]] || die "rootfs имеет метку '$label', ожидалась REMBLY"
  bootsz=$(stat -c %s "$BOOTIMG"); rootsz=$(stat -c %s "$ROOTFS")
  (( bootsz < 16*1024*1024 )) || die "boot image больше 16 MiB"
  (( rootsz > 512*1024*1024 )) || die "rootfs выглядит подозрительно маленьким"
  ensure_sparse

  DESIRED_BOOT_SHA=$(sha256sum "$BOOTIMG" | awk '{print $1}')
  DESIRED_ROOTFS_SHA=$(sha256sum "$ROOTFS" | awk '{print $1}')
  HOST_BUILDTIME=""
  [[ -f "$OUT/rembly-rootfs.buildtime" ]] && HOST_BUILDTIME=$(tr -dc '0-9' < "$OUT/rembly-rootfs.buildtime")
  if [[ -z "$HOST_BUILDTIME" ]] && command -v debugfs >/dev/null 2>&1; then
    HOST_BUILDTIME=$(debugfs -R 'cat /etc/rembly/buildtime' "$ROOTFS" 2>/dev/null | tr -dc '0-9\n' | head -n1 || true)
  fi
  ok "Образы проверены"
}

adb_bounded() { command timeout 120s adb "$@"; }

list_fastboot() { timeout 5s fastboot devices 2>/dev/null | awk '$2=="fastboot"{print $1}'; }
list_adb() { timeout 5s adb devices 2>/dev/null | awk '$2=="device" || $2=="recovery"{print $1}'; }

adb_part() {
  local serial=$1 name=$2
  adb_bounded -s "$serial" shell "for u in /sys/class/block/*/uevent; do grep -qx 'PARTNAME=$name' \"\$u\" 2>/dev/null && { d=\${u%/uevent}; echo /dev/\${d##*/}; break; }; done" 2>/dev/null | tr -d '\r'
}

make_adb_backup() {
  local serial=$1 bootdev recdev stamp bdir
  adb_bounded -s "$serial" shell id 2>/dev/null | grep -q 'uid=0' || return 0
  bootdev=$(adb_part "$serial" boot); recdev=$(adb_part "$serial" recovery)
  [[ -n "$bootdev" && -n "$recdev" ]] || return 0
  stamp=$(date +%Y%m%d-%H%M%S); bdir="$ROOT/backups/$stamp"; mkdir -p "$bdir"
  step "Сохраняю текущие boot/recovery перед прямой прошивкой"
  adb_bounded -s "$serial" exec-out "dd if=$bootdev bs=4096 2>/dev/null" > "$bdir/boot-current.bin" || true
  adb_bounded -s "$serial" exec-out "dd if=$recdev bs=4096 2>/dev/null" > "$bdir/recovery-current.bin" || true
  cp -f "$ROOT/boot.bin" "$bdir/boot-stock.bin"
  cp -f "$ROOT/recovery.bin" "$bdir/recovery-stock.bin"
  (cd "$bdir" && sha256sum *.bin > SHA256SUMS)
  printf '%s\n' "$bdir" > "$OUT/last-backup-dir.txt"
  ok "Backup: $bdir"
}

NEED_ROOTFS=1
NEED_BOOT=1
HAD_ADB_PROBE=0

probe_existing_adb() {
  adb_bounded start-server >/dev/null 2>&1 || true
  mapfile -t ads < <(list_adb)
  ((${#ads[@]}==1)) || return 1
  if (( HAD_ADB_PROBE )); then
    [[ "${ads[0]}" == "$ADB_SERIAL" ]] || die "ADB-устройство сменилось во время установки."
    timeout 10s adb -s "$ADB_SERIAL" reboot bootloader >/dev/null 2>&1 || true
    return 0
  fi
  ADB_SERIAL=${ads[0]}
  local product
  product=$(timeout 5s adb -s "$ADB_SERIAL" shell getprop ro.product.device 2>/dev/null | tr -d '\r\n' || true)
  [[ "${product,,}" == "${EXPECTED_PRODUCT,,}" ]] || die "ADB: устройство '$product' не подтверждено как $EXPECTED_PRODUCT."
  HAD_ADB_PROBE=1
  step "Сравниваю уже установленную систему"

  local remote_id remote_time bootdev remote_boot_sha bootsz
  remote_id=$(adb_bounded -s "$ADB_SERIAL" shell 'cat /etc/rembly/image-id 2>/dev/null' 2>/dev/null | tr -d '\r\n' || true)
  remote_time=$(adb_bounded -s "$ADB_SERIAL" shell 'cat /etc/rembly/buildtime 2>/dev/null' 2>/dev/null | tr -dc '0-9' || true)
  if [[ -n "$remote_id" && "$remote_id" == "$ROOTFS_ID" ]]; then
    NEED_ROOTFS=0
    ok "userdata уже содержит этот Rembly image-id"
  elif [[ -n "$HOST_BUILDTIME" && -n "$remote_time" && "$remote_time" == "$HOST_BUILDTIME" ]]; then
    NEED_ROOTFS=0
    ok "userdata уже содержит этот же Rembly build"
  else
    sub "Rootfs отличается или его версия не подтверждена"
  fi

  bootdev=$(adb_part "$ADB_SERIAL" boot)
  bootsz=$(stat -c %s "$BOOTIMG")
  if [[ -n "$bootdev" ]]; then
    remote_boot_sha=$(adb_bounded -s "$ADB_SERIAL" shell "head -c $bootsz $bootdev 2>/dev/null | sha256sum" 2>/dev/null | awk '{print $1}' | tr -d '\r\n' || true)
    if [[ "$remote_boot_sha" == "$DESIRED_BOOT_SHA" ]]; then
      NEED_BOOT=0
      ok "boot уже совпадает по SHA-256"
    else
      sub "Boot отличается, будет обновлён"
    fi
  fi

  if (( FORCE )); then
    NEED_ROOTFS=1
    NEED_BOOT=1
    sub "--force: повторная прошивка включена принудительно"
  elif (( ! NEED_ROOTFS && ! NEED_BOOT )); then
    ok "На планшете уже установлены те же данные. Повторная прошивка не нужна."
    exit 0
  fi

  make_adb_backup "$ADB_SERIAL"
  sub "Перевожу планшет в Fastboot"
  timeout 10s adb -s "$ADB_SERIAL" reboot bootloader >/dev/null 2>&1 || warn "ADB не подтвердил перезагрузку; продолжаю ожидание."
  return 0
}

wait_for_fastboot() {
  step "Автоматически подключаю A73 и жду Fastboot"
  sub "Если планшет выключен, подключи USB и включи его. Ожидание можно прервать Ctrl+C."
  local start=$SECONDS last_probe=-30 last_status="" status now
  local -a fbs ads
  timeout 5s adb start-server >/dev/null 2>&1 || true
  while :; do
    mapfile -t fbs < <(list_fastboot)
    # Count unauthorized/offline devices too: never pick one of several tablets.
    mapfile -t ads < <(timeout 5s adb devices 2>/dev/null | awk 'NR>1 && NF>=2{print $1}')
    ((${#fbs[@]} + ${#ads[@]} > 1)) && die "Подключено несколько ADB/Fastboot-устройств. Оставь только A73."
    if ((${#fbs[@]}==1)); then
      FB_SERIAL=${fbs[0]}
      [[ "$FB_SERIAL" =~ ^[a-zA-Z0-9._:-]+$ && "$FB_SERIAL" != .* ]] || die "Некорректный серийный номер Fastboot."
      ok "Fastboot: $FB_SERIAL"
      return 0
    fi
    now=$SECONDS
    if ((${#ads[@]}==1 && now-last_probe >= 30)); then
      last_probe=$now
      # Repeat discovery: Android/recovery may appear after the installer starts.
      probe_existing_adb || true
    fi
    status="Жду доступный ADB или Fastboot. Выключенный планшет без USB-интерфейса программно включить нельзя."
    if ((${#ads[@]}==1)); then
      status="Жду переход в Fastboot; ADB offline/unauthorized требует загрузки Android или разрешения отладки на планшете."
    fi
    if [[ "$status" != "$last_status" ]]; then sub "$status"; last_status=$status; fi
    (( WAIT_SECONDS > 0 && SECONDS-start >= WAIT_SECONDS )) && die "A73 не появился в Fastboot за ${WAIT_SECONDS} с."
    sleep 2
  done
}

fbget() {
  fastboot -s "$FB_SERIAL" getvar "$1" 2>&1 | sed -nE "s/^(INFO)?$1:[[:space:]]*//p" | head -n1 | tr -d '\r'
}

verify_fastboot_device() {
  local prod unl
  prod=$(fbget product || true); unl=$(fbget unlocked || true)
  [[ "$prod" == "$EXPECTED_PRODUCT" ]] || die "Найден '$prod', нужен $EXPECTED_PRODUCT."
  [[ "$unl" == yes ]] || die "Bootloader закрыт (unlocked=$unl)."
  ok "Устройство подтверждено: $prod, bootloader unlocked"
}

STATE_DIR="$HOME/.cache/rembly/install-state"
STATE_ROOTFS_SHA=""
STATE_BOOT_SHA=""
STATE_ROOTFS_ID=""
STATE_FILE=""

load_state() {
  STATE_FILE="$STATE_DIR/$FB_SERIAL.state"
  [[ -f "$STATE_FILE" ]] || return 0
  STATE_ROOTFS_SHA=$(sed -n 's/^ROOTFS_SHA=//p' "$STATE_FILE" | head -n1)
  STATE_BOOT_SHA=$(sed -n 's/^BOOT_SHA=//p' "$STATE_FILE" | head -n1)
  STATE_ROOTFS_ID=$(sed -n 's/^ROOTFS_ID=//p' "$STATE_FILE" | head -n1)
}

save_state() {
  mkdir -p "$STATE_DIR"
  cat > "$STATE_FILE" <<EOF
SERIAL=$FB_SERIAL
ROOTFS_SHA=$STATE_ROOTFS_SHA
ROOTFS_ID=$STATE_ROOTFS_ID
BOOT_SHA=$STATE_BOOT_SHA
UPDATED_AT=$(date +%s)
EOF
}

apply_state_skip() {
  load_state
  if (( HAD_ADB_PROBE )); then
    (( ! NEED_ROOTFS )) && { STATE_ROOTFS_SHA=$DESIRED_ROOTFS_SHA; STATE_ROOTFS_ID=$ROOTFS_ID; }
    (( ! NEED_BOOT )) && STATE_BOOT_SHA=$DESIRED_BOOT_SHA
    save_state
    return 0
  fi
  (( FORCE )) && return 0
  if [[ "$STATE_ROOTFS_SHA" == "$DESIRED_ROOTFS_SHA" && "$STATE_ROOTFS_ID" == "$ROOTFS_ID" ]]; then
    NEED_ROOTFS=0
    ok "userdata совпадает с последней успешной установкой на этом устройстве"
  fi
  if [[ "$STATE_BOOT_SHA" == "$DESIRED_BOOT_SHA" ]]; then
    NEED_BOOT=0
    ok "boot совпадает с последней успешной установкой на этом устройстве"
  fi
}

flash_rootfs() {
  (( NEED_ROOTFS )) || { ok "userdata не требует прошивки"; return 0; }
  step "Напрямую прошиваю Rembly rootfs через Fastboot"
  sub "Стираю только userdata, потому что rootfs изменился"
  fastboot -s "$FB_SERIAL" erase userdata
  fastboot -s "$FB_SERIAL" erase cache >/dev/null 2>&1 || true
  fastboot -s "$FB_SERIAL" erase metadata >/dev/null 2>&1 || true

  local fb=( -s "$FB_SERIAL" ) log="$OUT/last-fastboot-userdata.log"
  if fastboot --help 2>&1 | grep -q -- '-S'; then
    fb+=( -S 32M )
    sub "Sparse chunks: 32 MiB"
  fi
  if ! timeout --signal=KILL 45m fastboot "${fb[@]}" flash userdata "$SPARSE" 2>&1 | tee "$log"; then
    if grep -qi 'low power\|battery charging' "$log"; then
      die "Fastboot отказал из-за низкого заряда. Boot не изменён. Заряди планшет и запусти установщик снова."
    fi
    die "Прошивка userdata не удалась. Boot не изменён."
  fi
  STATE_ROOTFS_SHA=$DESIRED_ROOTFS_SHA
  STATE_ROOTFS_ID=$ROOTFS_ID
  save_state
  ok "userdata прошит успешно"
}

flash_boot() {
  (( NEED_BOOT )) || { ok "boot не требует прошивки"; return 0; }
  step "Прошиваю VT-boot Rembly последним"
  local log="$OUT/last-fastboot-boot.log"
  if ! fastboot -s "$FB_SERIAL" flash boot "$BOOTIMG" 2>&1 | tee "$log"; then
    die "Прошивка boot не удалась. Уже записанный userdata сохранён."
  fi
  STATE_BOOT_SHA=$DESIRED_BOOT_SHA
  save_state
  ok "boot прошит успешно"
}

finish_install() {
  if (( ! NEED_ROOTFS && ! NEED_BOOT )); then
    step "Нечего обновлять"
    ok "Устройство уже содержит эти же данные"
    fastboot -s "$FB_SERIAL" reboot >/dev/null 2>&1 || true
    return 0
  fi
  flash_rootfs
  flash_boot
  step "Перезагружаю Rembly OS"
  fastboot -s "$FB_SERIAL" reboot || true
  printf '\nREMBLY INSTALL COMPLETE\n'
}

ensure_images
wait_for_fastboot
verify_fastboot_device
apply_state_skip
finish_install
