#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
die() {
	echo -e "${RED}Error: $*${NC}" >&2
	exit 1
}

tmp_dir=""
sudo_keepalive_pid=""

cleanup() {
	if [ -n "$sudo_keepalive_pid" ]; then
		pkill -TERM -P "$sudo_keepalive_pid" 2>/dev/null || true
		kill "$sudo_keepalive_pid" 2>/dev/null || true
		wait "$sudo_keepalive_pid" 2>/dev/null || true
	fi
	if [ -n "$tmp_dir" ]; then
		rm -rf "$tmp_dir"
	fi
}

start_sudo_keepalive() {
	local interval="${SUDO_KEEPALIVE_INTERVAL:-30}"
	sudo -v
	while true; do
		sudo -n -v
		sleep "$interval" &
		wait "$!" || exit 0
	done &
	sudo_keepalive_pid="$!"
}

trap cleanup EXIT

if ! command -v yay >/dev/null 2>&1; then
	start_sudo_keepalive

	print_info "Instalando dependencias para compilar yay..."
	sudo pacman -S --needed --noconfirm base-devel git go

	print_info "Instalando yay..."
	tmp_dir="$(mktemp -d)"
	git clone https://aur.archlinux.org/yay.git "$tmp_dir/yay"
	(cd "$tmp_dir/yay" && makepkg -si --noconfirm)
else
	print_info "yay ya está instalado"
fi

print_info "Yay listo. Los paquetes AUR se eligen desde Desktop/Software."
