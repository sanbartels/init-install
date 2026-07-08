#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
SUNSHINE_REMOTE_ACCESS_READY=0
SUDO_PREFLIGHT_ERROR="sudo credentials are not available for non-interactive execution. Run 'sudo -v' in an interactive SSH session before launching this installer, or run it from the init-install menu where sudo preflight/cache is available."

print_info() { echo -e "${GREEN}[SUNSHINE]${NC} $*"; }
print_warning() { echo -e "${YELLOW}[SUNSHINE]${NC} $*"; }
die() {
	echo -e "${RED}Error:${NC} $*" >&2
	exit 1
}

fail_remote_access_not_ready() {
	echo -e "${RED}Remote access verification failed:${NC} Sunshine install completed, but remote access is not verified/safe yet." >&2
	echo "Remote access status remains NOT READY. Follow the diagnostics above before using Moonlight." >&2
	exit 2
}

require_cmd() {
	command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

sudo_preflight() {
	if sudo -n true >/dev/null 2>&1; then
		return 0
	fi

	die "$SUDO_PREFLIGHT_ERROR"
}

run_with_sudo() {
	sudo_preflight

	if sudo -n "$@"; then
		return 0
	fi

	local status=$?
	if ! sudo -n true >/dev/null 2>&1; then
		die "$SUDO_PREFLIGHT_ERROR"
	fi

	return "$status"
}

install_packages() {
	require_cmd yay
	require_cmd sudo
	require_cmd pacman
	sudo_preflight

	print_info "Installing Sunshine from AUR..."
	yay -S --needed --noconfirm sunshine

	print_info "Ensuring Wayland capture dependencies for Hyprland..."
	run_with_sudo pacman -S --needed --noconfirm \
		pipewire \
		wireplumber \
		xdg-desktop-portal \
		xdg-desktop-portal-hyprland
}

current_user() {
	if [ -n "${SUDO_USER:-}" ]; then
		printf '%s\n' "$SUDO_USER"
	elif [ -n "${USER:-}" ]; then
		printf '%s\n' "$USER"
	else
		id -un 2>/dev/null || true
	fi
}

enable_linger_if_possible() {
	local user
	user="$(current_user)"

	if [ -z "$user" ]; then
		print_warning "Could not detect the current user; skipping loginctl linger setup."
		return
	fi

	if command -v loginctl >/dev/null 2>&1; then
		print_info "Enabling linger for user '$user' so the Sunshine user service can survive SSH sessions..."
		run_with_sudo loginctl enable-linger "$user" || \
			print_warning "Could not enable linger automatically. Try: sudo loginctl enable-linger $user"
	else
		print_warning "loginctl is not available; if launching from SSH, enable linger manually on systemd systems."
	fi
}

sunshine_unit_exists() {
	local unit="$1"
	systemctl --user cat "$unit" >/dev/null 2>&1 || \
		systemctl --user list-unit-files "$unit" --no-legend 2>/dev/null | awk '{print $1}' | grep -qx "$unit"
}

find_sunshine_unit() {
	local unit
	for unit in app-dev.lizardbyte.app.Sunshine.service sunshine.service; do
		if sunshine_unit_exists "$unit"; then
			printf '%s\n' "$unit"
			return 0
		fi
	done

	systemctl --user list-unit-files '*Sunshine*.service' 'sunshine*.service' --no-legend 2>/dev/null | awk 'NR == 1 {print $1}'
}

print_user_service_context() {
	print_info "User service context:"
	echo "  - USER: ${USER:-unknown}"
	echo "  - XDG_RUNTIME_DIR: ${XDG_RUNTIME_DIR:-not set}"
	echo "  - DBUS_SESSION_BUS_ADDRESS: ${DBUS_SESSION_BUS_ADDRESS:-not set}"
	echo "  - Command: systemctl --user enable --now <sunshine-unit>"
}

ensure_hyprland_portal_ready() {
	local portal_unit="xdg-desktop-portal-hyprland.service"

	if ! systemctl --user show-environment >/dev/null 2>&1; then
		print_warning "User systemd bus is not available; cannot start $portal_unit before Sunshine."
		echo "Remote access status: NOT READY (Hyprland portal could not be verified)."
		echo "Run this installer inside the graphical user session or an SSH session with XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS for the desktop user."
		echo "Diagnostics to run inside the graphical user session:"
		echo "  systemctl --user status xdg-desktop-portal-hyprland.service --no-pager"
		echo "  journalctl --user -u xdg-desktop-portal-hyprland.service -b --no-pager"
		return 1
	fi

	print_info "Restarting Hyprland portal before Sunshine: $portal_unit"
	if ! systemctl --user restart "$portal_unit"; then
		print_warning "Could not restart $portal_unit; trying start instead."
		systemctl --user start "$portal_unit" || true
	fi

	if systemctl --user is-active --quiet "$portal_unit"; then
		print_info "Hyprland portal is active."
		return 0
	fi

	local portal_state
	portal_state="$(systemctl --user is-active "$portal_unit" 2>/dev/null || true)"
	[ -n "$portal_state" ] || portal_state="unknown"

	print_warning "Hyprland portal is not active after restart/start attempt: $portal_unit ($portal_state)."
	echo "Remote access status: NOT READY (Hyprland portal is $portal_state)."
	echo "Diagnostics for Hyprland portal readiness:"
	echo "  systemctl --user status xdg-desktop-portal-hyprland.service --no-pager"
	echo "  journalctl --user -u xdg-desktop-portal-hyprland.service -b --no-pager"
	echo "  systemctl --user status pipewire wireplumber xdg-desktop-portal --no-pager"
	systemctl --user status "$portal_unit" --no-pager || true
	return 1
}

tailscale_ipv4() {
	if command -v tailscale >/dev/null 2>&1; then
		tailscale ip -4 2>/dev/null | awk 'NR == 1 {print $1}'
	fi
}

diagnose_sunshine_listeners() {
	if ! command -v ss >/dev/null 2>&1; then
		print_warning "Cannot verify Sunshine listeners because 'ss' is not available."
		echo "Remote access status: NOT READY (listener exposure could not be verified)."
		return 1
	fi

	local listener_lines
	listener_lines="$(ss -tlnp 2>/dev/null | grep -E '(^|[[:space:]])LISTEN[[:space:]].*:(47984|47989|47990)([[:space:]]|$)' || true)"

	if [ -z "$listener_lines" ]; then
		print_warning "Sunshine service started, but no TCP listener was found on 47984/47989/47990."
		echo "Remote access status: NOT READY (no Sunshine listener detected)."
		echo "Diagnostics to run inside the graphical user session:"
		echo "  systemctl --user status app-dev.lizardbyte.app.Sunshine.service --no-pager"
		echo "  journalctl --user -u app-dev.lizardbyte.app.Sunshine.service -b --no-pager"
		echo "  systemctl --user status pipewire wireplumber xdg-desktop-portal-hyprland --no-pager"
		echo "  ss -tlnp | grep -E ':(47984|47989|47990)'"
		return 1
	fi

	local tailscale_ip
	tailscale_ip="$(tailscale_ipv4)"
	if [ -z "$tailscale_ip" ]; then
		print_warning "Sunshine listeners exist, but Tailscale IP could not be detected; private-only exposure was not verified."
		echo "Remote access status: NOT READY (run 'tailscale ip -4' and verify Sunshine binds only to that address)."
		printf '%s\n' "$listener_lines"
		return 1
	fi

	local unsafe_bindings=""
	local line local_addr
	while IFS= read -r line; do
		local_addr="$(printf '%s\n' "$line" | awk '{print $4}')"
		case "$local_addr" in
			"$tailscale_ip":47984|"$tailscale_ip":47989|"$tailscale_ip":47990|"[$tailscale_ip]":47984|"[$tailscale_ip]":47989|"[$tailscale_ip]":47990)
				;;
			*)
				unsafe_bindings="${unsafe_bindings}${line}\n"
				;;
		esac
	done <<< "$listener_lines"

	if [ -n "$unsafe_bindings" ]; then
		print_warning "Sunshine listeners exist, but they are not bound to the Tailscale IP only."
		echo "Remote access status: NOT READY (avoid public exposure before using Moonlight)."
		echo "Unsafe or unverified listener bindings:"
		printf '%b' "$unsafe_bindings"
		echo "Expected local address: ${tailscale_ip}:<sunshine-port>"
		return 1
	fi

	print_info "Sunshine listeners are bound to Tailscale IP $tailscale_ip only."
	echo "Remote access status: READY (Tailscale-only listener exposure verified)."
	return 0
}

enable_sunshine_service() {
	if ! command -v systemctl >/dev/null 2>&1; then
		print_warning "systemctl is not available; start Sunshine manually inside your Wayland session."
		return
	fi

	print_user_service_context
	systemctl --user daemon-reload 2>/dev/null || true
	if ! ensure_hyprland_portal_ready; then
		return
	fi

	local unit
	unit="$(find_sunshine_unit || true)"

	if [ -z "$unit" ]; then
		print_warning "Could not find a Sunshine user unit. Expected: app-dev.lizardbyte.app.Sunshine.service"
		echo "Try inside the graphical user session: systemctl --user list-unit-files '*Sunshine*.service'"
		return
	fi

	print_info "Enabling and starting Sunshine user service: $unit"
	if systemctl --user enable --now "$unit"; then
		if diagnose_sunshine_listeners; then
			SUNSHINE_REMOTE_ACCESS_READY=1
		fi
	else
		die "Could not enable/start $unit. Run inside the graphical user session and inspect: systemctl --user status $unit --no-pager"
	fi
}

install_packages
enable_linger_if_possible
enable_sunshine_service

if [ "$SUNSHINE_REMOTE_ACCESS_READY" -eq 1 ]; then
	print_info "Sunshine installed and Tailscale-only remote access was verified."
else
	print_warning "Sunshine installed, but remote access is NOT READY/VERIFIED yet. Follow the diagnostics below before using Moonlight."
fi
echo ""
echo "Next steps:"
echo "  1. Make sure Tailscale is authenticated: sudo tailscale up --ssh"
echo "  2. Open the Sunshine UI through Tailscale: https://<tailscale-ip-or-magicdns>:47990"
echo "  3. Install Moonlight on your Mac or iPhone."
echo "  4. Pair Moonlight with Sunshine using the Tailscale IP or MagicDNS name."
echo ""
echo "Notes:"
echo "  - Sunshine must run as the desktop user, not as root."
echo "  - Hyprland capture expects pipewire, wireplumber, and xdg-desktop-portal-hyprland in the user session."
echo "  - If input does not work, check /dev/uinput permissions for Sunshine."
echo "  - If the service is active but port 47990 is closed, inspect the journal commands printed above."

if [ "$SUNSHINE_REMOTE_ACCESS_READY" -ne 1 ]; then
	fail_remote_access_not_ready
fi
