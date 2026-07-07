#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[WAYVNC]${NC} $*"; }
print_warning() { echo -e "${YELLOW}[WAYVNC]${NC} $*"; }
die() {
	echo -e "${RED}Error:${NC} $*" >&2
	exit 1
}

command -v sudo >/dev/null 2>&1 || die "Falta sudo"
command -v pacman >/dev/null 2>&1 || die "Falta pacman; este módulo es para Arch Linux"

print_info "Instalando wayvnc desde repositorios oficiales de Arch..."
sudo pacman -S --needed --noconfirm wayvnc

print_info "wayvnc instalado."
echo ""
echo "Siguientes pasos:"
echo "  1. Conecta el VPS a Tailscale: sudo tailscale up --ssh"
echo "  2. Inicia sesión gráfica Wayland/Hyprland."
echo "  3. Ejecuta wayvnc ligado a la IP Tailscale o a localhost según tu túnel."
echo "  4. Conecta desde Mac/iPhone con un cliente VNC usando la red Tailscale."
echo ""
print_warning "No se crea configuración automática de contraseña/display; wayvnc queda como fallback simple."
