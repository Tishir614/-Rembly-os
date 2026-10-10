#!/usr/bin/env bash
# Rembly OS installer entry point.
# The core now owns both UI startup and all install logic, so no runtime source
# rewriting is needed.
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CORE="$ROOT/rembly-install-core.sh"
[[ -f "$CORE" ]] || { echo "Rembly installer core not found: $CORE" >&2; exit 1; }
exec bash "$CORE" "$@"
