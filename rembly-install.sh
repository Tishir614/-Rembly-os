#!/usr/bin/env bash
# Rembly OS installer entry point.
# The core owns UI and install logic. This wrapper also adopts an already-built
# legacy rootfs once, so upgrading the installer does not force a 3.5 GiB rebuild
# and userdata rewrite when the existing image is still the one on the tablet.
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CORE="$ROOT/rembly-install-core.sh"
OUT="$ROOT/out"
[[ -f "$CORE" ]] || { echo "Rembly installer core not found: $CORE" >&2; exit 1; }

want_rebuild=0
for a in "$@"; do [[ "$a" == --rebuild ]] && want_rebuild=1; done

if (( ! want_rebuild )) && [[ -s "$OUT/rembly-rootfs.img" && ! -f "$OUT/rembly-rootfs.source-id" ]]; then
  tree_hash=$(
    cd "$ROOT"
    while IFS= read -r -d '' f; do sha256sum "$f"; done < <(find rootfs -type f -print0 | sort -z)
  )
  tree_hash=$(printf '%s\n' "$tree_hash" | sha256sum | awk '{print $1}')
  rid=$(printf 'rootfs-tree=%s\nprofile=desktop\nsize=3584\n' "$tree_hash" | sha256sum | awk '{print $1}')
  printf '%s\n' "$rid" > "$OUT/rembly-rootfs.source-id"
  printf '[REMBLY] Existing rootfs adopted. It will be compared before any userdata flash.\n'
fi

exec bash "$CORE" "$@"
