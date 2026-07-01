#!/bin/bash
set -euo pipefail

print_info() { echo -e "\033[1;34m==>\033[0m $*"; }
die() { echo -e "\033[1;31mERROR:\033[0m $*" >&2; exit 1; }

command -v pacman >/dev/null 2>&1 || die "Falta pacman"

if ! command -v yay >/dev/null 2>&1; then
    die "Mango requiere yay instalado. Ejecuta primero Install base o yay_install."
fi

print_info "Instalando MangoWM desde AUR..."
yay -S --needed --noconfirm mangowm-git

print_info "Instalando dependencia de wallpaper..."
sudo pacman -S --needed --noconfirm swaybg

print_info "Mango instalado. Usa Import configs para copiar la configuración."
