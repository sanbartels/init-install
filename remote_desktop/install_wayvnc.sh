#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SERVICE_NAME="wayvnc.service"
MANAGED_PORT="5900"
PROBE_PORT="5901"
SOCKET_NAMESPACE_NAME="init-install-wayvnc"
LAUNCHER_PATH="$HOME/.local/bin/init-install-wayvnc"
USER_UNIT_DIR="$HOME/.config/systemd/user"
SERVICE_PATH="$USER_UNIT_DIR/$SERVICE_NAME"
SUNSHINE_ALIAS="$USER_UNIT_DIR/sunshine.service"
SUNSHINE_UNITS=(app-dev.lizardbyte.app.Sunshine.service sunshine.service)
PROBE_PID=""
PROBE_SOCKET_PATH=""
ROLLBACK_PID=""
ROLLBACK_SOCKET_PATH=""
MANUAL_5900_STOPPED=0
TRANSACTION_ACTIVE=0
TRANSACTION_SUCCESS=0
LAUNCHER_EXISTED=0
LAUNCHER_BACKUP_PATH=""
MANAGED_LAUNCHER_HASH=""
SERVICE_EXISTED=0
SERVICE_BACKUP_PATH=""
MANAGED_SERVICE_HASH=""
SERVICE_WAS_ENABLED=0
SERVICE_WAS_ACTIVE=0
SUNSHINE_RETIREMENT_ACTIVE=0
SUNSHINE_RETIREMENT_SUCCESS=0
SUNSHINE_ALIAS_TARGET=""
SUNSHINE_ALIAS_REMOVED=0
SUNSHINE_UNIT_NAMES=()
SUNSHINE_UNIT_WAS_ENABLED=()
SUNSHINE_UNIT_WAS_ACTIVE=()

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

runtime_dir_value() {
	local runtime="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
	case "$runtime" in
		/*) ;;
		*) die "XDG_RUNTIME_DIR must be an absolute active user runtime directory: $runtime" ;;
	esac
	case "$runtime" in
		*$'\n'*|*$'\r'*|*$'\t'*|*' '*) die "XDG_RUNTIME_DIR contains unsafe whitespace: $runtime" ;;
	esac
	[ ! -L "$runtime" ] || die "XDG_RUNTIME_DIR must not be a symlink: $runtime"
	[ -d "$runtime" ] || die "XDG_RUNTIME_DIR does not exist: $runtime"
	[ -O "$runtime" ] || die "XDG_RUNTIME_DIR is not owned by the current user: $runtime"
	printf '%s\n' "$runtime"
}

canonical_path() {
	python3 - "$1" <<'PY'
import os, sys
print(os.path.realpath(sys.argv[1]))
PY
}

file_hash() {
	python3 - "$1" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
}

snapshot_managed_file() {
	local path="$1" role="$2" backup_var="$3" existed_var="$4"
	[ ! -L "$path" ] || die "Refusing to overwrite symlinked $role path: $path"
	if [ -e "$path" ]; then
		[ -f "$path" ] || die "Refusing to overwrite non-regular $role path: $path"
		local backup_path
		backup_path="$(mktemp)"
		cp -p "$path" "$backup_path"
		printf -v "$backup_var" '%s' "$backup_path"
		printf -v "$existed_var" '%s' 1
	else
		printf -v "$backup_var" '%s' ""
		printf -v "$existed_var" '%s' 0
	fi
}

restore_managed_file() {
	local path="$1" role="$2" backup_path="$3" existed="$4" managed_hash="$5" mode="$6" current_hash
	[ -n "$managed_hash" ] || return 0
	if [ ! -e "$path" ]; then
		return 0
	fi
	current_hash="$(file_hash "$path" 2>/dev/null || true)"
	if [ "$current_hash" != "$managed_hash" ]; then
		print_warning "Current $role no longer matches installed managed content; preserving it: $path"
		return 1
	fi
	if [ "$existed" -eq 1 ] && [ -n "$backup_path" ]; then
		install -m "$mode" "$backup_path" "$path"
		print_warning "Restored previous $role: $path"
	else
		rm -f -- "$path"
		print_warning "Removed newly installed $role: $path"
	fi
}

cleanup_transaction_backups() {
	rm -f -- "${LAUNCHER_BACKUP_PATH:-}" "${SERVICE_BACKUP_PATH:-}" 2>/dev/null || true
}

capture_service_state() {
	if systemctl --user is-enabled --quiet "$SERVICE_NAME" >/dev/null 2>&1; then
		SERVICE_WAS_ENABLED=1
	else
		SERVICE_WAS_ENABLED=0
	fi
	if systemctl --user is-active --quiet "$SERVICE_NAME" >/dev/null 2>&1; then
		SERVICE_WAS_ACTIVE=1
	else
		SERVICE_WAS_ACTIVE=0
	fi
}

restore_service_state() {
	systemctl --user daemon-reload >/dev/null 2>&1 || true
	if [ "$SERVICE_WAS_ENABLED" -eq 1 ] && [ "$SERVICE_WAS_ACTIVE" -eq 1 ]; then
		systemctl --user enable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
	elif [ "$SERVICE_WAS_ENABLED" -eq 1 ]; then
		systemctl --user enable "$SERVICE_NAME" >/dev/null 2>&1 || true
	elif [ "$SERVICE_WAS_ACTIVE" -eq 1 ]; then
		systemctl --user start "$SERVICE_NAME" >/dev/null 2>&1 || true
	else
		systemctl --user disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
	fi
}

rollback_managed_files() {
	[ "$TRANSACTION_ACTIVE" -eq 1 ] || return 0
	[ "$TRANSACTION_SUCCESS" -ne 1 ] || return 0
	print_warning "Transactional rollback: restoring previous WayVNC launcher/unit and service state."
	systemctl --user disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
	restore_managed_file "$SERVICE_PATH" "WayVNC service unit" "$SERVICE_BACKUP_PATH" "$SERVICE_EXISTED" "$MANAGED_SERVICE_HASH" 0644 || true
	restore_managed_file "$LAUNCHER_PATH" "WayVNC launcher" "$LAUNCHER_BACKUP_PATH" "$LAUNCHER_EXISTED" "$MANAGED_LAUNCHER_HASH" 0755 || true
	restore_service_state
}

capture_sunshine_service_states() {
	local unit
	SUNSHINE_UNIT_NAMES=()
	SUNSHINE_UNIT_WAS_ENABLED=()
	SUNSHINE_UNIT_WAS_ACTIVE=()
	for unit in "${SUNSHINE_UNITS[@]}"; do
		if sunshine_unit_exists "$unit"; then
			SUNSHINE_UNIT_NAMES+=("$unit")
			if systemctl --user is-enabled --quiet "$unit" >/dev/null 2>&1; then
				SUNSHINE_UNIT_WAS_ENABLED+=(1)
			else
				SUNSHINE_UNIT_WAS_ENABLED+=(0)
			fi
			if systemctl --user is-active --quiet "$unit" >/dev/null 2>&1; then
				SUNSHINE_UNIT_WAS_ACTIVE+=(1)
			else
				SUNSHINE_UNIT_WAS_ACTIVE+=(0)
			fi
		fi
	done
	SUNSHINE_RETIREMENT_ACTIVE=1
}

restore_sunshine_retirement() {
	local index unit was_enabled was_active
	[ "$SUNSHINE_RETIREMENT_ACTIVE" -eq 1 ] || return 0
	[ "$SUNSHINE_RETIREMENT_SUCCESS" -ne 1 ] || return 0
	print_warning "Sunshine retirement did not complete; restoring its previous user-service state while keeping verified WayVNC available."
	if [ "$SUNSHINE_ALIAS_REMOVED" -eq 1 ] && [ ! -e "$SUNSHINE_ALIAS" ] && [ ! -L "$SUNSHINE_ALIAS" ]; then
		ln -s "$SUNSHINE_ALIAS_TARGET" "$SUNSHINE_ALIAS" || true
	fi
	systemctl --user daemon-reload >/dev/null 2>&1 || true
	for index in "${!SUNSHINE_UNIT_NAMES[@]}"; do
		unit="${SUNSHINE_UNIT_NAMES[$index]}"
		was_enabled="${SUNSHINE_UNIT_WAS_ENABLED[$index]}"
		was_active="${SUNSHINE_UNIT_WAS_ACTIVE[$index]}"
		if [ "$was_enabled" -eq 1 ] && [ "$was_active" -eq 1 ]; then
			systemctl --user enable --now "$unit" >/dev/null 2>&1 || true
		elif [ "$was_enabled" -eq 1 ]; then
			systemctl --user enable "$unit" >/dev/null 2>&1 || true
		elif [ "$was_active" -eq 1 ]; then
			systemctl --user start "$unit" >/dev/null 2>&1 || true
		else
			systemctl --user disable --now "$unit" >/dev/null 2>&1 || true
		fi
	done
}

cleanup_on_exit() {
	local status="$?"
	cleanup_probe
	if [ "$status" -ne 0 ]; then
		restore_sunshine_retirement || true
		rollback_managed_files || true
		cleanup_transaction_backups
	else
		cleanup_transaction_backups
	fi
}

validate_socket_port() {
	local port="$1"
	case "$port" in
		""|*[!0-9]*) die "Invalid WayVNC control socket port: $port" ;;
	esac
	[ "$port" -ge 1 ] && [ "$port" -le 65535 ] || die "Invalid WayVNC control socket port: $port"
}

validate_socket_nonce() {
	local role="$1" nonce="$2"
	case "$nonce" in
		""|*[!0-9]*) die "Invalid $role WayVNC control socket nonce: $nonce" ;;
	esac
}

socket_namespace_dir() {
	printf '%s/%s\n' "$(runtime_dir_value)" "$SOCKET_NAMESPACE_NAME"
}

ensure_socket_namespace() {
	local namespace_dir runtime_dir runtime_real parent_real namespace_real expected_real
	runtime_dir="$(runtime_dir_value)"
	namespace_dir="$(socket_namespace_dir)"
	[ ! -L "$namespace_dir" ] || die "Refusing symlinked WayVNC control socket namespace: $namespace_dir"
	mkdir -p "$namespace_dir"
	[ ! -L "$namespace_dir" ] || die "Refusing symlinked WayVNC control socket namespace: $namespace_dir"
	chmod 0700 "$namespace_dir"
	[ -d "$namespace_dir" ] || die "Could not create WayVNC control socket namespace: $namespace_dir"
	[ -O "$namespace_dir" ] || die "WayVNC control socket namespace is not owned by the current user: $namespace_dir"
	runtime_real="$(canonical_path "$runtime_dir")"
	parent_real="$(canonical_path "$(dirname "$namespace_dir")")"
	[ "$parent_real" = "$runtime_real" ] || die "WayVNC control socket namespace escaped XDG_RUNTIME_DIR: $namespace_dir"
	namespace_real="$(canonical_path "$namespace_dir")"
	expected_real="$runtime_real/$SOCKET_NAMESPACE_NAME"
	[ "$namespace_real" = "$expected_real" ] || die "WayVNC control socket namespace resolved unexpectedly: $namespace_dir"
	printf '%s\n' "$namespace_dir"
}

installer_socket_path() {
	local role="$1" port="$2" nonce="${3:-}"
	local namespace_dir
	validate_socket_port "$port"
	namespace_dir="$(ensure_socket_namespace)"
	case "$role" in
		probe|rollback)
			validate_socket_nonce "$role" "$nonce"
			printf '%s/%s-%s-%s.sock\n' "$namespace_dir" "$role" "$port" "$nonce"
			;;
		managed)
			printf '%s/managed-%s.sock\n' "$namespace_dir" "$port"
			;;
		*) die "Unknown WayVNC control socket role: $role" ;;
	esac
}

path_is_in_socket_namespace() {
	local path="$1" namespace_dir namespace_real parent_real
	namespace_dir="$(ensure_socket_namespace)"
	case "$path" in
		"$namespace_dir"/*.sock) ;;
		*) return 1 ;;
	esac
	[ ! -L "$path" ] || return 1
	namespace_real="$(canonical_path "$namespace_dir")"
	parent_real="$(canonical_path "$(dirname "$path")")"
	[ "$parent_real" = "$namespace_real" ] || return 1
}

remove_exact_installer_socket() {
	local path="$1" label="$2"
	[ -n "$path" ] || return 0
	if ! path_is_in_socket_namespace "$path"; then
		print_warning "Refusing to remove $label socket outside installer namespace: $path"
		return 0
	fi
	[ -e "$path" ] || return 0
	if [ -S "$path" ] && [ -O "$path" ]; then
		rm -f -- "$path"
		print_info "Removed $label WayVNC control socket: $path"
	else
		print_warning "Preserving ambiguous $label control socket: $path"
	fi
}

cleanup_probe() {
	if [ -n "${PROBE_PID:-}" ] && kill -0 "$PROBE_PID" 2>/dev/null; then
		kill "$PROBE_PID" 2>/dev/null || true
		wait "$PROBE_PID" 2>/dev/null || true
	fi
	remove_exact_installer_socket "${PROBE_SOCKET_PATH:-}" "probe"
}

cleanup_failed_service() {
	systemctl --user disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
}

trap cleanup_on_exit EXIT

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
	for cmd in systemctl tailscale wayvnc wayvncctl hyprctl ss ps awk grep python3 mktemp readlink dirname id kill sleep cp install ln; do
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
	if [ "$TRANSACTION_ACTIVE" -eq 0 ]; then
		capture_service_state
		TRANSACTION_ACTIVE=1
	fi
	snapshot_managed_file "$LAUNCHER_PATH" "WayVNC launcher" LAUNCHER_BACKUP_PATH LAUNCHER_EXISTED
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
runtime_dir_value() {
	local runtime="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
	case "$runtime" in
		/*) ;;
		*) fail "XDG_RUNTIME_DIR must be an absolute active user runtime directory: $runtime" ;;
	esac
	case "$runtime" in
		*$'\n'*|*$'\r'*|*$'\t'*|*' '*) fail "XDG_RUNTIME_DIR contains unsafe whitespace: $runtime" ;;
	esac
	[ ! -L "$runtime" ] || fail "XDG_RUNTIME_DIR must not be a symlink: $runtime"
	[ -d "$runtime" ] || fail "XDG_RUNTIME_DIR does not exist: $runtime"
	[ -O "$runtime" ] || fail "XDG_RUNTIME_DIR is not owned by the current user: $runtime"
	printf '%s\n' "$runtime"
}
canonical_path() {
	python3 - "$1" <<'PY'
import os, sys
print(os.path.realpath(sys.argv[1]))
PY
}
validate_socket_role() {
	local role="$1"
	case "$role" in
		probe|managed|rollback) ;;
		*) fail "Unknown WAYVNC_SOCKET_ROLE: $role" ;;
	esac
}
validate_socket_port() {
	local port="$1"
	case "$port" in
		""|*[!0-9]*) fail "Invalid WAYVNC_BIND_PORT: $port" ;;
	esac
	[ "$port" -ge 1 ] && [ "$port" -le 65535 ] || fail "Invalid WAYVNC_BIND_PORT: $port"
}
socket_namespace() {
	local runtime_dir namespace_dir runtime_real parent_real namespace_real expected_real
	runtime_dir="$(runtime_dir_value)"
	namespace_dir="$runtime_dir/init-install-wayvnc"
	[ ! -L "$namespace_dir" ] || fail "Refusing symlinked WayVNC control socket namespace: $namespace_dir"
	mkdir -p "$namespace_dir"
	[ ! -L "$namespace_dir" ] || fail "Refusing symlinked WayVNC control socket namespace: $namespace_dir"
	chmod 0700 "$namespace_dir"
	[ -d "$namespace_dir" ] || fail "Could not create WayVNC control socket namespace: $namespace_dir"
	[ -O "$namespace_dir" ] || fail "WayVNC control socket namespace is not owned by the current user: $namespace_dir"
	runtime_real="$(canonical_path "$runtime_dir")"
	parent_real="$(canonical_path "$(dirname "$namespace_dir")")"
	[ "$parent_real" = "$runtime_real" ] || fail "WayVNC control socket namespace escaped XDG_RUNTIME_DIR: $namespace_dir"
	namespace_real="$(canonical_path "$namespace_dir")"
	expected_real="$runtime_real/init-install-wayvnc"
	[ "$namespace_real" = "$expected_real" ] || fail "WayVNC control socket namespace resolved unexpectedly: $namespace_dir"
	printf '%s\n' "$namespace_dir"
}
control_socket_for_role() {
	local role="$1" port="$2" namespace_dir
	validate_socket_role "$role"
	validate_socket_port "$port"
	namespace_dir="$(socket_namespace)"
	case "$role" in
		probe|rollback) printf '%s/%s-%s-%s.sock\n' "$namespace_dir" "$role" "$port" "$$" ;;
		managed) printf '%s/managed-%s.sock\n' "$namespace_dir" "$port" ;;
	esac
}
validate_control_socket_path() {
	local path="$1" namespace_dir namespace_real parent_real runtime_dir
	runtime_dir="$(runtime_dir_value)"
	namespace_dir="$(socket_namespace)"
	case "$path" in
		"$namespace_dir"/*.sock) ;;
		*) fail "Refusing WayVNC control socket outside installer namespace: $path" ;;
	esac
	[ ! -L "$path" ] || fail "Refusing symlinked WayVNC control socket path: $path"
	namespace_real="$(canonical_path "$namespace_dir")"
	parent_real="$(canonical_path "$(dirname "$path")")"
	[ "$parent_real" = "$namespace_real" ] || fail "Refusing WayVNC control socket with escaped parent: $path"
	case "$path" in
		"$runtime_dir/wayvncctl"|"/tmp/wayvncctl-$(id -u)")
			fail "Refusing to use the default WayVNC control socket: $path"
			;;
	esac
}
socket_path_referenced_by_ss() {
	local path="$1" output
	if ! output="$(ss -H -xap 2>&1)"; then
		return 2
	fi
	if printf '%s\n' "$output" | awk -v path="$path" 'index($0, path) { found=1 } END { exit found ? 0 : 1 }'; then
		return 0
	fi
	return 1
}
assert_managed_socket_can_be_removed() {
	local path="$1" expected_path reference_status
	expected_path="$(control_socket_for_role managed "$bind_port")"
	[ "$path" = "$expected_path" ] || fail "Refusing to remove unexpected managed WayVNC control socket path: $path"
	validate_control_socket_path "$path"
	[ ! -L "$path" ] || fail "Managed WayVNC control socket path is a symlink; preserving it: $path"
	[ -S "$path" ] || fail "Managed WayVNC control socket path exists but is not a socket: $path"
	[ -O "$path" ] || fail "Managed WayVNC control socket is not owned by the current user: $path"
	if wayvncctl -S "$path" --json version >/dev/null 2>&1; then
		fail "Managed WayVNC control socket is live; refusing to remove it: $path"
	fi
	if socket_path_referenced_by_ss "$path"; then
		reference_status=0
	else
		reference_status=$?
	fi
	case "$reference_status" in
		0) fail "Managed WayVNC control socket is referenced by a live Unix socket; preserving it: $path" ;;
		1) return 0 ;;
		*) fail "Could not prove managed WayVNC control socket is stale with ss; preserving it: $path" ;;
	esac
}
prepare_control_socket() {
	local path="$1" role="$2"
	validate_control_socket_path "$path"
	if [ ! -e "$path" ]; then
		return 0
	fi
	if [ "$role" != "managed" ]; then
		fail "Refusing to reuse existing $role WayVNC control socket: $path"
	fi
	assert_managed_socket_can_be_removed "$path"
	# Same-user TOCTOU cannot be eliminated for pathname sockets; recheck immediately before unlinking and fail closed on ambiguity.
	assert_managed_socket_can_be_removed "$path"
	rm -f -- "$path"
	log "Removed stale installer-owned managed WayVNC control socket: $path"
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
	local attempt runtime candidates instance wl_socket sleep_seconds session_attempts max_label
	if [ -n "${WAYVNC_SESSION_ATTEMPTS:-}" ]; then
		session_attempts="$WAYVNC_SESSION_ATTEMPTS"
	else
		case "${socket_role:-managed}" in
			managed) session_attempts=0 ;;
			*) session_attempts=30 ;;
		esac
	fi
	case "$session_attempts" in
		""|*[!0-9]*) fail "WAYVNC_SESSION_ATTEMPTS must be a non-negative integer; use 0 for managed infinite wait" ;;
	esac
	if [ "$session_attempts" -eq 0 ]; then
		max_label="unbounded"
	else
		max_label="$session_attempts"
	fi
	runtime="$(runtime_dir_value)"
	export XDG_RUNTIME_DIR="$runtime"
	unset HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY
	attempt=1
	while [ "$session_attempts" -eq 0 ] || [ "$attempt" -le "$session_attempts" ]; do
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
		if [ "$session_attempts" -ne 0 ] || [ "$attempt" -eq 1 ] || [ $((attempt % 12)) -eq 0 ]; then
			log "Waiting for an active Hyprland instance with a valid Wayland socket and Virtual-1 in $runtime (attempt $attempt/$max_label)..."
		fi
		sleep "$sleep_seconds"
		attempt=$((attempt + 1))
	done
	fail "No active Hyprland instance from 'hyprctl instances -j' had an existing Wayland socket and Virtual-1. Run: hyprctl instances -j && hyprctl monitors -j"
}
for cmd in tailscale wayvnc wayvncctl hyprctl ss awk python3 grep dirname id sleep; do
	require_cmd "$cmd"
done
bind_port="${WAYVNC_BIND_PORT:-5900}"
validate_socket_port "$bind_port"
socket_role="${WAYVNC_SOCKET_ROLE:-managed}"
validate_socket_role "$socket_role"
tailscale_ip="$(tailscale ip -4 2>/dev/null | awk 'NR == 1 {print $1}')"
[ -n "$tailscale_ip" ] || fail "No Tailscale IPv4 detected. Run: sudo systemctl enable --now tailscaled.service && sudo tailscale up --ssh"
session_target="$(select_session)"
wayland_display="${session_target%%:*}"
output_name="${session_target#*:}"
control_socket="$(control_socket_for_role "$socket_role" "$bind_port")"
export WAYLAND_DISPLAY="$wayland_display"
export XKB_DEFAULT_LAYOUT=us
export XKB_DEFAULT_VARIANT=
export XKB_DEFAULT_OPTIONS=
if [ "${WAYVNC_VALIDATE_ONLY:-0}" = "1" ]; then
	validate_control_socket_path "$control_socket"
	log "Validated WayVNC target ${WAYLAND_DISPLAY}/${output_name} on ${tailscale_ip}:${bind_port}"
	exit 0
fi
prepare_control_socket "$control_socket" "$socket_role"
log "Starting WayVNC on ${tailscale_ip}:${bind_port} for ${WAYLAND_DISPLAY}/${output_name} with keyboard layout us and control socket ${control_socket}"
exec wayvnc -S "$control_socket" -L info --keyboard=us --output="$output_name" "${tailscale_ip}:${bind_port}"
LAUNCHER
	chmod 0755 "$tmp_path"
	MANAGED_LAUNCHER_HASH="$(file_hash "$tmp_path")"
	mv -f "$tmp_path" "$LAUNCHER_PATH"
	[ "$(file_hash "$LAUNCHER_PATH")" = "$MANAGED_LAUNCHER_HASH" ] || die "Managed WayVNC launcher hash mismatch after install: $LAUNCHER_PATH"
	print_info "Installed managed WayVNC launcher: $LAUNCHER_PATH"
}

write_service() {
	preflight_managed_path "$SERVICE_PATH"
	local tmp_path
	tmp_path="$(mktemp "${SERVICE_PATH}.tmp.XXXXXX")"
	snapshot_managed_file "$SERVICE_PATH" "WayVNC service unit" SERVICE_BACKUP_PATH SERVICE_EXISTED
	cat > "$tmp_path" <<SERVICE
[Unit]
Description=WayVNC bound to Tailscale for the active Hyprland session
After=graphical-session.target
Wants=graphical-session.target
StartLimitIntervalSec=300
StartLimitBurst=3
[Service]
Type=simple
ExecStart=$LAUNCHER_PATH
Restart=on-failure
RestartSec=30s
RestartSteps=5
RestartMaxDelaySec=60s
TimeoutStartSec=infinity
[Install]
WantedBy=default.target
SERVICE
	chmod 0644 "$tmp_path"
	MANAGED_SERVICE_HASH="$(file_hash "$tmp_path")"
	mv -f "$tmp_path" "$SERVICE_PATH"
	[ "$(file_hash "$SERVICE_PATH")" = "$MANAGED_SERVICE_HASH" ] || die "Managed WayVNC service hash mismatch after install: $SERVICE_PATH"
	print_info "Installed systemd user service: $SERVICE_PATH"
}

validate_launcher_session() {
	WAYVNC_VALIDATE_ONLY=1 WAYVNC_SOCKET_ROLE=probe WAYVNC_BIND_PORT="$PROBE_PORT" "$LAUNCHER_PATH"
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

verify_control_socket_live() {
	local socket_path="$1" label="$2"
	if ! path_is_in_socket_namespace "$socket_path"; then
		echo "$label control socket is outside installer namespace: $socket_path" >&2
		return 1
	fi
	if ! wayvncctl -S "$socket_path" --json version >/dev/null 2>&1; then
		echo "$label control socket did not respond to wayvncctl -S $socket_path --json version" >&2
		return 1
	fi
	print_info "$label control socket verified: $socket_path"
}

run_probe() {
	print_info "Running reversible WayVNC probe on private port $PROBE_PORT before stopping existing remote desktop paths..."
	WAYVNC_SOCKET_ROLE=probe WAYVNC_BIND_PORT="$PROBE_PORT" "$LAUNCHER_PATH" &
	PROBE_PID="$!"
	PROBE_SOCKET_PATH="$(installer_socket_path probe "$PROBE_PORT" "$PROBE_PID")"
	if ! verify_listener_exact "$PROBE_PORT" "$PROBE_PID" "WayVNC probe"; then
		cleanup_probe
		die "WayVNC probe failed; Sunshine and existing port $MANAGED_PORT processes were left untouched."
	fi
	if ! verify_control_socket_live "$PROBE_SOCKET_PATH" "WayVNC probe"; then
		cleanup_probe
		die "WayVNC probe control socket verification failed; Sunshine and existing port $MANAGED_PORT processes were left untouched."
	fi
	cleanup_probe
	PROBE_PID=""
	PROBE_SOCKET_PATH=""
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
	WAYVNC_SOCKET_ROLE=rollback WAYVNC_BIND_PORT="$MANAGED_PORT" "$LAUNCHER_PATH" &
	ROLLBACK_PID="$!"
	ROLLBACK_SOCKET_PATH="$(installer_socket_path rollback "$MANAGED_PORT" "$ROLLBACK_PID")"
	if verify_listener_exact "$MANAGED_PORT" "$ROLLBACK_PID" "Rollback WayVNC"; then
		if verify_control_socket_live "$ROLLBACK_SOCKET_PATH" "Rollback WayVNC"; then
			print_warning "Rollback WayVNC is running as pid $ROLLBACK_PID with control socket $ROLLBACK_SOCKET_PATH. Manage it manually or rerun the installer after fixing the service failure."
			return 0
		fi
		print_warning "Rollback WayVNC TCP listener is running, but its control socket did not verify: $ROLLBACK_SOCKET_PATH"
		return 0
	fi
	if kill -0 "$ROLLBACK_PID" 2>/dev/null; then
		kill "$ROLLBACK_PID" 2>/dev/null || true
		wait "$ROLLBACK_PID" 2>/dev/null || true
	fi
	remove_exact_installer_socket "$ROLLBACK_SOCKET_PATH" "rollback"
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
	local main_pid managed_socket
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
	managed_socket="$(installer_socket_path managed "$MANAGED_PORT")"
	if ! verify_control_socket_live "$managed_socket" "Managed WayVNC service"; then
		fail_after_port_mutation "Managed WayVNC control socket verification failed."
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
	[ -z "$listeners" ] || {
		echo "Sunshine retirement failed; listeners remain on 47984/47989/47990:
$listeners" >&2
		return 1
	}
}

retire_sunshine_services() {
	print_info "Disabling Sunshine user services after managed WayVNC was proven. Package/config/credentials/apps/logs/state are preserved."
	local unit alias_target
	if [ -L "$SUNSHINE_ALIAS" ]; then
		alias_target="$(readlink "$SUNSHINE_ALIAS" 2>/dev/null || true)"
		case "$alias_target" in
			/usr/lib/systemd/user/app-dev.lizardbyte.app.Sunshine.service|/usr/lib/systemd/user/sunshine.service|app-dev.lizardbyte.app.Sunshine.service|../app-dev.lizardbyte.app.Sunshine.service)
				SUNSHINE_ALIAS_TARGET="$alias_target"
				;;
			*) die "Refusing to remove unexpected sunshine.service symlink target: $alias_target" ;;
		esac
	elif [ -e "$SUNSHINE_ALIAS" ] && [ ! -f "$SUNSHINE_ALIAS" ]; then
		die "Refusing to retire non-regular Sunshine user unit: $SUNSHINE_ALIAS"
	fi
	capture_sunshine_service_states
	for unit in "${SUNSHINE_UNITS[@]}"; do
		if sunshine_unit_exists "$unit"; then
			systemctl --user disable --now "$unit" || return 1
		fi
	done
	if [ -L "$SUNSHINE_ALIAS" ]; then
		rm -f -- "$SUNSHINE_ALIAS"
		SUNSHINE_ALIAS_REMOVED=1
		print_info "Removed managed Sunshine alias symlink: $SUNSHINE_ALIAS -> $SUNSHINE_ALIAS_TARGET"
	elif [ -e "$SUNSHINE_ALIAS" ]; then
		print_info "Preserved custom regular Sunshine user unit: $SUNSHINE_ALIAS"
	fi
	verify_sunshine_listeners_gone || return 1
	SUNSHINE_RETIREMENT_SUCCESS=1
}

install_prerequisites
preflight_required_state
write_launcher
write_service
validate_launcher_session
preflight_port_5900_state
run_probe
start_managed_service
TRANSACTION_SUCCESS=1
retire_sunshine_services || die "Sunshine retirement failed; previous Sunshine state was restored and verified WayVNC remains available."
cleanup_transaction_backups

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
