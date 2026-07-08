#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
print_warning() { echo -e "${YELLOW}[WARN]${NC} $*"; }
print_success() { echo -e "${GREEN}[OK]${NC} $*"; }
die() { echo -e "${RED}Error: $*${NC}" >&2; exit 1; }

command -v sudo >/dev/null 2>&1 || die "Missing sudo"
command -v pacman >/dev/null 2>&1 || die "Missing pacman"
command -v systemctl >/dev/null 2>&1 || die "Missing systemctl; this module expects systemd on Arch Linux"

print_info "Installing OpenSSH..."
sudo pacman -S --needed --noconfirm openssh

print_info "Enabling and starting sshd.service..."
sudo systemctl enable --now sshd.service

if systemctl is-active --quiet sshd.service; then
	print_success "sshd.service is active"
else
	die "sshd.service was enabled, but systemctl does not report it active. Check: systemctl status sshd.service"
fi

if command -v ss >/dev/null 2>&1; then
	if ss -tlnp 2>/dev/null | grep -Eq '(^|[[:space:]])LISTEN[[:space:]].*:22[[:space:]]'; then
		print_success "SSH is listening on port 22"
	else
		die "Port 22 was not found in ss output. Check: sudo systemctl status sshd.service && ss -tlnp | grep ':22'"
	fi
else
	die "Cannot verify port 22 because 'ss' is not available"
fi

echo ""
echo "SSH hardening next steps (apply only after confirming a working key-based login):"
echo "  1. Copy/verify your public key in ~/.ssh/authorized_keys for the sudo user."
echo "  2. After key login works in a new session, set PasswordAuthentication no."
echo "  3. After sudo-user access works, set PermitRootLogin no."
echo "  4. Reload sshd and keep the current session open until a new login succeeds."

print_success "OpenSSH installed and sshd.service configured"
