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

command -v sudo >/dev/null 2>&1 || die "Falta sudo"
command -v pacman >/dev/null 2>&1 || die "Falta pacman"

print_info "Actualizando sistema base..."
sudo pacman -Syu --noconfirm

print_info "Instalando paquetes base..."
sudo pacman -S --needed --noconfirm \
	base \
	base-devel \
	linux \
	linux-firmware \
	grub \
	efibootmgr \
	sudo \
	git \
	curl \
	wget \
	jq \
	nano \
	less \
	unzip \
	7zip \
	tree \
	dosfstools \
	exfatprogs \
	zram-generator
