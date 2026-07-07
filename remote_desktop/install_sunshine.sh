#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[SUNSHINE]${NC} $*"; }
print_warning() { echo -e "${YELLOW}[SUNSHINE]${NC} $*"; }
die() {
	echo -e "${RED}Error:${NC} $*" >&2
	exit 1
}

command -v yay >/dev/null 2>&1 || die "yay no está instalado. Ejecuta primero Install base -> Yay AUR helper."

print_info "Instalando Sunshine desde AUR..."
yay -S --needed --noconfirm sunshine

if command -v systemctl >/dev/null 2>&1; then
	print_info "Intentando habilitar el servicio de usuario sunshine.service..."
	systemctl --user enable --now sunshine.service 2>/dev/null ||
		print_warning "No se pudo iniciar sunshine.service todavía. Inícialo dentro de tu sesión gráfica con: systemctl --user enable --now sunshine.service"
fi

print_info "Sunshine instalado."
echo ""
echo "Siguientes pasos:"
echo "  1. Asegura que Tailscale esté autenticado: sudo tailscale up --ssh"
echo "  2. Abre la UI de Sunshine desde el túnel/host: https://<tailscale-ip-o-magicdns>:47990"
echo "  3. Instala Moonlight en tu Mac o iPhone."
echo "  4. Empareja Moonlight con Sunshine usando la IP Tailscale o MagicDNS."
echo ""
echo "Notas:"
echo "  - En VPS puede hacer falta configurar un display virtual o una sesión gráfica activa."
echo "  - Si el input no funciona, revisa permisos de /dev/uinput para Sunshine."
