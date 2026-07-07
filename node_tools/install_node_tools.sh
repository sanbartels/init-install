#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[NODE]${NC} $*"; }
print_warning() { echo -e "${YELLOW}[NODE]${NC} $*"; }
die() {
	echo -e "${RED}Error:${NC} $*" >&2
	exit 1
}

command -v sudo >/dev/null 2>&1 || die "Falta sudo"
command -v pacman >/dev/null 2>&1 || die "Falta pacman; este módulo es para Arch Linux"

packages=(npm pnpm yarn)

if command -v node >/dev/null 2>&1; then
	print_warning "Node.js ya está instalado: $(node --version)"
	print_warning "No se instalará nodejs-lts-krypton para evitar conflicto con el Node actual."
else
	packages=(nodejs-lts-krypton "${packages[@]}")
fi

print_info "Instalando herramientas Node.js: ${packages[*]}"
sudo pacman -S --needed --noconfirm "${packages[@]}"
