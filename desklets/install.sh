#!/bin/bash
# Install the Mono desklets for the current user (Cinnamon).
#   ./install.sh             copy them into ~/.local/share/cinnamon/desklets
#   ./install.sh --enable    also place all five on the desktop
#   ./install.sh --uninstall remove them from the desktop and delete the copies
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/cinnamon/desklets"
UUIDS=(mono-date@monotile mono-clock@monotile mono-weather@monotile mono-system@monotile mono-day@monotile)

enabled() { gsettings get org.cinnamon enabled-desklets; }

remove_from_desktop() {
    python3 - "$(enabled)" "${UUIDS[@]}" <<'PY'
import ast, subprocess, sys
current = ast.literal_eval(sys.argv[1].replace("@as ", ""))
keep = [d for d in current if d.split(":")[0] not in sys.argv[2:]]
if keep != current:
    subprocess.run(["gsettings", "set", "org.cinnamon", "enabled-desklets", str(keep)], check=True)
PY
}

if [ "${1:-}" = "--uninstall" ]; then
    remove_from_desktop
    for u in "${UUIDS[@]}"; do rm -rf "${DEST:?}/$u"; done
    echo "Mono desklets removed."
    exit 0
fi

mkdir -p "$DEST"
for u in "${UUIDS[@]}"; do
    rm -rf "${DEST:?}/$u"
    cp -r "$SRC/$u" "$DEST/$u"
    cp "$SRC/common/monolib.js" "$DEST/$u/monolib.js"
done
echo "Installed to $DEST. Add them with right-click on the desktop > Add Desklets."

if [ "${1:-}" = "--enable" ]; then
    # date | clock / weather | system / day progress, top-left, 12px gaps
    python3 - "$(enabled)" "$(gsettings get org.cinnamon next-desklet-id)" <<'PY'
import ast, subprocess, sys
current = ast.literal_eval(sys.argv[1].replace("@as ", ""))
next_id = int(sys.argv[2].split()[-1])
layout = [("mono-date@monotile", 40, 70), ("mono-clock@monotile", 196, 70),
          ("mono-weather@monotile", 40, 222), ("mono-system@monotile", 196, 222),
          ("mono-day@monotile", 40, 374)]
present = {d.split(":")[0] for d in current}
for uuid, x, y in layout:
    if uuid not in present:
        current.append(f"{uuid}:{next_id}:{x}:{y}")
        next_id += 1
subprocess.run(["gsettings", "set", "org.cinnamon", "next-desklet-id", str(next_id)], check=True)
subprocess.run(["gsettings", "set", "org.cinnamon", "enabled-desklets", str(current)], check=True)
PY
    echo "Placed on the desktop. Right-click any of them > Configure to change it."
fi
