#!/bin/bash

set -euo pipefail

WALLPAPER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/wallpapers"

if ! command -v swaybg >/dev/null 2>&1; then
    echo "swaybg no está instalado; no se puede cargar wallpaper" >&2
    exit 0
fi

if [ ! -d "$WALLPAPER_DIR" ]; then
    echo "Directorio de wallpapers no encontrado: $WALLPAPER_DIR" >&2
    exit 0
fi

wallpaper="$(find "$WALLPAPER_DIR" -maxdepth 1 -type f \
    \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' \) \
    | shuf -n 1)"

if [ -z "$wallpaper" ]; then
    echo "No hay wallpapers en: $WALLPAPER_DIR" >&2
    exit 0
fi

pkill -x swaybg 2>/dev/null || true
exec swaybg -m fill -i "$wallpaper"
