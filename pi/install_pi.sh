#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

REPO_URL="https://github.com/j0k3r-dev-rgl/j0k3r-pi.git"
TARGET_DIR="$HOME/.pi/agent"
LOCAL_PREFIX="$HOME/.local"
PI_BIN="$LOCAL_PREFIX/bin/pi"
PI_PACKAGE="@earendil-works/pi-coding-agent"

print_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
print_success() { echo -e "${GREEN}[OK]${NC} $*"; }
print_warning() { echo -e "${YELLOW}[AVISO]${NC} $*"; }
die() { echo -e "${RED}Error: $*${NC}" >&2; exit 1; }

require_arch() {
    command -v pacman >/dev/null 2>&1 || die "No es Arch Linux o pacman no está disponible"
}

ensure_packages() {
    require_arch
    print_info "Instalando dependencias para Pi..."
    sudo pacman -S --needed --noconfirm git curl nodejs npm
}

ensure_local_bin_path() {
    local path_line='export PATH="$HOME/.local/bin:$PATH"'
    local shell_rc="$HOME/.bashrc"

    if [ -f "$shell_rc" ] && grep -Fxq "$path_line" "$shell_rc"; then
        print_info "~/.local/bin ya está en $shell_rc"
        return
    fi

    touch "$shell_rc"
    {
        echo ""
        echo "# init-install local bin"
        echo "$path_line"
    } >> "$shell_rc"
    print_warning "Agregado ~/.local/bin al PATH en $shell_rc. Reinicia la sesión o ejecuta: $path_line"
}

install_pi() {
    if [ -x "$PI_BIN" ]; then
        print_info "Pi ya está instalado: $PI_BIN"
        return
    fi

    print_info "Instalando Pi Coding Agent sin prompts interactivos..."
    npm install -g --ignore-scripts --min-release-age=0 --prefix "$LOCAL_PREFIX" --no-fund --no-audit --progress=false "$PI_PACKAGE"

    [ -x "$PI_BIN" ] || die "La instalación terminó pero no se encontró $PI_BIN"
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
    "$PI_BIN" install npm:pi-subagents-j0k3r
}

ensure_packages
ensure_local_bin_path
install_pi
clone_global_config
install_subagents_extension

print_success "Pi instalado y configurado"
print_warning "Si 'pi' no aparece en esta sesión, ejecuta: export PATH=\"$HOME/.local/bin:$PATH\""
