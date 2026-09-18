#!/system/bin/sh
# Read-only: compare on-disk image metadata, NOT the device's fused floor.
MODDIR=${MODDIR:-$(CDPATH= cd -- "$(dirname "$0")/.." 2>/dev/null && pwd)}
BY_NAME_DIR=${BY_NAME_DIR:-/dev/block/by-name}
part=${2:-abl}
case "$part" in
  ''|*[!a-zA-Z0-9_]*|*_a|*_b) printf 'ERROR=INVALID_PARTITION\n'; exit 1 ;;
esac
case "$1" in
  slots) ;;
  image) case "$3" in /*) ;; *) printf 'ERROR=ABSOLUTE_PATH_REQUIRED\n'; exit 1 ;; esac ;;
  *) printf 'ERROR=INVALID_ACTION\n'; exit 1 ;;
esac
if [ ! -x "$MODDIR/bin/arb_inspect" ]; then
  printf 'ERROR=INSPECTOR_MISSING\n'; exit 1
fi
slot=$(getprop ro.boot.slot_suffix 2>/dev/null)
case "$slot" in
  _a|_b) ;;
  *) slot=$(getprop ro.boot.slot 2>/dev/null); case "$slot" in a|b) slot="_$slot" ;; *) slot=unknown ;; esac ;;
esac
printf 'CURRENT_SLOT=%s\nPARTITION=%s\n' "$slot" "$part"
inspect_image() {
  # Never eval/source inspector output or caller-provided paths.
  "$MODDIR/bin/arb_inspect" "$2" | sed "s/^/$1_/"
}
if [ "$1" = slots ]; then
  inspect_image A "$BY_NAME_DIR/${part}_a"
  inspect_image B "$BY_NAME_DIR/${part}_b"
else
  if [ "$slot" = unknown ]; then
    printf 'CURRENT_STATUS=error\nCURRENT_ERROR=UNKNOWN_SLOT\n'
  else
    inspect_image CURRENT "$BY_NAME_DIR/${part}${slot}"
  fi
  inspect_image FILE "$3"
fi
