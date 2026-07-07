#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[TAILSCALE]${NC} $*"; }
print_warning() { echo -e "${YELLOW}[TODO]${NC} $*"; }

command -v sudo >/dev/null 2>&1 || {
	echo "Error: falta sudo" >&2
	exit 1
}
command -v pacman >/dev/null 2>&1 || {
	echo "Error: falta pacman; este módulo es para Arch Linux" >&2
	exit 1
}

print_info "Instalando Tailscale desde repositorios oficiales de Arch..."
sudo pacman -S --needed --noconfirm tailscale

print_info "Habilitando tailscaled..."
sudo systemctl enable --now tailscaled.service

print_info "Tailscale instalado y servicio activo."
print_warning "Autenticá este VPS manualmente con: sudo tailscale up --ssh"
print_warning "Luego conectate por la IP Tailscale o MagicDNS."
