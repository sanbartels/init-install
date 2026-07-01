#!/usr/bin/env python3
from __future__ import annotations

import curses
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from installer_lib.config_sync import DEFAULT_CONFIG_TARGETS, apply_sync_plan, compare_paths, SyncPlan

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = Path.home() / ".init-install.conf"
IMPORT_BACKUP_ROOT = Path.home() / ".config_backups" / "init-install"
EXPORT_BACKUP_ROOT = SCRIPT_DIR / ".config_backups" / "exports"

MUTUAL_EXCLUSIONS: dict[str, list[str]] = {
    "keyring": ["keepassxc"],
    "keepassxc": ["keyring"],
}


@dataclass(frozen=True)
class Category:
    key: str
    title: str
    summary: str
    packages: str
    scripts: tuple[str, ...] = ()
    internal_runner: Callable[[], list[str]] | None = None


@dataclass(frozen=True)
class MenuAction:
    key: str
    title: str
    summary: str
    callback_name: str


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    summary: str
    categories: tuple[Category, ...]
    default_selected: bool = False


def copy_if_missing(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return f"Ya existe {dst.name}, no se sobreescribe"
    shutil.copy2(src, dst)
    return f"Copiado: {dst}"


def run_command(command: list[str], *, cwd: Path = SCRIPT_DIR) -> list[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    output = (result.stdout or "") + (result.stderr or "")
    lines = [strip_ansi(line) for line in output.strip().splitlines() if line.strip()]
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, command, output=output)
    return lines


def install_pacman_packages(label: str, packages: Iterable[str]) -> Callable[[], list[str]]:
    package_list = tuple(packages)

    def runner() -> list[str]:
        messages = [f"[PACMAN] {label}: {' '.join(package_list)}"]
        messages.extend(run_command(["sudo", "pacman", "-S", "--needed", "--noconfirm", *package_list]))
        return messages

    return runner


def install_yay_packages(label: str, packages: Iterable[str]) -> Callable[[], list[str]]:
    package_list = tuple(packages)

    def runner() -> list[str]:
        if shutil.which("yay") is None:
            raise RuntimeError("yay no está instalado. Ejecuta primero Install base > Yay.")
        messages = [f"[YAY] {label}: {' '.join(package_list)}"]
        messages.extend(run_command(["yay", "-S", "--needed", "--noconfirm", *package_list]))
        return messages

    return runner


def run_post_install_actions() -> list[str]:
    messages: list[str] = ["[POST] Configurando MIME y comando update..."]

    mimeapps_src = SCRIPT_DIR / "mimeapps" / "mimeapps.list"
    if mimeapps_src.exists():
        messages.append(copy_if_missing(mimeapps_src, Path.home() / ".config" / "mimeapps.list"))

    update_installer = SCRIPT_DIR / "system_update" / "install_update_command.sh"
    if update_installer.exists():
        update_installer.chmod(update_installer.stat().st_mode | 0o111)
        messages.extend(run_command(["bash", str(update_installer)]))

    comandos_src = SCRIPT_DIR / "COMANDOS.md"
    if comandos_src.exists():
        destination = Path.home() / "COMANDOS.md"
        if destination.exists():
            messages.append("Ya existe COMANDOS.md, no se sobreescribe")
        else:
            shutil.copy2(comandos_src, destination)
            messages.append("Guía disponible en ~/COMANDOS.md")

    return messages


def package_text(*packages: str) -> str:
    return "Paquetes:\n" + "\n".join(f"- {pkg}" for pkg in packages)


def scripts(*relative_paths: str) -> tuple[str, ...]:
    return tuple(str(SCRIPT_DIR / path) for path in relative_paths)


BASE_SECTION = Section(
    "base",
    "Install base",
    "Sistema base, yay, drivers, red, audio, GPU, TRIM y post-install mínimo",
    (
        Category(
            "system_base",
            "Sistema base",
            "Actualiza el sistema e instala paquetes base esenciales",
            package_text("base", "base-devel", "linux", "linux-firmware", "grub", "efibootmgr", "sudo", "git", "curl", "wget", "jq", "nano", "unzip", "7zip", "tree"),
            scripts("system_base/install_base.sh"),
        ),
        Category(
            "yay_install",
            "Yay AUR helper",
            "Instala yay si no existe, sin instalar software extra",
            "Acciones:\n- clona yay desde AUR si falta\n- makepkg -si --noconfirm",
            scripts("yay_install/install_yay_packages.sh"),
        ),
        Category(
            "drivers_utilities",
            "Drivers y utilidades base",
            "Red, audio, códecs, microcódigo, GPU y TRIM",
            "Incluye NetworkManager, PipeWire, códecs, microcódigo CPU, drivers GPU detectados y fstrim.timer.",
            scripts(
                "drivers_utilities/network_install.sh",
                "drivers_utilities/audio_install.sh",
                "drivers_utilities/codecs_install.sh",
                "drivers_utilities/cpu_microcode_install.sh",
                "drivers_utilities/gpu_drivers_install.sh",
                "drivers_utilities/configure_trim.sh",
            ),
        ),
        Category(
            "post_install",
            "Post instalación básica",
            "Copia MIME, instala comando update y guía final",
            "Acciones:\n- mimeapps.list\n- comando update\n- COMANDOS.md",
            internal_runner=run_post_install_actions,
        ),
    ),
    default_selected=True,
)

DESKTOP_SECTION = Section(
    "desktop_bar",
    "Install desktop / bar",
    "Entornos gráficos, shell/barra y componentes visuales",
    (
        Category("hyprland", "Hyprland", "Instala Hyprland y dependencias de sesión", "Paquetes y acciones del módulo hyprland.", scripts("hyprland/install_hyprland.sh")),
        Category("mango", "MangoWM", "Instala MangoWM desde AUR", package_text("mangowm-git"), scripts("mango/install_mango.sh")),
        Category("waybar", "Waybar", "Instala Waybar", package_text("waybar", "python-gobject"), scripts("waybar/install_waybar.sh")),
        Category("noctalia", "Noctalia Shell", "Instala Noctalia Shell desde AUR", package_text("noctalia-shell"), scripts("noctalia/install_noctalia.sh")),
        Category("swaync", "swaync", "Centro de notificaciones", package_text("swaync", "python-gobject"), scripts("swaync/install_swaync.sh")),
        Category("wlogout", "wlogout", "Menú de apagado/logout", package_text("wlogout"), scripts("wlogout/install_wlogout.sh")),
        Category("rofi", "Rofi", "Launcher y applets", package_text("rofi"), scripts("rofi/install_rofi.sh")),
        Category("kitty", "Kitty", "Terminal Kitty", package_text("kitty"), scripts("kitty/install_kitty.sh")),
        Category("keyring", "GNOME Keyring", "Keyring, libsecret y agente SSH", package_text("gnome-keyring", "libsecret", "seahorse", "gcr-4"), scripts("keyring/install_keyring.sh", "keyring/configure_keyring.sh")),
        Category("keepassxc", "KeePassXC", "Alternativa a GNOME Keyring", package_text("keepassxc", "libsecret"), scripts("keepassxc/install_keepassxc.sh")),
    ),
)

SOFTWARE_SECTION = Section(
    "software",
    "Install software",
    "Programas de uso común agrupados en entradas seleccionables",
    (
        Category("firefox", "Firefox", "Navegador Firefox", package_text("firefox"), internal_runner=install_pacman_packages("Firefox", ["firefox"])),
        Category("google_chrome", "Google Chrome", "Navegador Google Chrome desde AUR", package_text("google-chrome"), internal_runner=install_yay_packages("Google Chrome", ["google-chrome"])),
        Category("discord", "Discord", "Cliente Discord", package_text("discord"), internal_runner=install_pacman_packages("Discord", ["discord"])),
        Category("obsidian", "Obsidian", "Notas Markdown", package_text("obsidian"), internal_runner=install_pacman_packages("Obsidian", ["obsidian"])),
        Category("onlyoffice", "OnlyOffice", "Suite ofimática desde AUR", package_text("onlyoffice-bin"), internal_runner=install_yay_packages("OnlyOffice", ["onlyoffice-bin"])),
        Category("media_tools", "Multimedia", "Reproductor, imágenes y descargas", package_text("mpv", "gimp", "yt-dlp", "ffmpeg"), internal_runner=install_pacman_packages("Multimedia", ["mpv", "gimp", "yt-dlp", "ffmpeg"])),
        Category("dev_tools", "Dev tools", "Herramientas de desarrollo frecuentes", package_text("github-cli", "lazygit", "jdk-openjdk", "nodejs", "npm", "uv"), internal_runner=install_pacman_packages("Dev tools", ["github-cli", "lazygit", "jdk-openjdk", "nodejs", "npm", "uv"])),
        Category("terminal_tools", "Terminal tools", "CLI de uso diario", package_text("btop", "eza", "fd", "ripgrep", "fzf", "fastfetch", "zoxide", "trash-cli", "tree"), internal_runner=install_pacman_packages("Terminal tools", ["btop", "eza", "fd", "ripgrep", "fzf", "fastfetch", "zoxide", "trash-cli", "tree"])),
        Category("desktop_utilities", "Desktop utilities", "Utilidades Wayland/escritorio comunes", package_text("brightnessctl", "playerctl", "udiskie", "python-gobject", "cliphist", "wl-clipboard", "grim", "slurp"), internal_runner=install_pacman_packages("Desktop utilities", ["brightnessctl", "playerctl", "udiskie", "python-gobject", "cliphist", "wl-clipboard", "grim", "slurp"])),
        Category("fonts", "Fonts", "Fuentes y emojis", package_text("ttf-jetbrains-mono-nerd", "noto-fonts-emoji", "ttf-dejavu", "woff2-font-awesome"), internal_runner=install_pacman_packages("Fonts", ["ttf-jetbrains-mono-nerd", "noto-fonts-emoji", "ttf-dejavu", "woff2-font-awesome"])), 
        Category("printing_sharing", "Printing / sharing", "Impresión, Samba y mDNS", package_text("cups", "cups-pdf", "cups-pk-helper", "gutenprint", "system-config-printer", "samba", "nss-mdns"), internal_runner=install_pacman_packages("Printing / sharing", ["cups", "cups-pdf", "cups-pk-helper", "gutenprint", "system-config-printer", "samba", "nss-mdns"])),
        Category("network_tools", "Network tools", "Utilidades de red", package_text("net-tools", "nmap", "rsync"), internal_runner=install_pacman_packages("Network tools", ["net-tools", "nmap", "rsync"])),
        Category("tts_tools", "TTS tools", "Piper/espeak para texto a voz", package_text("espeak-ng", "piper-tts", "piper-voices-es-ar"), internal_runner=install_yay_packages("TTS tools", ["espeak-ng", "piper-tts", "piper-voices-es-ar"])),
        Category("homebrew", "Homebrew", "Instala Homebrew global y de usuario", "Instala Homebrew y shellenv.", scripts("homebrew/install_homebrew.sh")),
        Category("docker", "Docker", "Docker y docker-compose", package_text("docker", "docker-compose"), scripts("docker/install_docker.sh")),
        Category("nvim", "Neovim", "Neovim desde pacman y dependencias", "Instalador completo del módulo nvim.", scripts("nvim/install.sh")),
        Category("yazi", "Yazi", "File manager Yazi", "Instalador completo del módulo yazi.", scripts("yazi/install_yazi.sh")),
        Category("mongodb_compass", "MongoDB Compass", "GUI oficial MongoDB", "Descarga release oficial e instala en /opt.", scripts("mongodb_compass/install_compass.sh")),
        Category("opencode", "Opencode", "Opencode CLI/config", "Instalador oficial de Opencode.", scripts("opencode/install_opencode.sh")),
        Category("claude_code", "Claude Code", "Claude Code CLI", "Instalador oficial de Claude Code.", scripts("claude_code/install_claude_code.sh")),
        Category("codex", "Codex", "Codex CLI via Homebrew", "Requiere Homebrew.", scripts("codex/install_codex.sh")),
        Category("intellij", "IntelliJ IDEA", "IntelliJ IDEA Ultimate oficial", "Descarga desde API oficial JetBrains.", scripts("intellij/install_intellij.sh")),
        Category("ssh", "SSH", "Configura claves SSH", "Módulo interactivo de SSH.", scripts("ssh/install_ssh.sh")),
        Category("zsh", "Zsh setup", "Zsh, Oh My Zsh y plugins", "Ejecuta pre_install.sh.", scripts("pre_install.sh")),
    ),
)

SECTIONS = (BASE_SECTION, DESKTOP_SECTION, SOFTWARE_SECTION)

MAIN_ACTIONS = (
    MenuAction("base", "Install base", BASE_SECTION.summary, "install_base"),
    MenuAction("desktop_bar", "Install desktop / bar", DESKTOP_SECTION.summary, "install_desktop_bar"),
    MenuAction("software", "Install software", SOFTWARE_SECTION.summary, "install_software"),
    MenuAction("import_configs", "Import configs", "Repo -> ~/.config, compara, confirma diferencias y crea backup", "import_configs"),
    MenuAction("export_configs", "Export configs", "~/.config -> repo, compara y confirma diferencias", "export_configs"),
    MenuAction("exit", "Exit", "Salir sin hacer cambios", "exit"),
)


class InstallerApp:
    def __init__(self, stdscr: curses.window) -> None:
        self.stdscr = stdscr
        self.selections: dict[str, bool] = {}
        self.message = "↑/↓ navegar · Enter abrir · S salir"
        self.load_selections()

    def load_selections(self) -> None:
        if not CONFIG_FILE.exists():
            return
        for raw_line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
            if not raw_line or raw_line.startswith("#") or "=" not in raw_line:
                continue
            key, value = raw_line.split("=", 1)
            if value in {"ON", "OFF"}:
                self.selections[key] = value == "ON"

    def save_selections(self) -> None:
        lines = ["# init-install selections"]
        for key in sorted(self.selections):
            lines.append(f"{key}={'ON' if self.selections[key] else 'OFF'}")
        CONFIG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def add_line(self, y: int, x: int, text: str, attr: int = 0) -> None:
        height, width = self.stdscr.getmaxyx()
        if y >= height:
            return
        available = max(1, width - x - 1)
        self.stdscr.addnstr(y, x, text, available, attr)

    def pause_message(self, title: str, lines: list[str]) -> None:
        while True:
            self.stdscr.erase()
            height, _ = self.stdscr.getmaxyx()
            self.add_line(0, 0, title, curses.A_BOLD)
            visible_height = max(1, height - 2)
            for idx, line in enumerate(lines[:visible_height]):
                self.add_line(1 + idx, 0, line)
            self.add_line(height - 1, 0, "Presioná una tecla para continuar", curses.A_BOLD)
            self.stdscr.refresh()
            self.stdscr.getch()
            return

    def render_main(self, current_index: int) -> None:
        self.stdscr.erase()
        curses.curs_set(0)
        height, width = self.stdscr.getmaxyx()
        title = "INIT-INSTALL — Menú Principal"
        self.add_line(0, max(0, (width - len(title)) // 2), title, curses.A_BOLD)
        self.add_line(1, 0, "Elegí una sección. Todo funciona en TTY con curses.", curses.A_DIM)

        for index, action in enumerate(MAIN_ACTIONS):
            attr = curses.A_REVERSE if index == current_index else curses.A_NORMAL
            self.add_line(3 + index, 0, f"{index + 1}. {action.title}", attr)
            self.add_line(3 + index, 28, action.summary, attr)

        self.add_line(height - 2, 0, "Enter: abrir  ↑/↓: navegar  S/Q: salir", curses.A_BOLD)
        self.add_line(height - 1, 0, self.message)
        self.stdscr.refresh()

    def main_menu(self) -> None:
        current_index = 0
        while True:
            self.render_main(current_index)
            key = self.stdscr.getch()
            if key in (curses.KEY_UP, ord("k")):
                current_index = max(0, current_index - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                current_index = min(len(MAIN_ACTIONS) - 1, current_index + 1)
            elif ord("1") <= key <= ord(str(len(MAIN_ACTIONS))):
                current_index = int(chr(key)) - 1
                if self.dispatch_action(MAIN_ACTIONS[current_index]):
                    return
            elif key in (curses.KEY_ENTER, 10, 13):
                if self.dispatch_action(MAIN_ACTIONS[current_index]):
                    return
            elif key in (ord("s"), ord("S"), ord("q"), ord("Q"), 27):
                return

    def dispatch_action(self, action: MenuAction) -> bool:
        if action.callback_name == "exit":
            return True
        getattr(self, action.callback_name)()
        return False

    def install_base(self) -> None:
        self.run_category_section(BASE_SECTION)

    def install_desktop_bar(self) -> None:
        self.run_category_section(DESKTOP_SECTION)

    def install_software(self) -> None:
        self.run_category_section(SOFTWARE_SECTION)

    def run_category_section(self, section: Section) -> None:
        selected = self.choose_categories(section.categories, section.title, section.default_selected)
        if selected:
            self.run_installation(selected)

    def choose_categories(self, categories: tuple[Category, ...], title: str, default_selected: bool) -> list[Category]:
        current_index = 0
        top_index = 0
        number_buffer = ""
        for category in categories:
            self.selections.setdefault(category.key, default_selected)
        self.save_selections()

        while True:
            self.stdscr.erase()
            height, width = self.stdscr.getmaxyx()
            self.add_line(0, max(0, (width - len(title)) // 2), title, curses.A_BOLD)
            self.add_line(1, 0, "Espacio alterna · A ejecutar selección · V ver detalle · Q volver", curses.A_DIM)
            if number_buffer:
                self.add_line(2, 0, f"Número: {number_buffer} (Enter para alternar)", curses.A_DIM)

            list_height = max(1, height - 6)
            if current_index < top_index:
                top_index = current_index
            elif current_index >= top_index + list_height:
                top_index = current_index - list_height + 1

            for row, index in enumerate(range(top_index, min(len(categories), top_index + list_height))):
                category = categories[index]
                marker = "[x]" if self.selections.get(category.key, False) else "[ ]"
                attr = curses.A_REVERSE if index == current_index else curses.A_NORMAL
                self.add_line(4 + row, 0, f"{index + 1:>2}. {marker} {category.title}", attr)
                self.add_line(4 + row, 34, category.summary, attr)

            self.add_line(height - 2, 0, "A: Ejecutar  T: Toggle All  V: Ver  Q: Volver", curses.A_BOLD)
            self.add_line(height - 1, 0, self.message)
            self.stdscr.refresh()

            key = self.stdscr.getch()
            if key in (curses.KEY_UP, ord("k")):
                current_index = max(0, current_index - 1)
                number_buffer = ""
            elif key in (curses.KEY_DOWN, ord("j")):
                current_index = min(len(categories) - 1, current_index + 1)
                number_buffer = ""
            elif key in (curses.KEY_HOME,):
                current_index = 0
                number_buffer = ""
            elif key in (curses.KEY_END,):
                current_index = len(categories) - 1
                number_buffer = ""
            elif ord("0") <= key <= ord("9"):
                number_buffer = (number_buffer + chr(key)).lstrip("0") or "0"
                number_buffer = number_buffer[:2]
                self.message = "Presioná Enter para alternar esa entrada"
            elif key in (ord(" "), curses.KEY_ENTER, 10, 13):
                if number_buffer:
                    number = int(number_buffer)
                    number_buffer = ""
                    if 1 <= number <= len(categories):
                        current_index = number - 1
                        self.toggle_category(categories[current_index])
                    else:
                        self.message = "Número fuera de rango"
                else:
                    self.toggle_category(categories[current_index])
            elif key in (ord("t"), ord("T")):
                enable_all = not all(self.selections.get(category.key, False) for category in categories)
                for category in categories:
                    self.selections[category.key] = enable_all
                self.save_selections()
                self.message = "Todo activado" if enable_all else "Todo desactivado"
            elif key in (ord("v"), ord("V")):
                self.view_category(categories[current_index])
            elif key in (ord("a"), ord("A")):
                number_buffer = ""
                selected = [category for category in categories if self.selections.get(category.key, False)]
                if not selected:
                    self.message = "Nada seleccionado"
                else:
                    return selected
            elif key in (ord("q"), ord("Q"), ord("s"), ord("S"), 27):
                return []

    def toggle_category(self, category: Category) -> None:
        self.selections[category.key] = not self.selections.get(category.key, False)
        if self.selections[category.key]:
            for excluded in MUTUAL_EXCLUSIONS.get(category.key, []):
                self.selections[excluded] = False
        self.save_selections()
        self.message = f"Alternado: {category.title}"

    def view_category(self, category: Category) -> None:
        scroll = 0
        content = [category.title, "", category.summary, "", *category.packages.splitlines()]
        while True:
            self.stdscr.erase()
            height, width = self.stdscr.getmaxyx()
            wrapped: list[str] = []
            for line in content:
                wrapped.extend(textwrap.wrap(line, max(20, width - 2)) or [""])
            visible_height = max(1, height - 2)
            max_scroll = max(0, len(wrapped) - visible_height)
            scroll = max(0, min(scroll, max_scroll))
            for idx, line in enumerate(wrapped[scroll:scroll + visible_height]):
                self.add_line(idx, 0, line)
            self.add_line(height - 1, 0, "↑/↓ desplazar · q/Esc volver", curses.A_BOLD)
            self.stdscr.refresh()
            key = self.stdscr.getch()
            if key in (ord("q"), ord("Q"), 27):
                return
            if key in (curses.KEY_UP, ord("k")):
                scroll -= 1
            elif key in (curses.KEY_DOWN, ord("j")):
                scroll += 1
            elif key == curses.KEY_NPAGE:
                scroll += visible_height
            elif key == curses.KEY_PPAGE:
                scroll -= visible_height

    def draw_install_screen(self, current: int, total: int, category_title: str, logs: list[str]) -> None:
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()
        percent = int((current / total) * 100) if total else 100
        bar_width = max(10, min(width - 12, 50))
        filled = int((percent / 100) * bar_width)
        bar = "[" + "#" * filled + "-" * (bar_width - filled) + "]"
        self.add_line(0, 0, "Ejecutando selección", curses.A_BOLD)
        self.add_line(1, 0, f"[{current}/{total}] {category_title}")
        self.add_line(2, 0, f"Progreso: {bar} {percent}%")
        self.add_line(4, 0, "Salida:")
        log_height = max(1, height - 7)
        for idx, line in enumerate(logs[-log_height:]):
            self.add_line(5 + idx, 0, line)
        self.add_line(height - 1, 0, "No cierres la terminal durante la operación", curses.A_DIM)
        self.stdscr.refresh()

    def run_script(self, script_path: str, current: int, total: int, category_title: str, logs: list[str]) -> None:
        script = Path(script_path)
        if not script.exists():
            raise FileNotFoundError(f"No se encontró el script: {script}")
        script.chmod(script.stat().st_mode | 0o111)
        process = subprocess.Popen(
            ["bash", str(script)],
            cwd=SCRIPT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in iter(process.stdout.readline, ""):
            logs.append(strip_ansi(line.rstrip()))
            self.draw_install_screen(current, total, category_title, logs)
        process.stdout.close()
        return_code = process.wait()
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, process.args)

    def run_installation(self, selected: list[Category]) -> None:
        all_logs: list[str] = []
        for index, category in enumerate(selected, start=1):
            category_logs = [f"==> {category.title}"]
            self.draw_install_screen(index, len(selected), category.title, category_logs)
            try:
                if category.internal_runner is not None:
                    category_logs.extend(category.internal_runner())
                    self.draw_install_screen(index, len(selected), category.title, category_logs)
                else:
                    for script in category.scripts:
                        self.run_script(script, index, len(selected), category.title, category_logs)
                category_logs.append(f"Completado: {category.title}")
                all_logs.extend(category_logs)
                self.draw_install_screen(index, len(selected), category.title, category_logs)
                time.sleep(0.4)
            except Exception as exc:
                category_logs.append(f"ERROR: {exc}")
                all_logs.extend(category_logs)
                self.draw_install_screen(index, len(selected), category.title, category_logs)
                self.pause_message("La operación falló", category_logs[-20:])
                self.message = f"Falló: {category.title}"
                return
        self.pause_message("Operación finalizada correctamente", all_logs[-20:] or ["Sin salida"])
        self.message = "Operación completada"

    def import_configs(self) -> None:
        self.run_config_section("import")

    def export_configs(self) -> None:
        self.run_config_section("export")

    def run_config_section(self, direction: str) -> None:
        title = "Import configs" if direction == "import" else "Export configs"
        if direction == "export":
            self.pause_message(
                "Aviso antes de exportar configs",
                [
                    "Export configs copia archivos desde ~/.config hacia este repo.",
                    "Revisa bien la selección para no guardar datos privados por accidente.",
                    "El sync ignora .git, node_modules, __pycache__ y .cache, pero no inspecciona contenidos.",
                    "Si una config del repo difiere, se creará backup antes de actualizarla.",
                ],
            )
        categories = tuple(
            Category(
                f"config_{direction}_{target.key}",
                target.title,
                f"{target.repo_relative} {'->' if direction == 'import' else '<-'} {target.home_relative}",
                f"Repo: {target.repo_relative}\nHome: {target.home_relative}",
            )
            for target in DEFAULT_CONFIG_TARGETS
        )
        selected_items = self.choose_categories(categories, title, default_selected=True)
        if not selected_items:
            return
        selected_keys = {item.key.removeprefix(f"config_{direction}_") for item in selected_items}
        targets = [target for target in DEFAULT_CONFIG_TARGETS if target.key in selected_keys]
        self.execute_config_sync(direction, targets)

    def execute_config_sync(self, direction: str, targets: list) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup_root = IMPORT_BACKUP_ROOT if direction == "import" else EXPORT_BACKUP_ROOT
        logs: list[str] = []
        total = len(targets)
        for index, target in enumerate(targets, start=1):
            if direction == "import":
                source = target.repo_path(SCRIPT_DIR)
                destination = target.home_path(Path.home())
            else:
                source = target.home_path(Path.home())
                destination = target.repo_path(SCRIPT_DIR)
            plan = compare_paths(target.key, source, destination)
            logs.append(f"[{target.title}] {plan.summary}")
            self.draw_install_screen(index, total, target.title, logs)

            confirmed = True
            if plan.needs_confirmation:
                confirmed = self.confirm_config_replace(direction, target.title, plan)

            result = apply_sync_plan(plan, backup_root=backup_root, confirmed=confirmed, timestamp=timestamp)
            if result.backup_path:
                logs.append(f"Backup: {result.backup_path}")
            logs.append(f"Resultado: {target.title}: {result.action} {result.message}".strip())
            self.draw_install_screen(index, total, target.title, logs)
            time.sleep(0.2)
        self.pause_message("Config sync finalizado", logs[-30:] or ["Sin cambios"])
        self.message = "Config sync completado"

    def confirm_config_replace(self, direction: str, target_title: str, plan: SyncPlan) -> bool:
        action = "importar desde repo" if direction == "import" else "exportar hacia repo"
        while True:
            self.stdscr.erase()
            height, _ = self.stdscr.getmaxyx()
            self.add_line(0, 0, f"Confirmar actualización: {target_title}", curses.A_BOLD)
            lines = [
                f"Acción: {action}",
                f"Fuente: {plan.source}",
                f"Destino: {plan.destination}",
                "",
                plan.summary,
                "",
                "Si confirmas, primero se crea backup del destino.",
                "Luego se copian solo archivos nuevos/modificados desde la fuente.",
                "Los archivos extra que existan solo en destino se conservan.",
                "No se muestran contenidos para evitar exponer datos sensibles.",
                "",
                "S: confirmar  N/Q/Esc: omitir",
            ]
            for idx, line in enumerate(lines[: max(1, height - 2)]):
                self.add_line(2 + idx, 0, line)
            self.stdscr.refresh()
            key = self.stdscr.getch()
            if key in (ord("s"), ord("S"), ord("y"), ord("Y")):
                return True
            if key in (ord("n"), ord("N"), ord("q"), ord("Q"), 27):
                return False

    def run(self) -> None:
        self.stdscr.keypad(True)
        self.main_menu()


def validate_environment() -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("Este script requiere ejecutarse en una TTY interactiva.")
    for command in ("bash", "sudo"):
        if shutil.which(command) is None:
            raise SystemExit(f"Falta el comando requerido: {command}")
    if shutil.which("pacman") is None:
        raise SystemExit("Este script está pensado para Arch/derivados (pacman no encontrado).")
    subprocess.run(["sudo", "-v"], check=True)


def main(stdscr: curses.window) -> None:
    curses.use_default_colors()
    app = InstallerApp(stdscr)
    app.run()


if __name__ == "__main__":
    validate_environment()
    curses.wrapper(main)
