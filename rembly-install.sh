#!/usr/bin/env bash
# Rembly OS installer entry point.
# The flashing/install engine is preserved byte-for-byte in rembly-install-core.sh.
# This file only injects the branded terminal UI, then runs the original engine.
set -Eeuo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CORE="$ROOT/rembly-install-core.sh"
UI="$ROOT/tools/rembly-installer-ui.sh"
RUNTIME="$ROOT/.rembly-install-runtime-$$.sh"

cleanup() { rm -f "$RUNTIME"; }
trap cleanup EXIT INT TERM

[[ -f "$CORE" ]] || { echo "Rembly installer core not found: $CORE" >&2; exit 1; }
[[ -f "$UI" ]] || { echo "Rembly installer UI not found: $UI" >&2; exit 1; }
command -v awk >/dev/null 2>&1 || { echo "awk is required" >&2; exit 1; }

export REMBLY_UI_HELPER="$UI"

# Replace only the old presentation block at runtime. Everything before and after
# it is copied unchanged from the original installer engine.
awk '
  BEGIN { visual=0; done=0 }
  !done && $0 == "if [[ -t 1 ]]; then" {
    visual=1
    print ". \"${REMBLY_UI_HELPER:?}\""
    print "rembly_ui_start"
    next
  }
  visual && $0 == "mkdir -p \"$OUT\"" {
    visual=0; done=1
    print "[[ \"$(uname -s)\" == Linux ]] || die \"Установщик рассчитан на Linux ПК.\""
    print "mkdir -p \"$OUT\""
    next
  }
  !visual { print }
' "$CORE" > "$RUNTIME"

chmod 700 "$RUNTIME"
grep -q '^rembly_ui_start$' "$RUNTIME" || {
  echo "Rembly installer UI patch marker was not found. Original installer was not started." >&2
  exit 1
}

bash "$RUNTIME" "$@"
