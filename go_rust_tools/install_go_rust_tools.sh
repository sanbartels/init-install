#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[GO/RUST]${NC} $*"; }
print_warning() { echo -e "${YELLOW}[GO/RUST]${NC} $*"; }
die() { echo -e "${RED}Error:${NC} $*" >&2; exit 1; }

command -v sudo >/dev/null 2>&1 || die "Falta sudo"
command -v pacman >/dev/null 2>&1 || die "Falta pacman; este módulo es para Arch Linux"

if command -v go >/dev/null 2>&1; then
    print_warning "Go ya está instalado: $(go version)"
else
    print_info "Instalando Go..."
    sudo pacman -S --needed --noconfirm go
fi

if command -v rustup >/dev/null 2>&1; then
    print_warning "rustup ya está instalado: $(rustup --version | head -n1)"
elif command -v rustc >/dev/null 2>&1 || command -v cargo >/dev/null 2>&1; then
    print_warning "Rust/Cargo ya está instalado sin rustup."
    print_warning "No se instalará rustup para evitar conflictos con el toolchain existente."
else
    print_info "Instalando rustup..."
    sudo pacman -S --needed --noconfirm rustup
fi

if command -v rustup >/dev/null 2>&1; then
    if rustup default 2>/dev/null | grep -q '^no default toolchain'; then
        print_info "Configurando toolchain Rust estable..."
        rustup default stable
    else
        print_info "Rust toolchain ya configurado: $(rustup default)"
    fi
fi

print_info "Go/Rust listo."
