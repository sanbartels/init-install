#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

MANAGED_MARKER="init-install managed Hyprland startup"
MANAGED_MARKER_LINE="# $MANAGED_MARKER"
LAUNCHER_NAME="init-install-start-hyprland"
GREETD_CONFIG_PATH="${INIT_INSTALL_GREETD_CONFIG_PATH:-/etc/greetd/config.toml}"
BACKUP_PATH=""
ROLLBACK_RESTORE_PATH=""
MANAGED_CONFIG_HASH=""
LAUNCHER_PATH=""
LAUNCHER_EXISTED=0
LAUNCHER_BACKUP_PATH=""
MANAGED_LAUNCHER_HASH=""
INSTALLED_LAUNCHER=0
PRIOR_CONFIG_EXISTED=0
PRIOR_UNMANAGED_CONFIG=0
INSTALLED_CONFIG=0
GREETD_STATE_CAPTURED=0
GREETD_WAS_ENABLED=0
GREETD_WAS_ACTIVE=0

print_info() { echo -e "${GREEN}[HYPRLAND-STARTUP]${NC} $*"; }
print_warning() { echo -e "${YELLOW}[HYPRLAND-STARTUP]${NC} $*"; }
die() {
	echo -e "${RED}Error:${NC} $*" >&2
	exit 1
}

require_cmd() {
	command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

command_exists() {
	command -v "$1" >/dev/null 2>&1
}

sudo_preflight() {
	if ! command -v sudo >/dev/null 2>&1; then
		die "Privileged greetd setup is required, but sudo is not installed. Install sudo or run from an environment with sudo, then rerun."
	fi
	if ! sudo -n true >/dev/null 2>&1; then
		die "Privileged greetd setup requires non-interactive sudo. Run 'sudo -v' in an interactive SSH session, then rerun this installer before the sudo cache expires."
	fi
}

validate_username() {
	local username="$1"
	case "$username" in
		""|root|*[!abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-]*) return 1 ;;
	esac
	case "$username" in
		[abcdefghijklmnopqrstuvwxyz_]*|[ABCDEFGHIJKLMNOPQRSTUVWXYZ_]*) return 0 ;;
		*) return 1 ;;
	esac
}

validate_absolute_safe_path() {
	local label="$1" path="$2"
	case "$path" in
		/*) ;;
		*) die "$label must be an absolute path: $path" ;;
	esac
	case "$path" in
		*[!abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._/-]*) die "$label contains unsupported TOML/shell-special characters: $path" ;;
	esac
}

validate_toml_shell_value() {
	local label="$1" value="$2"
	case "$value" in
		""|*[!abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._/-]*) die "$label contains unsupported TOML/shell-special characters: $value" ;;
	esac
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

privileged_file_hash() {
	sudo -n python3 - "$1" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
}

resolve_desktop_user() {
	local current_uid candidate candidate_uid
	current_uid="$(id -u)"
	if [ "$current_uid" -eq 0 ]; then
		candidate="${SUDO_USER:-}"
		validate_username "$candidate" || die "Run this installer through sudo from the non-root desktop user, or run it directly as that user. Refusing to configure root autologin."
		candidate_uid="$(id -u "$candidate" 2>/dev/null || true)"
		[ -n "$candidate_uid" ] || die "Could not resolve UID for desktop user: $candidate"
		[ "$candidate_uid" -ne 0 ] || die "Refusing to configure greetd initial_session autologin as root."
		printf '%s\n' "$candidate"
		return 0
	fi
	candidate="$(id -un)"
	validate_username "$candidate" || die "Current desktop username is not safe for managed greetd TOML: $candidate"
	printf '%s\n' "$candidate"
}

resolve_user_home() {
	local username="$1" entry home
	entry="$(getent passwd "$username" || true)"
	[ -n "$entry" ] || die "Could not resolve passwd entry for desktop user: $username"
	home="$(printf '%s\n' "$entry" | cut -d: -f6)"
	validate_absolute_safe_path "Desktop user home" "$home"
	validate_toml_shell_value "Desktop user home" "$home"
	[ -d "$home" ] || die "Desktop user home does not exist: $home"
	printf '%s\n' "$home"
}

validate_greetd_config_path() {
	validate_absolute_safe_path "greetd config path" "$GREETD_CONFIG_PATH"
	case "$GREETD_CONFIG_PATH" in
		*/config.toml) ;;
		*) die "greetd config path must end in config.toml: $GREETD_CONFIG_PATH" ;;
	esac
	[ ! -L "$GREETD_CONFIG_PATH" ] || die "Refusing to overwrite symlinked greetd config: $GREETD_CONFIG_PATH"
}

package_installed() {
	local package="$1"
	pacman -Qi "$package" >/dev/null 2>&1
}

install_greetd_packages() {
	local missing_packages=() package
	for package in greetd greetd-agreety; do
		if ! package_installed "$package"; then
			missing_packages+=("$package")
		fi
	done
	if [ "${#missing_packages[@]}" -eq 0 ]; then
		print_info "greetd and agreety packages are already installed; skipping pacman."
		return 0
	fi
	print_info "Installing missing greetd packages: ${missing_packages[*]}"
	sudo_preflight
	sudo -n pacman -S --needed --noconfirm "${missing_packages[@]}" || \
		die "Failed to install greetd packages after sudo preflight. Run 'sudo -v' interactively, then retry before the sudo cache expires."
}

choose_hyprland_command() {
	# Arch extra/hyprland 0.55.4-1 ships /usr/bin/start-hyprland, /usr/bin/Hyprland, and /usr/bin/hyprland.
	# Prefer the packaged starter when present; fall back to the compositor binary only for older/broken installs.
	if command_exists start-hyprland; then
		printf 'start-hyprland\n'
		return 0
	fi
	if command_exists Hyprland; then
		printf 'Hyprland\n'
		return 0
	fi
	die "Hyprland is not available. Install Hyprland first, then rerun this startup installer."
}

preflight() {
	local cmd
	for cmd in id getent cut pacman systemctl mktemp python3 install dirname date chmod mv grep rm mkdir hyprctl ps awk sleep stat; do
		require_cmd "$cmd"
	done
	validate_greetd_config_path
	sudo_preflight
}

validate_greetd_tty1_conflict() {
	local unit_source
	unit_source="$(systemctl cat greetd.service 2>/dev/null || true)"
	if ! printf '%s\n' "$unit_source" | grep -Eq '^Conflicts=.*getty@tty1\.service'; then
		die "Packaged greetd.service does not prove Conflicts=getty@tty1.service. Refusing service mutation; inspect: systemctl cat greetd.service"
	fi
	print_info "Verified packaged greetd.service conflicts with getty@tty1.service; no manual getty disablement needed."
}

safe_owner_check() {
	local path="$1" desktop_user="$2" current_uid owner
	current_uid="$(id -u)"
	[ ! -L "$path" ] || die "Refusing symlinked managed launcher parent: $path"
	[ -d "$path" ] || die "Managed launcher parent is not a directory: $path"
	if [ "$current_uid" -eq 0 ]; then
		owner="$(stat -c %U "$path" 2>/dev/null || stat -f %Su "$path" 2>/dev/null || true)"
		[ "$owner" = "$desktop_user" ] || die "Managed launcher parent is owned by '$owner', expected '$desktop_user': $path"
	else
		[ -O "$path" ] || die "Managed launcher parent is not owned by the current user: $path"
	fi
}

prepare_launcher_parent() {
	local desktop_user="$1" desktop_home="$2" local_dir bin_dir current_uid primary_group
	local_dir="$desktop_home/.local"
	bin_dir="$local_dir/bin"
	validate_absolute_safe_path "managed launcher .local path" "$local_dir"
	validate_absolute_safe_path "managed launcher bin path" "$bin_dir"
	[ ! -L "$desktop_home" ] || die "Refusing symlinked desktop home: $desktop_home"
	[ -d "$desktop_home" ] || die "Desktop home is not a directory: $desktop_home"
	current_uid="$(id -u)"
	if [ "$current_uid" -eq 0 ]; then
		[ ! -e "$local_dir" ] || safe_owner_check "$local_dir" "$desktop_user"
		sudo -n -u "$desktop_user" install -d -m 0755 "$local_dir"
		safe_owner_check "$local_dir" "$desktop_user"
		[ ! -e "$bin_dir" ] || safe_owner_check "$bin_dir" "$desktop_user"
		sudo -n -u "$desktop_user" install -d -m 0755 "$bin_dir"
		safe_owner_check "$bin_dir" "$desktop_user"
	else
		[ ! -e "$local_dir" ] || safe_owner_check "$local_dir" "$desktop_user"
		mkdir -p "$local_dir"
		safe_owner_check "$local_dir" "$desktop_user"
		[ ! -e "$bin_dir" ] || safe_owner_check "$bin_dir" "$desktop_user"
		mkdir -p "$bin_dir"
		safe_owner_check "$bin_dir" "$desktop_user"
	fi
}

snapshot_launcher_for_rollback() {
	local launcher_path="$1"
	LAUNCHER_PATH="$launcher_path"
	if [ -e "$launcher_path" ]; then
		[ -f "$launcher_path" ] || die "Refusing to backup non-regular launcher path: $launcher_path"
		[ ! -L "$launcher_path" ] || die "Refusing symlinked launcher path: $launcher_path"
		LAUNCHER_EXISTED=1
		LAUNCHER_BACKUP_PATH="$(mktemp)"
		cp -p "$launcher_path" "$LAUNCHER_BACKUP_PATH"
	else
		LAUNCHER_EXISTED=0
		LAUNCHER_BACKUP_PATH=""
	fi
}

write_launcher() {
	local desktop_user="$1" desktop_home="$2" tmp_path launcher_path current_uid primary_group
	launcher_path="$desktop_home/.local/bin/$LAUNCHER_NAME"
	LAUNCHER_PATH="$launcher_path"
	validate_absolute_safe_path "managed launcher path" "$launcher_path"
	validate_toml_shell_value "managed launcher path" "$launcher_path"
	prepare_launcher_parent "$desktop_user" "$desktop_home"
	[ ! -L "$launcher_path" ] || die "Refusing to overwrite symlinked launcher: $launcher_path"
	[ ! -e "$launcher_path" ] || [ -f "$launcher_path" ] || die "Refusing to overwrite non-regular launcher path: $launcher_path"
	snapshot_launcher_for_rollback "$launcher_path"
	tmp_path="$(mktemp)"
	cat > "$tmp_path" <<'LAUNCHER'
#!/bin/bash
set -euo pipefail

log() { printf '[init-install-start-hyprland] %s\n' "$*" >&2; }

retry_min_seconds="${HYPRLAND_START_RETRY_MIN_SECONDS:-2}"
retry_max_seconds="${HYPRLAND_START_RETRY_MAX_SECONDS:-60}"
child_pid=""

validate_retry_seconds() {
	local label="$1" value="$2"
	case "$value" in
		""|*[!0-9]*) log "$label must be a positive integer: $value"; exit 2 ;;
	esac
	[ "$value" -gt 0 ] || { log "$label must be greater than zero: $value"; exit 2; }
}

choose_hyprland_command() {
	if command -v start-hyprland >/dev/null 2>&1; then
		printf 'start-hyprland\n'
		return 0
	fi
	if command -v Hyprland >/dev/null 2>&1; then
		printf 'Hyprland\n'
		return 0
	fi
	return 127
}

stop_child() {
	if [ -n "${child_pid:-}" ] && kill -0 "$child_pid" 2>/dev/null; then
		kill "$child_pid" 2>/dev/null || true
		wait "$child_pid" 2>/dev/null || true
	fi
	exit 0
}

trap stop_child INT TERM HUP

export XDG_SESSION_TYPE=wayland
export XDG_CURRENT_DESKTOP=Hyprland
export XDG_SESSION_DESKTOP=Hyprland
export DESKTOP_SESSION=Hyprland
export XDG_DATA_DIRS="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
export XDG_CONFIG_DIRS="${XDG_CONFIG_DIRS:-/etc/xdg}"
export XCURSOR_SIZE="${XCURSOR_SIZE:-24}"
export HYPRCURSOR_SIZE="${HYPRCURSOR_SIZE:-24}"
export TZ="${TZ:-America/Argentina/Buenos_Aires}"
export GNOME_KEYRING_CONTROL="${GNOME_KEYRING_CONTROL:-/run/user/$(id -u)/keyring}"

validate_retry_seconds HYPRLAND_START_RETRY_MIN_SECONDS "$retry_min_seconds"
validate_retry_seconds HYPRLAND_START_RETRY_MAX_SECONDS "$retry_max_seconds"
if [ "$retry_max_seconds" -lt "$retry_min_seconds" ]; then
	log "HYPRLAND_START_RETRY_MAX_SECONDS must be >= HYPRLAND_START_RETRY_MIN_SECONDS"
	exit 2
fi

attempt=1
delay="$retry_min_seconds"
while true; do
	if ! command_name="$(choose_hyprland_command)"; then
		log "Neither start-hyprland nor Hyprland is available"
		exit 127
	fi
	log "Starting Hyprland with ${command_name} (attempt ${attempt})"
	"$command_name" &
	child_pid="$!"
	set +e
	wait "$child_pid"
	status="$?"
	set -e
	child_pid=""
	if [ "$status" -eq 0 ]; then
		log "Hyprland exited cleanly; returning control to greetd"
		exit 0
	fi
	log "Hyprland exited with status ${status}; retrying in ${delay}s"
	sleep "$delay"
	attempt=$((attempt + 1))
	if [ "$delay" -lt "$retry_max_seconds" ]; then
		delay=$((delay * 2))
		[ "$delay" -le "$retry_max_seconds" ] || delay="$retry_max_seconds"
	fi
done
LAUNCHER
	chmod 0755 "$tmp_path"
	MANAGED_LAUNCHER_HASH="$(file_hash "$tmp_path")"
	current_uid="$(id -u)"
	if [ "$current_uid" -eq 0 ]; then
		primary_group="$(id -gn "$desktop_user")"
		sudo -n install -o "$desktop_user" -g "$primary_group" -m 0755 "$tmp_path" "$launcher_path"
		rm -f -- "$tmp_path"
	else
		install -m 0755 "$tmp_path" "$launcher_path"
		rm -f -- "$tmp_path"
	fi
	INSTALLED_LAUNCHER=1
	[ "$(file_hash "$launcher_path")" = "$MANAGED_LAUNCHER_HASH" ] || fail_with_rollback "Managed launcher hash mismatch after install: $launcher_path"
	print_info "Installed managed Hyprland launcher: $launcher_path"
	printf '%s\n' "$launcher_path"
}

write_candidate_config() {
	local desktop_user="$1" launcher_path="$2" tmp_path
	validate_toml_shell_value "greetd initial_session user" "$desktop_user"
	validate_toml_shell_value "greetd initial_session command" "$launcher_path"
	tmp_path="$(mktemp)"
	cat > "$tmp_path" <<CONFIG
# $MANAGED_MARKER
# Managed by init-install/hyprland/configure_hyprland_startup.sh

[terminal]
vt = 1
switch = true

[default_session]
command = "agreety --cmd /bin/bash"

[initial_session]
command = "$launcher_path"
user = "$desktop_user"
CONFIG
	printf '%s\n' "$tmp_path"
}

validate_candidate_config() {
	local config_path="$1" desktop_user="$2" launcher_path="$3"
	python3 - "$config_path" "$desktop_user" "$launcher_path" <<'PY'
import pathlib
import sys

config_path = pathlib.Path(sys.argv[1])
desktop_user = sys.argv[2]
launcher_path = sys.argv[3]
text = config_path.read_text(encoding="utf-8")
try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None
if tomllib is not None:
    data = tomllib.loads(text)
    if data.get("terminal", {}).get("vt") != 1:
        raise SystemExit("greetd terminal.vt must be 1")
    if data.get("terminal", {}).get("switch") is not True:
        raise SystemExit("greetd terminal.switch must be true")
    if data.get("default_session", {}).get("command") != "agreety --cmd /bin/bash":
        raise SystemExit("greetd default_session.command is not the managed recovery command")
    if data.get("initial_session", {}).get("command") != launcher_path:
        raise SystemExit("greetd initial_session.command does not match the managed launcher")
    if data.get("initial_session", {}).get("user") != desktop_user:
        raise SystemExit("greetd initial_session.user does not match the desktop user")
required_lines = {
    "[terminal]",
    "vt = 1",
    "switch = true",
    "[default_session]",
    'command = "agreety --cmd /bin/bash"',
    "[initial_session]",
    f'command = "{launcher_path}"',
    f'user = "{desktop_user}"',
}
lines = {line.strip() for line in text.splitlines()}
missing = sorted(required_lines - lines)
if missing:
    raise SystemExit(f"missing required greetd config lines: {missing}")
if text.count("[terminal]") != 1 or text.count("[default_session]") != 1 or text.count("[initial_session]") != 1:
    raise SystemExit("greetd config must contain each managed section exactly once")
assert desktop_user != "root"
PY
}

config_is_managed() {
	[ -f "$GREETD_CONFIG_PATH" ] && grep -Fxq "$MANAGED_MARKER_LINE" "$GREETD_CONFIG_PATH" 2>/dev/null
}

current_config_is_managed_privileged() {
	[ -f "$GREETD_CONFIG_PATH" ] && sudo -n grep -Fxq "$MANAGED_MARKER_LINE" "$GREETD_CONFIG_PATH" 2>/dev/null
}

current_config_matches_installed_hash() {
	[ -n "$MANAGED_CONFIG_HASH" ] || return 1
	[ -f "$GREETD_CONFIG_PATH" ] || return 1
	[ "$(privileged_file_hash "$GREETD_CONFIG_PATH" 2>/dev/null || true)" = "$MANAGED_CONFIG_HASH" ]
}

install_greetd_config() {
	local candidate_config="$1" config_dir config_tmp timestamp rollback_snapshot
	config_dir="$(dirname "$GREETD_CONFIG_PATH")"
	timestamp="$(date +%Y%m%d%H%M%S)"
	if [ -f "$GREETD_CONFIG_PATH" ]; then
		PRIOR_CONFIG_EXISTED=1
		if config_is_managed; then
			rollback_snapshot="$(mktemp)"
			sudo -n cp -a "$GREETD_CONFIG_PATH" "$rollback_snapshot"
			ROLLBACK_RESTORE_PATH="$rollback_snapshot"
		else
			PRIOR_UNMANAGED_CONFIG=1
			BACKUP_PATH="${GREETD_CONFIG_PATH}.init-install-backup.${timestamp}"
			ROLLBACK_RESTORE_PATH="$BACKUP_PATH"
			print_warning "Preserving existing unmanaged greetd config: $BACKUP_PATH"
			sudo -n cp -a "$GREETD_CONFIG_PATH" "$BACKUP_PATH"
		fi
	fi
	sudo -n mkdir -p "$config_dir"
	config_tmp="${GREETD_CONFIG_PATH}.init-install.tmp.$$"
	sudo -n install -m 0644 "$candidate_config" "$config_tmp"
	sudo -n mv -f "$config_tmp" "$GREETD_CONFIG_PATH"
	INSTALLED_CONFIG=1
	current_config_matches_installed_hash || fail_with_rollback "Managed greetd config hash mismatch after install: $GREETD_CONFIG_PATH"
	print_info "Installed managed greetd config: $GREETD_CONFIG_PATH"
}

capture_greetd_state() {
	if systemctl is-enabled --quiet greetd.service >/dev/null 2>&1; then
		GREETD_WAS_ENABLED=1
	else
		GREETD_WAS_ENABLED=0
	fi
	if systemctl is-active --quiet greetd.service >/dev/null 2>&1; then
		GREETD_WAS_ACTIVE=1
	else
		GREETD_WAS_ACTIVE=0
	fi
	GREETD_STATE_CAPTURED=1
}

restore_greetd_state() {
	[ "$GREETD_STATE_CAPTURED" -eq 1 ] || return 0
	if [ "$GREETD_WAS_ENABLED" -eq 1 ] && [ "$GREETD_WAS_ACTIVE" -eq 1 ]; then
		sudo -n systemctl enable --now greetd.service >/dev/null 2>&1 || true
	elif [ "$GREETD_WAS_ENABLED" -eq 1 ]; then
		sudo -n systemctl enable greetd.service >/dev/null 2>&1 || true
		sudo -n systemctl stop greetd.service >/dev/null 2>&1 || true
	elif [ "$GREETD_WAS_ACTIVE" -eq 1 ]; then
		sudo -n systemctl disable greetd.service >/dev/null 2>&1 || true
		sudo -n systemctl start greetd.service >/dev/null 2>&1 || true
	else
		sudo -n systemctl disable --now greetd.service >/dev/null 2>&1 || true
	fi
}

rollback_launcher_after_failure() {
	local current_hash
	[ "$INSTALLED_LAUNCHER" -eq 1 ] || return 0
	[ -n "$LAUNCHER_PATH" ] || return 0
	if [ ! -e "$LAUNCHER_PATH" ]; then
		return 0
	fi
	current_hash="$(file_hash "$LAUNCHER_PATH" 2>/dev/null || true)"
	if [ "$current_hash" != "$MANAGED_LAUNCHER_HASH" ]; then
		print_warning "Current launcher no longer matches the installed managed content; preserving it: $LAUNCHER_PATH"
		return 1
	fi
	if [ "$LAUNCHER_EXISTED" -eq 1 ] && [ -n "$LAUNCHER_BACKUP_PATH" ]; then
		install -m 0755 "$LAUNCHER_BACKUP_PATH" "$LAUNCHER_PATH"
		print_warning "Restored previous Hyprland launcher: $LAUNCHER_PATH"
	else
		rm -f -- "$LAUNCHER_PATH"
		print_warning "Removed newly installed Hyprland launcher: $LAUNCHER_PATH"
	fi
}

rollback_config_after_failure() {
	local rollback_status=0
	[ "$INSTALLED_CONFIG" -eq 1 ] || return 0
	print_warning "Transactional rollback: restoring previous greetd config and service state."
	sudo -n systemctl disable --now greetd.service >/dev/null 2>&1 || true
	if ! current_config_is_managed_privileged; then
		print_warning "Current greetd config no longer has the exact managed marker; preserving it and refusing automatic overwrite/remove: $GREETD_CONFIG_PATH"
		rollback_status=1
	elif ! current_config_matches_installed_hash; then
		print_warning "Current greetd config no longer matches the exact installed managed content; preserving it and refusing automatic overwrite/remove: $GREETD_CONFIG_PATH"
		rollback_status=1
	elif [ "$PRIOR_CONFIG_EXISTED" -eq 1 ] && [ -n "$ROLLBACK_RESTORE_PATH" ]; then
		sudo -n install -m 0644 "$ROLLBACK_RESTORE_PATH" "$GREETD_CONFIG_PATH"
		print_warning "Restored previous greetd config from: $ROLLBACK_RESTORE_PATH"
	else
		sudo -n rm -f "$GREETD_CONFIG_PATH"
		print_warning "Removed managed greetd config because no prior config existed: $GREETD_CONFIG_PATH"
	fi
	restore_greetd_state
	return "$rollback_status"
}

print_recovery_evidence() {
	local recovery_backup_path
	if [ "$PRIOR_CONFIG_EXISTED" -eq 1 ] && [ -n "$ROLLBACK_RESTORE_PATH" ]; then
		recovery_backup_path="$ROLLBACK_RESTORE_PATH"
	elif [ "$PRIOR_CONFIG_EXISTED" -eq 0 ]; then
		recovery_backup_path="__NO_PRIOR_CONFIG__"
	else
		recovery_backup_path=""
	fi
	cat <<EOF

Recovery evidence commands:
  systemctl status greetd.service --no-pager
  journalctl -u greetd.service -b --no-pager
  managed_config_sha256='$MANAGED_CONFIG_HASH'
  backup_path='$recovery_backup_path'
  current_config_sha256="\$(sudo python3 -c 'import hashlib, pathlib; print(hashlib.sha256(pathlib.Path("$GREETD_CONFIG_PATH").read_bytes()).hexdigest())')"
  if [ "\$current_config_sha256" != "\$managed_config_sha256" ]; then
    echo 'greetd config changed after install; preserving it' >&2
    exit 1
  elif [ -n "\$backup_path" ] && [ "\$backup_path" != '__NO_PRIOR_CONFIG__' ]; then
    sudo install -m 0644 "\$backup_path" '$GREETD_CONFIG_PATH'
  elif [ "\$backup_path" = '__NO_PRIOR_CONFIG__' ]; then
    sudo rm -f '$GREETD_CONFIG_PATH'
  else
    echo 'prior backup path is unknown; preserving config' >&2
    exit 1
  fi
EOF
}

fail_with_rollback() {
	local message="$1"
	rollback_config_after_failure || true
	rollback_launcher_after_failure || true
	print_recovery_evidence >&2
	die "$message"
}

enable_greetd() {
	sudo_preflight
	sudo -n systemctl enable --now greetd.service || \
		return 1
	print_info "greetd.service is enabled and started."
}

run_as_desktop_user() {
	local desktop_user="$1" desktop_uid="$2" runtime_dir
	shift 2
	runtime_dir="${HYPRLAND_STARTUP_RUNTIME_DIR:-/run/user/$desktop_uid}"
	if [ "$(id -u)" -eq 0 ]; then
		sudo -n -u "$desktop_user" env XDG_RUNTIME_DIR="$runtime_dir" HYPRLAND_INSTANCE_SIGNATURE="${HYPRLAND_INSTANCE_SIGNATURE:-}" WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" "$@"
	else
		env XDG_RUNTIME_DIR="$runtime_dir" HYPRLAND_INSTANCE_SIGNATURE="${HYPRLAND_INSTANCE_SIGNATURE:-}" WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" "$@"
	fi
}

select_instance_line() {
	local runtime_dir="$1" instances_json="$2"
	python3 - "$runtime_dir" "$instances_json" <<'PY'
import json
import os
import stat
import sys

runtime_dir = sys.argv[1]
instances_json = sys.argv[2]
try:
    data = json.loads(instances_json)
except Exception:
    sys.exit(1)
if not isinstance(data, list):
    sys.exit(1)
for item in data:
    if not isinstance(item, dict):
        continue
    instance = item.get("instance") or item.get("signature")
    wl_socket = item.get("wl_socket") or item.get("waylandSocket") or item.get("wayland_socket")
    pid = item.get("pid")
    if isinstance(instance, str) and isinstance(wl_socket, str) and isinstance(pid, int):
        socket_path = os.path.join(runtime_dir, wl_socket)
        try:
            socket_mode = os.stat(socket_path).st_mode
        except OSError:
            continue
        if stat.S_ISSOCK(socket_mode):
            print(f"{pid}\t{instance}\t{wl_socket}")
            sys.exit(0)
sys.exit(1)
PY
}

monitors_have_virtual_1() {
	local monitors_json="$1"
	python3 - "$monitors_json" <<'PY'
import json
import sys

try:
    data = json.loads(sys.argv[1])
except Exception:
    sys.exit(1)
if isinstance(data, list) and any(isinstance(item, dict) and item.get("name") == "Virtual-1" for item in data):
    sys.exit(0)
sys.exit(1)
PY
}

validate_started_session() {
	local desktop_user="$1" desktop_uid="$2" attempts delay runtime_dir attempt instances_json instance_line pid instance wl_socket owner monitors_json
	attempts="${HYPRLAND_STARTUP_VALIDATION_ATTEMPTS:-24}"
	delay="${HYPRLAND_STARTUP_VALIDATION_DELAY_SECONDS:-5}"
	case "$attempts" in ""|*[!0-9]*) die "HYPRLAND_STARTUP_VALIDATION_ATTEMPTS must be a positive integer" ;; esac
	case "$delay" in ""|*[!0-9]*) die "HYPRLAND_STARTUP_VALIDATION_DELAY_SECONDS must be a positive integer" ;; esac
	[ "$attempts" -gt 0 ] || die "HYPRLAND_STARTUP_VALIDATION_ATTEMPTS must be greater than zero"
	[ "$delay" -gt 0 ] || die "HYPRLAND_STARTUP_VALIDATION_DELAY_SECONDS must be greater than zero"
	runtime_dir="${HYPRLAND_STARTUP_RUNTIME_DIR:-/run/user/$desktop_uid}"
	for attempt in $(seq 1 "$attempts"); do
		if ! systemctl is-active --quiet greetd.service; then
			print_warning "greetd.service is not active yet (attempt $attempt/$attempts)."
		else
			instances_json="$(run_as_desktop_user "$desktop_user" "$desktop_uid" hyprctl instances -j 2>/dev/null || true)"
			instance_line="$(select_instance_line "$runtime_dir" "$instances_json" || true)"
			if [ -n "$instance_line" ]; then
				IFS=$'\t' read -r pid instance wl_socket <<< "$instance_line"
				owner="$(ps -o user= -p "$pid" 2>/dev/null | awk 'NR == 1 {print $1}')"
				if [ "$owner" = "$desktop_user" ]; then
					monitors_json="$(HYPRLAND_INSTANCE_SIGNATURE="$instance" WAYLAND_DISPLAY="$wl_socket" run_as_desktop_user "$desktop_user" "$desktop_uid" hyprctl monitors -j 2>/dev/null || true)"
					if monitors_have_virtual_1 "$monitors_json"; then
						print_info "Validated greetd-started Hyprland session: pid $pid, socket $runtime_dir/$wl_socket, output Virtual-1."
						return 0
					fi
					print_warning "Hyprland instance $instance exists but Virtual-1 is not visible yet (attempt $attempt/$attempts)."
				else
					print_warning "Hyprland instance pid $pid is owned by '$owner', expected '$desktop_user' (attempt $attempt/$attempts)."
				fi
			else
				print_warning "No valid Hyprland instance with pid and Wayland socket in $runtime_dir yet (attempt $attempt/$attempts)."
			fi
		fi
		[ "$attempt" -eq "$attempts" ] || sleep "$delay"
	done
	cat >&2 <<EOF
Hyprland startup validation failed. Inspect:
  systemctl status greetd.service --no-pager
  journalctl -u greetd.service -b --no-pager
  sudo -u $desktop_user XDG_RUNTIME_DIR=$runtime_dir hyprctl instances -j
  sudo -u $desktop_user XDG_RUNTIME_DIR=$runtime_dir hyprctl monitors -j
EOF
	return 1
}

print_runbook() {
	local launcher_path="$1" recovery_backup_path
	if [ -n "$BACKUP_PATH" ]; then
		recovery_backup_path="$BACKUP_PATH"
	elif [ "$PRIOR_CONFIG_EXISTED" -eq 0 ]; then
		recovery_backup_path="__NO_PRIOR_CONFIG__"
	else
		recovery_backup_path=""
	fi
	cat <<EOF

Hyprland startup is now managed by greetd initial_session.

Pre-reboot checks:
  systemctl status greetd.service --no-pager
  journalctl -u greetd.service -b --no-pager
  test -x "$launcher_path"
  sudo sed -n '1,120p' "$GREETD_CONFIG_PATH"
  sudo grep -Fx '$MANAGED_MARKER_LINE' "$GREETD_CONFIG_PATH"
  [ "\$(sudo python3 -c 'import hashlib, pathlib; print(hashlib.sha256(pathlib.Path("$GREETD_CONFIG_PATH").read_bytes()).hexdigest())')" = "$MANAGED_CONFIG_HASH" ]

Rollback commands over SSH/Tailscale:
  sudo systemctl disable --now greetd.service
  managed_config_sha256='$MANAGED_CONFIG_HASH'
  backup_path='$recovery_backup_path'
  current_config_sha256="\$(sudo python3 -c 'import hashlib, pathlib; print(hashlib.sha256(pathlib.Path("$GREETD_CONFIG_PATH").read_bytes()).hexdigest())')"
  if [ "\$current_config_sha256" != "\$managed_config_sha256" ]; then
    echo 'greetd config changed after install; preserving it' >&2
    exit 1
  elif [ -n "\$backup_path" ] && [ "\$backup_path" != '__NO_PRIOR_CONFIG__' ]; then
    sudo install -m 0644 "\$backup_path" "$GREETD_CONFIG_PATH"
    sudo systemctl enable --now greetd.service  # only if the preserved config should run again
  elif [ "\$backup_path" = '__NO_PRIOR_CONFIG__' ]; then
    sudo rm -f "$GREETD_CONFIG_PATH"
  else
    echo 'prior backup path is unknown; preserving config' >&2
    exit 1
  fi
EOF
	cat <<'EOF'

Recovery remains SSH/Tailscale first. Provider console access reaches the autologged-in desktop session by design.
Do not reboot blindly: validate greetd status, config contents, and WayVNC readiness before scheduling a reboot.
EOF
}

main() {
	local desktop_user desktop_home desktop_uid launcher_path candidate_config hyprland_command
	preflight
	desktop_user="$(resolve_desktop_user)"
	desktop_uid="$(id -u "$desktop_user")"
	desktop_home="$(resolve_user_home "$desktop_user")"
	hyprland_command="$(choose_hyprland_command)"
	print_info "Target desktop user: $desktop_user"
	print_info "Target desktop UID: $desktop_uid"
	print_info "Target desktop home: $desktop_home"
	print_info "Hyprland launch command: $hyprland_command"
	capture_greetd_state
	install_greetd_packages
	validate_greetd_tty1_conflict
	write_launcher "$desktop_user" "$desktop_home"
	launcher_path="$LAUNCHER_PATH"
	candidate_config="$(write_candidate_config "$desktop_user" "$launcher_path")"
	validate_candidate_config "$candidate_config" "$desktop_user" "$launcher_path"
	MANAGED_CONFIG_HASH="$(file_hash "$candidate_config")"
	install_greetd_config "$candidate_config"
	rm -f -- "$candidate_config"
	enable_greetd || fail_with_rollback "Failed to enable/start greetd.service after sudo preflight. Inspect: systemctl status greetd.service --no-pager"
	validate_started_session "$desktop_user" "$desktop_uid" || fail_with_rollback "greetd started, but the Hyprland/Wayland/Virtual-1 validation failed. Rollback was attempted."
	print_runbook "$launcher_path"
}

main "$@"
