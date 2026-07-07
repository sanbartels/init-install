#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[DOCKER]${NC} $*"; }
print_warning() { echo -e "${YELLOW}[DOCKER]${NC} $*"; }
die() { echo -e "${RED}Error:${NC} $*" >&2; exit 1; }

command -v sudo >/dev/null 2>&1 || die "Falta sudo"
command -v pacman >/dev/null 2>&1 || die "Falta pacman; este módulo es para Arch Linux"

print_info "Instalando Docker y Docker Compose..."
sudo pacman -S --needed --noconfirm docker docker-compose

print_info "Habilitando Docker..."
if sudo systemctl enable --now docker.service; then
    print_info "docker.service activo"
else
    print_warning "Docker quedó instalado, pero docker.service no pudo arrancar."
    print_warning "Revisa el motivo con: sudo systemctl status docker.service"
    print_warning "Y más detalle con: sudo journalctl -xeu docker.service"
fi

TARGET_USER="${SUDO_USER:-$USER}"
if ! getent group docker >/dev/null 2>&1; then
    sudo groupadd docker || true
fi
sudo usermod -aG docker "$TARGET_USER"

print_info "Usuario '$TARGET_USER' agregado al grupo docker."
print_warning "Cierra y vuelve a entrar a la sesión para usar Docker sin sudo."
