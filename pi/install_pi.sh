#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

REPO_URL="https://github.com/j0k3r-dev-rgl/j0k3r-pi.git"
TARGET_DIR="$HOME/.pi/agent"

print_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
print_success() { echo -e "${GREEN}[OK]${NC} $*"; }
die() { echo -e "${RED}Error: $*${NC}" >&2; exit 1; }

require_arch() {
    command -v pacman >/dev/null 2>&1 || die "No es Arch Linux o pacman no está disponible"
}

ensure_packages() {
    require_arch
    print_info "Instalando dependencias para Pi..."
    sudo pacman -S --needed --noconfirm git curl
}

install_pi() {
    if command -v pi >/dev/null 2>&1; then
        print_info "Pi ya está instalado: $(command -v pi)"
        return
    fi

    print_info "Instalando Pi Coding Agent con instalador oficial..."
    curl -fsSL https://pi.dev/install.sh | sh

    command -v pi >/dev/null 2>&1 || die "La instalación terminó pero el comando 'pi' no está disponible"
}

clone_global_config() {
    if [ -d "$TARGET_DIR/.git" ]; then
        print_info "Actualizando configuración global de Pi en $TARGET_DIR..."
        git -C "$TARGET_DIR" pull --ff-only
        return
    fi

    if [ -e "$TARGET_DIR" ] && [ -n "$(find "$TARGET_DIR" -mindepth 1 -maxdepth 1 2>/dev/null)" ]; then
        die "$TARGET_DIR existe y no está vacío. Muévelo o vacíalo antes de clonar j0k3r-pi."
    fi

    print_info "Clonando configuración global de Pi en $TARGET_DIR..."
    mkdir -p "$TARGET_DIR"
    git clone --depth 1 "$REPO_URL" "$TARGET_DIR"
}

install_subagents_extension() {
    print_info "Instalando extensión de subagents..."
    pi install npm:pi-subagents-j0k3r
}

ensure_packages
install_pi
clone_global_config
install_subagents_extension

print_success "Pi instalado y configurado"
