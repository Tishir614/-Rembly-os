#!/usr/bin/env bash
# Safe boot-only fallback for A73/MediaTek when Android reboot-to-bootloader
# lands in MT65xx Preloader instead of Fastboot.
set -Eeuo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT="$ROOT/out"
BOOTIMG="$OUT/A73-linux-test.img"
KERNEL_IMG="$OUT/rembly-kernel-vt.zImage"
LOG="$OUT/last-mtk-boot.log"
EXPECTED_STOCK_BOOT_SHA=a94d3f8a18d626d0e12c3c1fe0848076a5c7754f2f108f727a9a21249a3483f4

say()  { printf '[REMBLY] %s\n' "$*"; }
warn() { printf '[REMBLY][WARN] %s\n' "$*" >&2; }
die()  { printf '[REMBLY][ERROR] %s\n' "$*" >&2; exit 1; }

[[ "$(uname -s)" == Linux ]] || die "MTK fallback рассчитан на Linux."
command -v timeout >/dev/null 2>&1 || die "Не найден timeout."
command -v sha256sum >/dev/null 2>&1 || die "Не найден sha256sum."
command -v python3 >/dev/null 2>&1 || die "Не найден python3."

[[ -s "$KERNEL_IMG" ]] || die "VT-ядро не собрано: $KERNEL_IMG"
[[ -s "$BOOTIMG" ]] || die "Boot-образ не собран: $BOOTIMG"
[[ -f "$ROOT/boot.bin" ]] || die "Нет проверенного stock boot.bin"

stock_sha=$(sha256sum "$ROOT/boot.bin" | awk '{print $1}')
[[ "$stock_sha" == "$EXPECTED_STOCK_BOOT_SHA" ]] || die "stock boot.bin не совпадает с проверенным образом A73"

bootsz=$(stat -c %s "$BOOTIMG")
(( bootsz > 4*1024*1024 && bootsz < 16*1024*1024 )) || die "Подозрительный размер boot: $bootsz байт"
python3 - "$BOOTIMG" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
with p.open('rb') as f:
    magic = f.read(8)
if magic != b'ANDROID!':
    raise SystemExit('boot image has no ANDROID! magic')
PY

find_mtkclient() {
  local p="${REMBLY_MTKCLIENT_DIR:-}"
  if [[ -n "$p" && -f "$p/mtk.py" ]]; then
    printf '%s\n' "$p"; return 0
  fi
  for p in \
    "$ROOT/mtkclient" \
    "$ROOT/../mtkclient" \
    "$HOME/mtkclient" \
    "$HOME/Documents/mtkclient" \
    "$HOME/Downloads/mtkclient"; do
    [[ -f "$p/mtk.py" ]] && { printf '%s\n' "$p"; return 0; }
  done
  p=$(find "$HOME/Documents" "$HOME/Downloads" -maxdepth 8 -type f -path '*/mtkclient/mtk.py' -print -quit 2>/dev/null || true)
  [[ -n "$p" ]] && { dirname "$p"; return 0; }
  return 1
}

MTK_DIR=$(find_mtkclient || true)
[[ -n "$MTK_DIR" ]] || die "mtkclient не найден. Укажи REMBLY_MTKCLIENT_DIR=/путь/к/mtkclient"
MTK_PY="$MTK_DIR/mtk.py"
if [[ -x "$MTK_DIR/.venv/bin/python" ]]; then
  PY="$MTK_DIR/.venv/bin/python"
elif [[ -x "$MTK_DIR/venv/bin/python" ]]; then
  PY="$MTK_DIR/venv/bin/python"
else
  PY=$(command -v python3)
fi

sudo -v
mkdir -p "$ROOT/backups" "$OUT"
backup_dir="$ROOT/backups/mtk-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"
backup="$backup_dir/boot-before-mtk.bin"

say "Fastboot недоступен. Перехожу на безопасный MediaTek boot-only режим."
say "mtkclient: $MTK_DIR"
say "Пробую сохранить текущий boot. Если Preloader ещё не пойман, mtkclient будет ждать устройство."

set +e
timeout --signal=KILL 180s sudo "$PY" "$MTK_PY" r boot "$backup" 2>&1 | tee "$OUT/last-mtk-backup.log"
backup_rc=${PIPESTATUS[0]}
set -e
if (( backup_rc == 0 )) && [[ -s "$backup" ]]; then
  (cd "$backup_dir" && sha256sum boot-before-mtk.bin > SHA256SUMS)
  printf '%s\n' "$backup_dir" > "$OUT/last-backup-dir.txt"
  say "Текущий boot сохранён: $backup"
else
  rm -f "$backup"
  warn "Не удалось прочитать текущий boot. Проверенный stock boot.bin остаётся резервным образом."
fi

say "Записываю ТОЛЬКО раздел boot. userdata/system/vendor/NVRAM не трогаются."
set +e
timeout --signal=KILL 240s sudo "$PY" "$MTK_PY" w boot "$BOOTIMG" 2>&1 | tee "$LOG"
write_rc=${PIPESTATUS[0]}
set -e
(( write_rc == 0 )) || die "mtkclient не смог записать boot. Другие разделы не изменялись. Лог: $LOG"

sha256sum "$BOOTIMG" > "$OUT/last-mtk-boot.sha256"
say "Boot записан успешно. Перезагружаю планшет."
timeout 60s sudo "$PY" "$MTK_PY" reset >/dev/null 2>&1 || warn "Автоперезагрузка не сработала. Можно включить планшет кнопкой питания."
printf '\nREMBLY MTK BOOT UPDATE COMPLETE\n'
