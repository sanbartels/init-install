#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
die() { echo -e "${RED}Error: $*${NC}" >&2; exit 1; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

print_info "Instalando Hyprland y dependencias..."
sudo pacman -S --needed --noconfirm hyprland swaybg

# Herramientas para capturas de pantalla (keybind: Print)
print_info "Instalando herramientas de captura de pantalla..."
sudo pacman -S --needed --noconfirm \
    grim \
    slurp \
    wl-clipboard \
    flameshot

# Integración con portales y Qt Wayland
print_info "Instalando portales XDG y soporte Qt Wayland..."
sudo pacman -S --needed --noconfirm \
    xdg-desktop-portal-hyprland \
    xdg-desktop-portal-gtk \
    xdg-user-dirs \
    qt5-wayland \
    qt6-wayland

# Agente de autenticación (polkit)
print_info "Instalando agente polkit..."
sudo pacman -S --needed --noconfirm polkit-gnome

# Fuentes necesarias
print_info "Instalando fuentes..."
sudo pacman -S --needed --noconfirm \
    ttf-jetbrains-mono-nerd \
    ttf-font-awesome \
    noto-fonts \
    noto-fonts-emoji

# Actualizar caché de fuentes
fc-cache -fv

bash "$SCRIPT_DIR/configure_hyprland.sh"
