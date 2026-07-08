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

current_user_uid() {
	local user="$1"

	if [ -z "$user" ]; then
		return 0
	fi

	id -u "$user" 2>/dev/null || true
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

auto_discover_user_systemd_bus() {
	local user uid runtime_root runtime_dir bus_path
	user="$(current_user)"
	uid="$(current_user_uid "$user")"
	runtime_root="${SUNSHINE_RUNTIME_ROOT:-/run/user}"

	if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
		if [ -n "$uid" ]; then
			runtime_dir="${runtime_root%/}/$uid"
			if [ -d "$runtime_dir" ]; then
				export XDG_RUNTIME_DIR="$runtime_dir"
				print_info "Auto-detected XDG_RUNTIME_DIR: $XDG_RUNTIME_DIR"
			else
				print_warning "XDG_RUNTIME_DIR is not set and auto-detect path does not exist: $runtime_dir"
			fi
		else
			print_warning "XDG_RUNTIME_DIR is not set and the target user id could not be detected for user '${user:-unknown}'."
		fi
	fi

	if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
		if [ -n "${XDG_RUNTIME_DIR:-}" ]; then
			bus_path="$XDG_RUNTIME_DIR/bus"
			if [ -e "$bus_path" ]; then
				export DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path"
				print_info "Auto-detected DBUS_SESSION_BUS_ADDRESS: $DBUS_SESSION_BUS_ADDRESS"
			else
				print_warning "DBUS_SESSION_BUS_ADDRESS is not set and user bus socket was not found: $bus_path"
			fi
		else
			print_warning "DBUS_SESSION_BUS_ADDRESS is not set and XDG_RUNTIME_DIR is unavailable for auto-detection."
		fi
	fi
}

root_user_service_context_is_safe() {
	local user uid runtime_root expected_runtime_dir expected_bus_path
	user="$(current_user)"
	uid="$(current_user_uid "$user")"
	runtime_root="${SUNSHINE_RUNTIME_ROOT:-/run/user}"

	if [ "${EUID:-0}" -ne 0 ]; then
		return 0
	fi

	if [ -z "$user" ] || [ -z "$uid" ] || [ "$uid" = "0" ]; then
		print_warning "Sunshine must run as the desktop user, not root; skipping user service startup."
		echo "Remote access status: NOT READY (desktop user systemd bus was not selected)."
		echo "Run this installer as the desktop user, or invoke it through sudo with SUDO_USER set to the desktop account."
		return 1
	fi

	expected_runtime_dir="${runtime_root%/}/$uid"
	expected_bus_path="$expected_runtime_dir/bus"
	if [ "${XDG_RUNTIME_DIR:-}" != "$expected_runtime_dir" ] || \
		[ "${DBUS_SESSION_BUS_ADDRESS:-}" != "unix:path=$expected_bus_path" ] || \
		[ ! -e "$expected_bus_path" ]; then
		print_warning "Running as root/sudo, but the desktop user's systemd bus is not safely selected."
		echo "Remote access status: NOT READY (Sunshine user service was not started as root)."
		echo "Target desktop user: $user (uid $uid)"
		echo "Expected XDG_RUNTIME_DIR: $expected_runtime_dir"
		echo "Expected DBUS_SESSION_BUS_ADDRESS: unix:path=$expected_bus_path"
		echo "Run this installer inside the graphical session for '$user', or start that desktop session so the user bus exists."
		return 1
	fi

	return 0
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
	local user uid
	user="$(current_user)"
	uid="$(current_user_uid "$user")"

	print_info "User service context:"
	echo "  - Target user: ${user:-unknown}"
	echo "  - Target UID: ${uid:-unknown}"
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
		echo "The installer auto-detects the desktop user's /run/user/<uid>/bus when present; the user systemd bus is still unreachable."
		echo "Run this installer inside the graphical user session, or start the desktop session so XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS exist for the desktop user."
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

sunshine_config_path() {
	if [ -n "${SUNSHINE_CONFIG_PATH:-}" ]; then
		printf '%s\n' "$SUNSHINE_CONFIG_PATH"
		return 0
	fi

	local user user_home
	user="$(current_user)"
	if [ "${EUID:-0}" -eq 0 ] && [ -n "${SUDO_USER:-}" ] && [ -n "$user" ] && [ "$user" != "root" ] && command -v getent >/dev/null 2>&1; then
		user_home="$(getent passwd "$user" | awk -F: 'NR == 1 {print $6}')"
		if [ -n "$user_home" ]; then
			printf '%s/.config/sunshine/sunshine.conf\n' "$user_home"
			return 0
		fi
	fi

	if [ -n "${HOME:-}" ]; then
		printf '%s/.config/sunshine/sunshine.conf\n' "$HOME"
		return 0
	fi

	return 1
}

trim_value() {
	local value="$*"
	value="${value#"${value%%[![:space:]]*}"}"
	value="${value%"${value##*[![:space:]]}"}"
	printf '%s\n' "$value"
}

safe_origin_host() {
	local host="$1"
	local IFS=.
	local -a labels
	local label

	[ -n "$host" ] || return 1
	case "$host" in
		*'*'*|*'/'*|*':'*|*','*|*'['*|*']'*|*' '*|*'\t'*|.*|*.|*..*)
			return 1
			;;
	esac

	[ "${#host}" -le 253 ] || return 1
	read -r -a labels <<< "$host"
	[ "${#labels[@]}" -gt 0 ] || return 1
	for label in "${labels[@]}"; do
		[ -n "$label" ] || return 1
		[ "${#label}" -le 63 ] || return 1
		printf '%s\n' "$label" | grep -Eq '^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$' || return 1
	done
}

SUNSHINE_CSRF_ORIGINS=""

append_csrf_origin() {
	local origin
	origin="$(trim_value "$1")"

	[ -n "$origin" ] || return 0
	if [ -n "$SUNSHINE_CSRF_ORIGINS" ] && printf '%s\n' "$SUNSHINE_CSRF_ORIGINS" | grep -Fxq "$origin"; then
		return 0
	fi

	SUNSHINE_CSRF_ORIGINS="${SUNSHINE_CSRF_ORIGINS}${SUNSHINE_CSRF_ORIGINS:+$'\n'}${origin}"
}

append_csrf_origin_for_host() {
	local host
	host="$(trim_value "$1")"
	host="${host%.}"

	if safe_origin_host "$host"; then
		append_csrf_origin "https://${host}:47990"
	fi
}

csrf_origin_host() {
	local origin host
	origin="$(trim_value "$1")"

	case "$origin" in
		https://*:47990)
			host="${origin#https://}"
			host="${host%:47990}"
			[ -n "$host" ] || return 1
			printf '%s\n' "$host"
			;;
		*)
			return 1
			;;
	esac
}

is_ipv4_host() {
	local host="$1"
	local IFS=.
	local -a octets
	local octet

	[[ "$host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
	read -r -a octets <<< "$host"
	[ "${#octets[@]}" -eq 4 ] || return 1
	for octet in "${octets[@]}"; do
		[[ "$octet" =~ ^[0-9]+$ ]] || return 1
		[ "$octet" -ge 0 ] && [ "$octet" -le 255 ] || return 1
	done
}

is_localhost_origin_host() {
	local host="$1"

	case "$host" in
		localhost|127.*)
			is_ipv4_host "$host" 2>/dev/null || [ "$host" = "localhost" ]
			;;
		*)
			return 1
			;;
	esac
}

is_tailscale_ipv4_host() {
	local host="$1"
	local second_octet

	is_ipv4_host "$host" || return 1
	second_octet="${host#100.}"
	[ "$second_octet" != "$host" ] || return 1
	second_octet="${second_octet%%.*}"
	[ "$second_octet" -ge 64 ] && [ "$second_octet" -le 127 ]
}

is_tailscale_magic_dns_host() {
	local host="$1"

	safe_origin_host "$host" || return 1
	case "$host" in
		*.*.ts.net)
			return 0
			;;
		*)
			return 1
			;;
	esac
}

is_existing_csrf_origin_trusted() {
	local origin host
	origin="$(trim_value "$1")"

	if ! host="$(csrf_origin_host "$origin")"; then
		return 1
	fi
	safe_origin_host "$host" || return 1

	if [ -n "$SUNSHINE_CSRF_ORIGINS" ] && printf '%s\n' "$SUNSHINE_CSRF_ORIGINS" | grep -Fxq "$origin"; then
		return 0
	fi

	case "$origin" in
		https://arch:47990)
			return 0
			;;
	esac

	is_localhost_origin_host "$host" || is_tailscale_ipv4_host "$host" || is_tailscale_magic_dns_host "$host"
}

append_existing_csrf_origins() {
	local config_path="$1"
	local raw_origin origin

	[ -f "$config_path" ] || return 0
	while IFS= read -r raw_origin; do
		origin="$(trim_value "$raw_origin")"
		[ -n "$origin" ] || continue
		if is_existing_csrf_origin_trusted "$origin"; then
			append_csrf_origin "$origin"
		else
			print_warning "Dropping unsafe or malformed Sunshine csrf_allowed_origins entry: $origin"
		fi
	done < <(
		awk -F= '
			{
				key = $1
				gsub(/^[ \t]+|[ \t]+$/, "", key)
				if (key == "csrf_allowed_origins") {
					value = substr($0, index($0, "=") + 1)
					gsub(/,/, "\n", value)
					print value
				}
			}
		' "$config_path"
	)
}

append_tailscale_csrf_origins() {
	local tailscale_ip status_hosts status_host

	append_csrf_origin_for_host "arch"

	tailscale_ip="$(tailscale_ipv4)"
	if [ -n "$tailscale_ip" ]; then
		append_csrf_origin_for_host "$tailscale_ip"
	fi

	if ! command -v tailscale >/dev/null 2>&1; then
		return 0
	fi

	status_hosts="$(tailscale status --json 2>/dev/null | awk '
		/"Self"[[:space:]]*:/ { in_self = 1 }
		in_self && /"HostName"[[:space:]]*:/ {
			value = $0
			sub(/^.*"HostName"[[:space:]]*:[[:space:]]*"/, "", value)
			sub(/".*$/, "", value)
			print value
		}
		in_self && /"DNSName"[[:space:]]*:/ {
			value = $0
			sub(/^.*"DNSName"[[:space:]]*:[[:space:]]*"/, "", value)
			sub(/".*$/, "", value)
			print value
		}
		in_self && /^[[:space:]]*}/ { in_self = 0 }
	' || true)"

	if [ -z "$status_hosts" ] && [ -n "$tailscale_ip" ]; then
		status_hosts="$(tailscale status 2>/dev/null | awk -v ip="$tailscale_ip" '$1 == ip {print $2; exit}' || true)"
	fi

	if [ -z "$status_hosts" ] && command -v hostname >/dev/null 2>&1; then
		status_hosts="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
	fi

	while IFS= read -r status_host; do
		append_csrf_origin_for_host "$status_host"
	done <<< "$status_hosts"
}

write_sunshine_csrf_origins() {
	local config_path="$1"
	local joined=""
	local count=0
	local origin tmp_path

	while IFS= read -r origin; do
		[ -n "$origin" ] || continue
		joined="${joined}${joined:+,}${origin}"
		count=$((count + 1))
	done <<< "$SUNSHINE_CSRF_ORIGINS"

	[ -n "$joined" ] || return 0

	tmp_path="${config_path}.tmp.$$"
	awk '
		{
			line = $0
			sub(/^[ \t]+/, "", line)
			if (line ~ /^csrf_allowed_origins[ \t]*=/) {
				next
			}
			print
		}
	' "$config_path" > "$tmp_path"
	if [ -s "$tmp_path" ]; then
		printf '\n' >> "$tmp_path"
	fi
	printf 'csrf_allowed_origins = %s\n' "$joined" >> "$tmp_path"
	mv "$tmp_path" "$config_path"
	chmod 600 "$config_path" 2>/dev/null || print_warning "Could not set secure permissions on $config_path; check file ownership."

	print_info "Configured Sunshine CSRF allowed origins ($count): $joined"
}

configure_sunshine_csrf_allowed_origins() {
	local config_path config_dir

	if ! config_path="$(sunshine_config_path)"; then
		print_warning "Could not determine Sunshine config path; skipping CSRF allowed origins setup."
		return 0
	fi

	config_dir="$(dirname "$config_path")"
	mkdir -p "$config_dir"
	chmod 700 "$config_dir" 2>/dev/null || print_warning "Could not set secure permissions on $config_dir; check directory ownership."
	if [ ! -e "$config_path" ]; then
		: > "$config_path"
	fi
	chmod 600 "$config_path" 2>/dev/null || print_warning "Could not set secure permissions on $config_path; check file ownership."

	SUNSHINE_CSRF_ORIGINS=""
	append_tailscale_csrf_origins
	append_existing_csrf_origins "$config_path"
	write_sunshine_csrf_origins "$config_path"
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

	auto_discover_user_systemd_bus
	print_user_service_context
	if ! root_user_service_context_is_safe; then
		return
	fi
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
configure_sunshine_csrf_allowed_origins
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
