#!/usr/bin/env bash
# Build a VT-capable Linux 3.18 kernel for K37MV1_BSP / MT6737M.
# The resulting zImage is later combined with the exact DTB from the verified
# stock boot image, so this script never flashes the tablet by itself.
set -Eeuo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT="$ROOT/out"
CACHE=${REMBLY_BUILD_CACHE:-"$HOME/.cache/rembly-kernel"}
BSP_DIR="$CACHE/orangepi-bsp"
TC_DIR="$CACHE/arm-eabi-4.8"
BSP_URL=${REMBLY_KERNEL_BSP_URL:-https://github.com/iscle/OrangePi_4G-IOT_Android_8.1_BSP.git}
BSP_COMMIT=${REMBLY_KERNEL_BSP_COMMIT:-58548740b6e9afe99a55b77582588c37609d2bca}
TC_URL=${REMBLY_KERNEL_TOOLCHAIN_URL:-https://github.com/ubports-android/aosp_platform_prebuilts_gcc_linux-x86_arm_arm-eabi-4.8.git}
REBUILD=0
[[ "${1:-}" == --rebuild ]] && REBUILD=1

mkdir -p "$OUT" "$CACHE"
command -v git >/dev/null 2>&1 || { echo "git not found" >&2; exit 1; }
command -v make >/dev/null 2>&1 || { echo "make not found" >&2; exit 1; }
command -v sha256sum >/dev/null 2>&1 || { echo "sha256sum not found" >&2; exit 1; }

if [[ ! -d "$BSP_DIR/.git" ]]; then
  echo "== cloning K37MV1_BSP kernel source"
  git clone --filter=blob:none --no-checkout "$BSP_URL" "$BSP_DIR"
  git -C "$BSP_DIR" sparse-checkout init --cone
  git -C "$BSP_DIR" sparse-checkout set kernel-3.18
fi

git -C "$BSP_DIR" fetch --depth 1 origin "$BSP_COMMIT"
git -C "$BSP_DIR" checkout --detach -q "$BSP_COMMIT"
git -C "$BSP_DIR" sparse-checkout set kernel-3.18

if [[ ! -x "$TC_DIR/bin/arm-eabi-gcc" ]]; then
  echo "== cloning ARM EABI GCC 4.8 toolchain"
  rm -rf "$TC_DIR"
  git clone --depth 1 "$TC_URL" "$TC_DIR"
fi

K="$BSP_DIR/kernel-3.18"
[[ -f "$K/Makefile" ]] || { echo "kernel-3.18 source missing" >&2; exit 1; }
[[ -f "$ROOT/kernel_config.txt" ]] || { echo "kernel_config.txt missing" >&2; exit 1; }

TC_COMMIT=$(git -C "$TC_DIR" rev-parse HEAD 2>/dev/null || echo unknown)
CONFIG_SHA=$(sha256sum "$ROOT/kernel_config.txt" | awk '{print $1}')
INPUT_ID=$(printf '%s\n%s\n%s\n%s\n' "$BSP_COMMIT" "$TC_COMMIT" "$CONFIG_SHA" \
  'VT CONSOLE_TRANSLATIONS VT_CONSOLE HW_CONSOLE FRAMEBUFFER_CONSOLE' | sha256sum | awk '{print $1}')
OUT_KERNEL="$OUT/rembly-kernel-vt.zImage"
STAMP="$OUT/rembly-kernel-vt.id"

if (( ! REBUILD )) && [[ -s "$OUT_KERNEL" && -f "$STAMP" ]] && [[ "$(cat "$STAMP" 2>/dev/null)" == "$INPUT_ID" ]]; then
  echo "== VT kernel is current: $OUT_KERNEL"
  exit 0
fi

echo "== preparing stock tablet kernel config"
cp "$ROOT/kernel_config.txt" "$K/.config"
chmod +x "$K/scripts/config" 2>/dev/null || true

cfg_on() {
  local key=$1
  if [[ -x "$K/scripts/config" ]]; then
    "$K/scripts/config" --file "$K/.config" --enable "$key"
  else
    sed -i -E "/^(# )?CONFIG_${key}(=| is not set)/d" "$K/.config"
    printf 'CONFIG_%s=y\n' "$key" >> "$K/.config"
  fi
}

for key in VT CONSOLE_TRANSLATIONS VT_CONSOLE HW_CONSOLE FRAMEBUFFER_CONSOLE; do
  cfg_on "$key"
done

export ARCH=arm
export CROSS_COMPILE="$TC_DIR/bin/arm-eabi-"

if (( REBUILD )); then
  make -C "$K" ARCH=arm CROSS_COMPILE="$CROSS_COMPILE" clean
fi

make -C "$K" ARCH=arm CROSS_COMPILE="$CROSS_COMPILE" olddefconfig

for key in VT VT_CONSOLE HW_CONSOLE FRAMEBUFFER_CONSOLE; do
  grep -qx "CONFIG_${key}=y" "$K/.config" || {
    echo "required CONFIG_${key}=y was not accepted by kernel Kconfig" >&2
    exit 1
  }
done

echo "== building K37MV1_BSP zImage with VT console"
JOBS=${REMBLY_KERNEL_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)}
make -C "$K" -j"$JOBS" ARCH=arm CROSS_COMPILE="$CROSS_COMPILE" KCFLAGS="${KCFLAGS:-} -Wno-error" zImage

[[ -s "$K/arch/arm/boot/zImage" ]] || { echo "kernel build did not produce zImage" >&2; exit 1; }
cp -f "$K/arch/arm/boot/zImage" "$OUT_KERNEL"
printf '%s\n' "$INPUT_ID" > "$STAMP"
cat > "$OUT/rembly-kernel-vt.buildinfo" <<EOF
BSP_COMMIT=$BSP_COMMIT
TOOLCHAIN_COMMIT=$TC_COMMIT
CONFIG_SHA256=$CONFIG_SHA
INPUT_ID=$INPUT_ID
EOF

echo "== kernel ready: $OUT_KERNEL"
sha256sum "$OUT_KERNEL"
