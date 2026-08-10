#!/usr/bin/env bash
# make_icns.sh
# ============
# Generates resources/icons/app_icon.icns from the master SVG, for the
# macOS .app bundle icon. Run once per release, or whenever app_icon.svg
# changes. Requires macOS (uses sips + iconutil, both built in).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SVG_SOURCE="$REPO_ROOT/resources/icons/app_icon.svg"
ICNS_OUTPUT="$REPO_ROOT/resources/icons/app_icon.icns"
ICONSET_DIR="$(mktemp -d)/icon.iconset"

if [[ "$(uname)" != "Darwin" ]]; then
    echo "make_icns.sh must be run on macOS (needs sips + iconutil)." >&2
    exit 1
fi

mkdir -p "$ICONSET_DIR"

echo "==> Rasterizing $SVG_SOURCE at each required size"
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" -s format png "$SVG_SOURCE" \
        --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z "$double" "$double" -s format png "$SVG_SOURCE" \
        --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null
done

echo "==> Building .icns"
iconutil -c icns "$ICONSET_DIR" -o "$ICNS_OUTPUT"
rm -rf "$(dirname "$ICONSET_DIR")"

echo "==> Wrote $ICNS_OUTPUT"
