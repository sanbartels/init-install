#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SERVICE_NAME="wayvnc.service"
MANAGED_PORT="5900"
PROBE_PORT="5901"
LAUNCHER_PATH="$HOME/.local/bin/init-install-wayvnc"
USER_UNIT_DIR="$HOME/.config/systemd/user"
SERVICE_PATH="$USER_UNIT_DIR/$SERVICE_NAME"
SUNSHINE_ALIAS="$USER_UNIT_DIR/sunshine.service"
SUNSHINE_UNITS=(app-dev.lizardbyte.app.Sunshine.service sunshine.service)
PROBE_PID=""
ROLLBACK_PID=""
MANUAL_5900_STOPPED=0

print_info() { echo -e "${GREEN}[WAYVNC]${NC} $*"; }
print_warning() { echo -e "${YELLOW}[WAYVNC]${NC} $*"; }
die() {
	echo -e "${RED}Error:${NC} $*" >&2
	exit 1
}

require_cmd() {
	command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

sudo_preflight() {
	if ! command -v sudo >/dev/null 2>&1; then
		die "Privileged remediation is required, but sudo is not installed. Install missing prerequisites manually, then rerun this installer."
	fi
	if ! sudo -n true >/dev/null 2>&1; then
		die "Privileged remediation is required, but non-interactive sudo is unavailable. Run 'sudo -v' in an interactive SSH session, then rerun this installer before the sudo cache expires."
	fi
}

package_installed() {
	local package="$1"
	pacman -Qi "$package" >/dev/null 2>&1
}

tailscaled_ready() {
	systemctl is-enabled --quiet tailscaled.service >/dev/null 2>&1 && \
		systemctl is-active --quiet tailscaled.service >/dev/null 2>&1
}

tailscale_ipv4() {
	tailscale ip -4 2>/dev/null | awk 'NR == 1 {print $1}'
}

listener_lines_for_port() {
	local port="$1"
	ss -H -ltnp 2>/dev/null | awk -v port="$port" '$1 == "LISTEN" && $4 ~ ":" port "$" {print}' || true
}

line_has_pid() {
	local line="$1" expected_pid="$2"
	case "$line" in
		*"pid=$expected_pid,"*|*"pid=$expected_pid)"*) return 0 ;;
		*) return 1 ;;
	esac
}

extract_first_pid() {
	awk 'match($0, /pid=[0-9]+/) {print substr($0, RSTART + 4, RLENGTH - 4); exit}'
}

service_main_pid() {
	systemctl --user show "$SERVICE_NAME" --property=MainPID --value 2>/dev/null | awk 'NR == 1 {print $1}'
}

cleanup_probe() {
	if [ -n "${PROBE_PID:-}" ] && kill -0 "$PROBE_PID" 2>/dev/null; then
		kill "$PROBE_PID" 2>/dev/null || true
		wait "$PROBE_PID" 2>/dev/null || true
	fi
}

cleanup_failed_service() {
	systemctl --user disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
}

trap cleanup_probe EXIT

install_prerequisites() {
	require_cmd pacman
	require_cmd systemctl
	local missing_packages=()
	local package
	for package in wayvnc tailscale; do
		if ! package_installed "$package"; then
			missing_packages+=("$package")
		fi
	done
	if [ "${#missing_packages[@]}" -gt 0 ]; then
		print_info "Installing missing WayVNC/Tailscale prerequisites: ${missing_packages[*]}"
		sudo_preflight
		sudo -n pacman -S --needed --noconfirm "${missing_packages[@]}" || \
			die "Failed to install missing packages after sudo preflight. Re-run 'sudo -v' in an interactive SSH session, then retry before the sudo cache expires."
	else
		print_info "WayVNC and Tailscale packages are already installed; skipping pacman."
	fi
	if tailscaled_ready; then
		print_info "tailscaled.service is already enabled and active; skipping privileged system service setup."
	else
		print_info "Enabling and starting tailscaled.service for private Tailscale binding..."
		sudo_preflight
		sudo -n systemctl enable --now tailscaled.service || \
			die "Failed to enable/start tailscaled.service after sudo preflight. Re-run 'sudo -v' in an interactive SSH session, then retry before the sudo cache expires."
	fi
}

preflight_required_state() {
	local cmd tailscale_ip
	for cmd in systemctl tailscale wayvnc hyprctl ss ps awk grep python3 mktemp readlink dirname id kill sleep; do
		require_cmd "$cmd"
	done
	for package in wayvnc tailscale; do
		pacman -Qi "$package" >/dev/null 2>&1 || die "Required package is not installed after prerequisite step: $package"
	done
	systemctl --user show-environment >/dev/null 2>&1 || die "User systemd bus is unavailable. Run this from the desktop user session or enable/start the user manager before changing remote desktop services."
	tailscale_ip="$(tailscale_ipv4)"
	[ -n "$tailscale_ip" ] || die "No Tailscale IPv4 detected. Run: sudo tailscale up --ssh"
	case "$LAUNCHER_PATH$SERVICE_PATH" in
		*$'\n'*|*$'\r'*|*$'\t'*|*' '*) die "Unsupported HOME path for systemd unit generation: $HOME" ;;
	esac
}

preflight_managed_path() {
	local path="$1" parent
	parent="$(dirname "$path")"
	[ ! -L "$path" ] || die "Refusing to overwrite symlink: $path"
	[ ! -e "$path" ] || [ -f "$path" ] || die "Refusing to overwrite non-regular file: $path"
	mkdir -p "$parent"
	[ -d "$parent" ] || die "Cannot create managed path parent: $parent"
}

write_launcher() {
	preflight_managed_path "$LAUNCHER_PATH"
	local tmp_path
	tmp_path="$(mktemp "${LAUNCHER_PATH}.tmp.XXXXXX")"
	cat > "$tmp_path" <<'LAUNCHER'
#!/bin/bash
set -euo pipefail
log() { printf '[init-install-wayvnc] %s\n' "$*" >&2; }
fail() {
	printf '[init-install-wayvnc] ERROR: %s\n' "$*" >&2
	exit 1
}
require_cmd() {
	command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}
instances_tsv() {
	hyprctl instances -j 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
if not isinstance(data, list):
    sys.exit(1)
for item in data:
    if not isinstance(item, dict):
        continue
    inst = item.get("instance") or item.get("signature")
    wl = item.get("wl_socket") or item.get("waylandSocket") or item.get("wayland_socket")
    if isinstance(inst, str) and isinstance(wl, str) and inst and wl:
        print(f"{inst}\t{wl}")
'
}
monitor_has_virtual_1() {
	hyprctl monitors -j 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
if not isinstance(data, list):
    sys.exit(1)
for item in data:
    if isinstance(item, dict) and item.get("name") == "Virtual-1":
        sys.exit(0)
sys.exit(1)
'
}
select_session() {
	local attempt runtime candidates instance wl_socket sleep_seconds session_attempts
	session_attempts="${WAYVNC_SESSION_ATTEMPTS:-30}"
	runtime="${XDG_RUNTIME_DIR:-}"
	if [ -z "$runtime" ] || [ ! -d "$runtime" ]; then
		runtime="/run/user/$(id -u)"
	fi
	export XDG_RUNTIME_DIR="$runtime"
	unset HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY
	for attempt in $(seq 1 "$session_attempts"); do
		candidates="$(instances_tsv || true)"
		while IFS=$'\t' read -r instance wl_socket; do
			[ -n "$instance" ] && [ -n "$wl_socket" ] || continue
			[ -S "$runtime/$wl_socket" ] || continue
			export HYPRLAND_INSTANCE_SIGNATURE="$instance"
			export WAYLAND_DISPLAY="$wl_socket"
			if monitor_has_virtual_1; then
				printf '%s:%s\n' "$wl_socket" "Virtual-1"
				return 0
			fi
		done <<< "$candidates"
		sleep_seconds=$((attempt < 10 ? 2 : 5))
		log "Waiting for an active Hyprland instance with a valid Wayland socket and Virtual-1 in $runtime (attempt $attempt/$session_attempts)..."
		sleep "$sleep_seconds"
	done
	fail "No active Hyprland instance from 'hyprctl instances -j' had an existing Wayland socket and Virtual-1. Run: hyprctl instances -j && hyprctl monitors -j"
}
for cmd in tailscale wayvnc hyprctl awk python3 grep id sleep; do
	require_cmd "$cmd"
done
bind_port="${WAYVNC_BIND_PORT:-5900}"
case "$bind_port" in *[!0-9]*|"") fail "Invalid WAYVNC_BIND_PORT: $bind_port" ;; esac
tailscale_ip="$(tailscale ip -4 2>/dev/null | awk 'NR == 1 {print $1}')"
[ -n "$tailscale_ip" ] || fail "No Tailscale IPv4 detected. Run: sudo systemctl enable --now tailscaled.service && sudo tailscale up --ssh"
session_target="$(select_session)"
wayland_display="${session_target%%:*}"
output_name="${session_target#*:}"
export WAYLAND_DISPLAY="$wayland_display"
export XKB_DEFAULT_LAYOUT=us
export XKB_DEFAULT_VARIANT=
export XKB_DEFAULT_OPTIONS=
if [ "${WAYVNC_VALIDATE_ONLY:-0}" = "1" ]; then
	log "Validated WayVNC target ${WAYLAND_DISPLAY}/${output_name} on ${tailscale_ip}:${bind_port}"
	exit 0
fi
log "Starting WayVNC on ${tailscale_ip}:${bind_port} for ${WAYLAND_DISPLAY}/${output_name} with keyboard layout us"
exec wayvnc -L info --keyboard=us --output="$output_name" "${tailscale_ip}:${bind_port}"
LAUNCHER
	chmod 0755 "$tmp_path"
	mv -f "$tmp_path" "$LAUNCHER_PATH"
	print_info "Installed managed WayVNC launcher: $LAUNCHER_PATH"
}

write_service() {
	preflight_managed_path "$SERVICE_PATH"
	local tmp_path
	tmp_path="$(mktemp "${SERVICE_PATH}.tmp.XXXXXX")"
	cat > "$tmp_path" <<SERVICE
[Unit]
Description=WayVNC bound to Tailscale for the active Hyprland session
After=graphical-session.target
Wants=graphical-session.target
StartLimitIntervalSec=300
StartLimitBurst=6
[Service]
Type=simple
ExecStart=$LAUNCHER_PATH
Restart=on-failure
RestartSec=10s
RestartSteps=5
RestartMaxDelaySec=60s
[Install]
WantedBy=default.target
SERVICE
	chmod 0644 "$tmp_path"
	mv -f "$tmp_path" "$SERVICE_PATH"
	print_info "Installed systemd user service: $SERVICE_PATH"
}

validate_launcher_session() {
	WAYVNC_VALIDATE_ONLY=1 WAYVNC_BIND_PORT="$PROBE_PORT" "$LAUNCHER_PATH"
}

preflight_port_5900_state() {
	local lines line pid owner current_user main_pid
	lines="$(listener_lines_for_port "$MANAGED_PORT")"
	[ -n "$lines" ] || return 0
	current_user="$(id -un 2>/dev/null || true)"
	main_pid="$(service_main_pid || true)"
	while IFS= read -r line; do
		[ -n "$line" ] || continue
		if [ -n "$main_pid" ] && [ "$main_pid" != "0" ] && line_has_pid "$line" "$main_pid"; then
			continue
		fi
		pid="$(printf '%s\n' "$line" | extract_first_pid)"
		owner="$(ps -o user= -p "$pid" 2>/dev/null | awk 'NR == 1 {print $1}')"
		case "$line" in
			*wayvnc*) [ "$owner" = "$current_user" ] && continue ;;
		esac
		die "Port $MANAGED_PORT is already held by an unrelated listener; refusing to stop it: $line"
	done <<< "$lines"
}

verify_listener_exact() {
	local port="$1" expected_pid="$2" label="$3" tailscale_ip lines unsafe line local_addr saw_expected=0 attempt
	tailscale_ip="$(tailscale_ipv4)"
	[ -n "$tailscale_ip" ] || { echo "Cannot verify $label because Tailscale IPv4 is unavailable." >&2; return 1; }
	lines=""
	for attempt in $(seq 1 45); do
		lines="$(listener_lines_for_port "$port")"
		[ -n "$lines" ] && break
		sleep 2
	done
	[ -n "$lines" ] || { echo "$label did not open TCP port $port. Inspect: journalctl --user -u $SERVICE_NAME -b --no-pager" >&2; return 1; }
	unsafe=""
	while IFS= read -r line; do
		local_addr="$(printf '%s\n' "$line" | awk '{print $4}')"
		case "$local_addr" in
			"$tailscale_ip:$port"|"[$tailscale_ip]:$port") ;;
			*) unsafe="${unsafe}${line}\n"; continue ;;
		esac
		if line_has_pid "$line" "$expected_pid"; then
			saw_expected=1
		else
			unsafe="${unsafe}${line}\n"
		fi
	done <<< "$lines"
	if [ -n "$unsafe" ] || [ "$saw_expected" -ne 1 ]; then
		echo "$label listener is not owned by expected PID $expected_pid on the current Tailscale IPv4 only:" >&2
		printf '%b' "${unsafe:-$lines\n}" >&2
		return 1
	fi
	print_info "$label listener verified on Tailscale only: ${tailscale_ip}:${port} (pid $expected_pid)"
}

run_probe() {
	print_info "Running reversible WayVNC probe on private port $PROBE_PORT before stopping existing remote desktop paths..."
	WAYVNC_BIND_PORT="$PROBE_PORT" "$LAUNCHER_PATH" &
	PROBE_PID="$!"
	if ! verify_listener_exact "$PROBE_PORT" "$PROBE_PID" "WayVNC probe"; then
		cleanup_probe
		die "WayVNC probe failed; Sunshine and existing port $MANAGED_PORT processes were left untouched."
	fi
	cleanup_probe
	PROBE_PID=""
}

wait_for_port_release() {
	local port="$1" timeout_seconds="$2" elapsed=0 lines
	while [ "$elapsed" -lt "$timeout_seconds" ]; do
		lines="$(listener_lines_for_port "$port")"
		[ -z "$lines" ] && return 0
		sleep 1
		elapsed=$((elapsed + 1))
	done
	echo "Port $port did not release within ${timeout_seconds}s. Remaining listeners:" >&2
	listener_lines_for_port "$port" >&2
	return 1
}

release_port_5900() {
	local lines line pid owner current_user
	current_user="$(id -un 2>/dev/null || true)"
	systemctl --user stop "$SERVICE_NAME" >/dev/null 2>&1 || true
	lines="$(listener_lines_for_port "$MANAGED_PORT")"
	while IFS= read -r line; do
		[ -n "$line" ] || continue
		pid="$(printf '%s\n' "$line" | extract_first_pid)"
		owner="$(ps -o user= -p "$pid" 2>/dev/null | awk 'NR == 1 {print $1}')"
		if [ -n "$pid" ] && [ "$owner" = "$current_user" ]; then
			case "$line" in
				*wayvnc*)
					print_info "Stopping current user's manual WayVNC listener on port $MANAGED_PORT (pid $pid)."
					kill "$pid" 2>/dev/null || true
					MANUAL_5900_STOPPED=1
					;;
				*) die "Port $MANAGED_PORT is held by a non-WayVNC process; refusing to kill it: $line" ;;
			esac
		else
			die "Port $MANAGED_PORT is held by another user or unknown PID; refusing to kill it: $line"
		fi
	done <<< "$lines"
	wait_for_port_release "$MANAGED_PORT" "${WAYVNC_PORT_RELEASE_TIMEOUT:-20}" || return 1
}

attempt_rollback_5900() {
	print_warning "Attempting rollback: starting the validated WayVNC launcher manually on port $MANAGED_PORT."
	WAYVNC_BIND_PORT="$MANAGED_PORT" "$LAUNCHER_PATH" &
	ROLLBACK_PID="$!"
	if verify_listener_exact "$MANAGED_PORT" "$ROLLBACK_PID" "Rollback WayVNC"; then
		print_warning "Rollback WayVNC is running as pid $ROLLBACK_PID. Manage it manually or rerun the installer after fixing the service failure."
		return 0
	fi
	if kill -0 "$ROLLBACK_PID" 2>/dev/null; then
		kill "$ROLLBACK_PID" 2>/dev/null || true
		wait "$ROLLBACK_PID" 2>/dev/null || true
	fi
	print_warning "Rollback WayVNC failed. Use SSH and inspect: journalctl --user -u $SERVICE_NAME -b --no-pager"
	return 1
}

fail_after_port_mutation() {
	local message="$1"
	cleanup_failed_service
	if [ "$MANUAL_5900_STOPPED" -eq 1 ]; then
		attempt_rollback_5900 || true
	fi
	die "$message"
}

start_managed_service() {
	local main_pid
	systemctl --user daemon-reload
	if ! release_port_5900; then
		fail_after_port_mutation "Could not release port $MANAGED_PORT for managed WayVNC."
	fi
	if ! systemctl --user enable --now "$SERVICE_NAME"; then
		fail_after_port_mutation "Could not enable/start $SERVICE_NAME."
	fi
	main_pid="$(service_main_pid || true)"
	[ -n "$main_pid" ] && [ "$main_pid" != "0" ] || fail_after_port_mutation "Could not determine $SERVICE_NAME MainPID after start."
	if ! verify_listener_exact "$MANAGED_PORT" "$main_pid" "Managed WayVNC service"; then
		fail_after_port_mutation "Managed WayVNC listener verification failed."
	fi
}

sunshine_unit_exists() {
	local unit="$1"
	systemctl --user list-unit-files "$unit" --no-legend 2>/dev/null | awk '{print $1}' | grep -qx "$unit" || \
		systemctl --user status "$unit" --no-pager >/dev/null 2>&1
}

verify_sunshine_listeners_gone() {
	local listeners
	listeners="$(ss -H -ltnp 2>/dev/null | awk '$1 == "LISTEN" && $4 ~ /:(47984|47989|47990)$/ {print}' || true)"
	[ -z "$listeners" ] || die "Sunshine retirement failed; listeners remain on 47984/47989/47990:
$listeners"
}

retire_sunshine_services() {
	print_info "Disabling Sunshine user services after managed WayVNC was proven. Package/config/credentials/apps/logs/state are preserved."
	local unit
	for unit in "${SUNSHINE_UNITS[@]}"; do
		if sunshine_unit_exists "$unit"; then
			systemctl --user disable --now "$unit" || die "Could not disable/stop Sunshine unit: $unit"
		fi
	done
	if [ -L "$SUNSHINE_ALIAS" ]; then
		local alias_target
		alias_target="$(readlink "$SUNSHINE_ALIAS" 2>/dev/null || true)"
		case "$alias_target" in
			/usr/lib/systemd/user/app-dev.lizardbyte.app.Sunshine.service|/usr/lib/systemd/user/sunshine.service|app-dev.lizardbyte.app.Sunshine.service|../app-dev.lizardbyte.app.Sunshine.service)
				rm -f -- "$SUNSHINE_ALIAS"
				print_info "Removed managed Sunshine alias symlink: $SUNSHINE_ALIAS -> $alias_target"
				;;
			*) die "Refusing to remove unexpected sunshine.service symlink target: $alias_target" ;;
		esac
	elif [ -e "$SUNSHINE_ALIAS" ]; then
		die "Refusing to remove non-symlink Sunshine user unit: $SUNSHINE_ALIAS"
	fi
	verify_sunshine_listeners_gone
}

install_prerequisites
preflight_required_state
write_launcher
write_service
validate_launcher_session
preflight_port_5900_state
run_probe
start_managed_service
retire_sunshine_services

print_info "WayVNC is installed as the normal remote desktop path."
cat <<EOF

Connect through Tailscale only: <current-tailscale-ip>:5900
Recovery commands:
  systemctl --user status $SERVICE_NAME --no-pager
  journalctl --user -u $SERVICE_NAME -b --no-pager
  systemctl --user restart $SERVICE_NAME
  systemctl --user disable --now $SERVICE_NAME

Sunshine is preserved as rollback material but disabled in the normal path.
EOF
