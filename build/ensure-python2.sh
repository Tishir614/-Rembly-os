#!/usr/bin/env bash
# Print a Python 2.7 executable; diagnostics go to stderr. No system install.
set -Eeuo pipefail
valid_python2() {
  "$1" -c 'import sys, xml.dom.minidom, ConfigParser; xml.dom.minidom.parseString("<dct/>"); sys.exit(sys.version_info[:2] != (2, 7))' >/dev/null 2>&1
}
if [[ -n "${REMBLY_KERNEL_PYTHON:-}" ]]; then
  valid_python2 "$REMBLY_KERNEL_PYTHON" || { echo 'REMBLY_KERNEL_PYTHON must point to working Python 2.7' >&2; exit 1; }
  command -v "$REMBLY_KERNEL_PYTHON"
  exit 0
fi
if command -v python2 >/dev/null && valid_python2 python2; then
  command -v python2
  exit 0
fi
CACHE=${REMBLY_BUILD_CACHE:-"$HOME/.cache/rembly-kernel"}
mkdir -p "$CACHE"
CACHE=$(cd "$CACHE" && pwd)
PREFIX="$CACHE/python-2.7.18"
if valid_python2 "$PREFIX/bin/python2.7"; then
  printf '%s\n' "$PREFIX/bin/python2.7"
  exit 0
fi
for tool in python3 gcc make tar xz; do
  command -v "$tool" >/dev/null || { echo "Python 2 bootstrap requires $tool" >&2; exit 1; }
done
ARCHIVE="$CACHE/Python-2.7.18.tar.xz"
SHA=b62c0e7937551d0cc02b8fd5cb0f544f9405bafc9a54d3808ed4594812edef43
echo '== preparing private Python 2.7.18 for MediaTek DrvGen (first run only)' >&2
python3 - "$ARCHIVE" "$SHA" <<'PY'
import hashlib
import os
import sys
import urllib.request
from pathlib import Path
archive, expected = Path(sys.argv[1]), sys.argv[2]
if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
    try:
        with urllib.request.urlopen('https://www.python.org/ftp/python/2.7.18/Python-2.7.18.tar.xz', timeout=120) as response:
            data = response.read()
    except OSError as error:
        raise SystemExit('Cannot download Python 2.7.18: %s' % error)
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit('Python source checksum mismatch')
    temporary = archive.with_name(archive.name + '.%s.part' % os.getpid())
    temporary.write_bytes(data)
    temporary.replace(archive)
PY
BUILD=$(mktemp -d "$CACHE/python2-build.XXXXXX")
trap 'rm -rf -- "$BUILD"' EXIT
LOG="$CACHE/python2-build.log"
JOBS=${REMBLY_KERNEL_JOBS:-2}
echo "== building Python 2.7; log: $LOG" >&2
if ! (
  tar -xJf "$ARCHIVE" -C "$BUILD" &&
  cd "$BUILD/Python-2.7.18" &&
  # GCC 15 defaults to C23; CPython 2 requires the older C dialect.
  CC=gcc CFLAGS='-O2 -std=gnu11 -fcommon' ./configure --prefix="$PREFIX" --without-ensurepip &&
  make -j"$JOBS" &&
  make install
) >"$LOG" 2>&1; then
  tail -n 40 "$LOG" >&2
  exit 1
fi
valid_python2 "$PREFIX/bin/python2.7" || { echo "Python 2 validation failed; see $LOG" >&2; exit 1; }
printf '%s\n' "$PREFIX/bin/python2.7"
