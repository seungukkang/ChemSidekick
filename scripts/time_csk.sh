#!/bin/sh
# Time a few csk commands, for reference only (not a test).
#
#   scripts/time_csk.sh              # uses ~/.local/bin/csk
#   scripts/time_csk.sh /path/to/csk
#
# Run it right after a reboot to see the cold start, then again for the warm times.
# Each command runs once; the first line is the coldest.

CSK="${1:-$HOME/.local/bin/csk}"
if [ ! -x "$CSK" ]; then
  echo "csk not found at $CSK (install: uv tool install --editable .)" >&2
  exit 1
fi

echo "csk: $CSK"
echo "uptime: $(uptime)"
run() {
  start=$(perl -MTime::HiRes=time -e 'printf "%.3f", time')
  "$CSK" "$@" >/dev/null 2>&1
  code=$?
  end=$(perl -MTime::HiRes=time -e 'printf "%.3f", time')
  printf '%6.2f s  exit %d  csk %s\n' "$(echo "$end - $start" | bc)" "$code" "$*"
}

run element Fe --json
run element Fe --json
run element --json
run stereo "CC(O)C(O)C(O)C" --json --no-3d --no-open
run stereo "CC(O)C(O)C(O)C" --json --no-open
run stereo "CC(O)C(O)C(O)C" --json --no-open
