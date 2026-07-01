#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

print_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
print_step() { echo -e "${BLUE}[....] $*${NC}"; }
print_ok()   { echo -e "${GREEN}[ OK ] $*${NC}"; }
print_skip() { echo -e "${YELLOW}[SKIP]${NC} $*"; }
die()        { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_CONFIG_DIR="$SCRIPT_DIR/configs"
NVIM_CONFIG_DIR="$HOME/.config/nvim"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Instalación de Neovim               ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

[ -d "$LOCAL_CONFIG_DIR" ] || die "No se encontró la configuración local en $LOCAL_CONFIG_DIR"

# ─── 1. Neovim y dependencias ─────────────────────────────────────────────────
print_step "Instalando Neovim desde pacman y dependencias..."
if sudo pacman -S --needed --noconfirm \
    neovim \
    git gcc make unzip curl ripgrep fd fzf lazygit \
    nodejs-lts-krypton npm pnpm yarn bun \
    python python-pip python-pynvim \
    jdk-openjdk maven gradle \
    tree-sitter tree-sitter-cli wl-clipboard; then
    print_ok "Neovim y dependencias instalados"
else
    die "Falló la instalación con pacman"
fi

if command -v nvim >/dev/null 2>&1; then
    NVIM_VERSION="$(nvim --version 2>/dev/null | head -1 || true)"
    print_ok "Neovim disponible: ${NVIM_VERSION:-$(command -v nvim)}"
else
    die "La instalación terminó pero el comando 'nvim' no está disponible"
fi

# ─── 2. Configuración ─────────────────────────────────────────────────────────
echo ""
if [ -d "$NVIM_CONFIG_DIR" ] && [ -n "$(ls -A "$NVIM_CONFIG_DIR" 2>/dev/null)" ]; then
    print_warn "Ya existe configuración en $NVIM_CONFIG_DIR"
    echo ""
    echo "  Opciones:"
    echo "    1) Reemplazar — mueve la actual a backup y aplica la del repo"
    echo "    2) Mantener   — no toca nada"
    echo ""
    echo -en "${YELLOW}[????]${NC} ¿Qué deseas hacer? (1/2, default: 2): "
    read -r config_choice
    config_choice="${config_choice:-2}"

    case "$config_choice" in
        1)
            BACKUP_DIR="$HOME/.config/nvim.bak.$(date +%Y%m%d_%H%M%S)"
            print_step "Moviendo config actual a $BACKUP_DIR..."
            mv "$NVIM_CONFIG_DIR" "$BACKUP_DIR"
            print_ok "Backup creado en $BACKUP_DIR"

            print_step "Aplicando configuración del repositorio..."
            mkdir -p "$NVIM_CONFIG_DIR"
            cp -a "$LOCAL_CONFIG_DIR/." "$NVIM_CONFIG_DIR/"
            print_ok "Configuración aplicada"
            ;;
        2)
            print_skip "Configuración existente conservada sin cambios"
            ;;
        *)
            print_warn "Opción no reconocida. Configuración conservada sin cambios."
            ;;
    esac
else
    print_step "Aplicando configuración de Neovim..."
    mkdir -p "$NVIM_CONFIG_DIR"
    cp -a "$LOCAL_CONFIG_DIR/." "$NVIM_CONFIG_DIR/"
    print_ok "Configuración aplicada en $NVIM_CONFIG_DIR"
fi

echo ""
print_ok "Instalación de Neovim completada."
echo ""
