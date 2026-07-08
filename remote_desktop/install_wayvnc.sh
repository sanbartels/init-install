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

command -v sudo >/dev/null 2>&1 || die "Missing sudo"
command -v pacman >/dev/null 2>&1 || die "Missing pacman; this module is for Arch Linux"

print_info "Installing wayvnc from official Arch repositories..."
sudo pacman -S --needed --noconfirm wayvnc

if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
	print_warning "XDG_RUNTIME_DIR is not set in this shell. Start wayvnc from the active Hyprland user session, or export /run/user/$(id -u)."
fi

if [ -z "${WAYLAND_DISPLAY:-}" ]; then
	print_warning "WAYLAND_DISPLAY is not set in this shell. Check the active display with: ls \"${XDG_RUNTIME_DIR:-/run/user/$(id -u)}\"/wayland-*"
fi

TAILSCALE_IP=""
if command -v tailscale >/dev/null 2>&1; then
	TAILSCALE_IP="$(tailscale ip -4 2>/dev/null | awk 'NR == 1 {print $1}')"
fi

print_info "wayvnc installed."
echo ""
echo "Safe Hyprland/Tailscale launch path:"
echo "  1. Connect the VPS to Tailscale: sudo tailscale up --ssh"
echo "  2. Start or attach to the active Hyprland user session."
echo "  3. Export the active Wayland runtime before launching wayvnc:"
echo ""
echo "     export XDG_RUNTIME_DIR=\"\${XDG_RUNTIME_DIR:-/run/user/\$(id -u)}\""
echo "     export WAYLAND_DISPLAY=\"\${WAYLAND_DISPLAY:-wayland-1}\""
echo "     export XKB_DEFAULT_LAYOUT=us"
echo "     export XKB_DEFAULT_VARIANT="
echo "     export XKB_DEFAULT_OPTIONS="
echo "     wayvnc --keyboard=us ${TAILSCALE_IP:-<tailscale-ip>}:5900"
echo ""
echo "Input validation notes:"
echo "  - Test keyboard input in nano or another real editor. Raw cat can show ^H or ANSI/control sequences and produce misleading results."
echo "  - Keep the Hyprland keyboard layout simple for remote sessions: kb_layout=us, empty variant/options."
echo "  - If Ghostty looks dark or blurred in VNC, disable background opacity and blur for remote sessions."
echo ""
print_warning "No password/display configuration is created automatically; wayvnc remains a simple fallback."
