#!/usr/bin/env bash
# Compatibility entry point.
# The main installer is now direct Fastboot by default, builds the VT-capable
# kernel, and skips unchanged userdata/boot automatically.
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec bash "$ROOT/rembly-install.sh" "$@"
