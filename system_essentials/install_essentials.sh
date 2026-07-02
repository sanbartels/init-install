#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
die() { echo -e "${RED}Error: $*${NC}" >&2; exit 1; }

command -v sudo >/dev/null 2>&1 || die "Falta sudo"
command -v pacman >/dev/null 2>&1 || die "Falta pacman"

print_info "Instalando utilidades esenciales del sistema..."
sudo pacman -S --needed --noconfirm \
    btop \
    eza \
    fd \
    ripgrep \
    fzf \
    udiskie \
    brightnessctl \
    playerctl \
    python-gobject \
    zoxide

print_info "Utilidades esenciales listas."
