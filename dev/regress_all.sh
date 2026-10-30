#!/usr/bin/env bash
# Linux/macOS counterpart of regress_all.ps1. Run from the repo root; results land in
# $TEMP/spr/all (TEMP defaults to /tmp), so dev/qa_*.py read them unchanged.
# JOBS sets how many sets run at once (default: CPU count); ONLY=ghost,swat limits the
# characters. Logs go to $TEMP/spr/logs so qa_failures.py sees only result folders.
set -uo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
out="${TEMP:-/tmp}/spr/all"
logs="${TEMP:-/tmp}/spr/logs"
mkdir -p "$out" "$logs"
run() {
  skill=$1 c=$2 p=$3
  d="$out/$c-$p" log="$logs/$c-$p.log"
  spec="$root/$skill/assets/characters/$c.json"
  [ -d "${spec%.json}" ] && spec="${spec%.json}/character.json"     # cut-out characters are folders
  rm -rf "$d"
  python3 "$root/$skill/scripts/generate.py" --character "$spec" \
    --preset "$p" --out "$d" > "$log" 2>&1 || return
  python3 "$root/$skill/scripts/qa_motion.py" "$d" >> "$log" 2>&1 || return
  echo "$c-$p: $(grep -E '^result:|Traceback' "$log" | tail -1)"
}
export -f run; export root out logs
{
  for c in hero knight mage ninja goblin cutout_demo; do for p in hd pixel; do echo "game-sprite-animator $c $p"; done; done
  for c in commando swat ghost mercenary; do for p in hd pixel; do echo "game-shooter-animator $c $p"; done; done
  for c in wanderer warden; do for p in hd pixel; do echo "game-topdown-animator $c $p"; done; done
  for p in hd pixel; do echo "game-quadruped-animator wolf $p"; done
} | grep -E "${ONLY:+ (${ONLY//,/|}) }" | xargs -P "${JOBS:-$(nproc)}" -L 1 bash -c 'run "$@"' _ || exit $?
echo "ALL DONE"
