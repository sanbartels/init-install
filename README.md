# init-install

Scripts bash/Python modulares para replicar y mantener el setup real del usuario sobre Arch Linux.

## Primer arranque en Arch mínimo

Si el sistema recién instalado no tiene `git`, instálalo antes de clonar el repo:

```bash
pacman -Syu --needed git sudo nano
```

Si estás conectado como `root`, crea un usuario normal antes de ejecutar el
instalador. El instalador escribe configs en `$HOME`, instala herramientas de
usuario y algunos módulos usan el usuario actual para grupos como `docker`.
Ejecutarlo como `root` dejaría esas configs bajo `/root`.

```bash
useradd -m -G wheel -s /bin/bash <usuario>
passwd <usuario>
EDITOR=nano visudo
```

En `visudo`, habilita la línea del grupo `wheel`:

```text
%wheel ALL=(ALL:ALL) ALL
```

Luego entra con el usuario nuevo:

```bash
su - <usuario>
```

## Uso

```bash
git clone https://github.com/sanbartels/init-install.git
cd init-install
./install.sh
```

`install.sh` valida Arch/Python/TTY y abre `install.py`, un menú interactivo en `curses`, usable desde TTY.

## Menú principal

El instalador está seccionado para no tener que recorrer todo cuando solo quieres hacer una tarea puntual:

1. **Install base**
2. **Install desktop / bar**
3. **Install software**
4. **Import configs**
5. **Export configs**
6. **Exit**

Las selecciones se guardan en:

```bash
~/.init-install.conf
```

## Secciones

### Install base

Instala la base mínima y drivers:

- sistema base
- yay como helper AUR
- Tailscale para acceso remoto privado
- red
- audio PipeWire
- códecs
- microcódigo CPU
- drivers GPU detectados
- TRIM
- post-install mínimo (`mimeapps`, comando `update`, guía `COMANDOS.md`)

### Install desktop / bar

Permite elegir componentes de escritorio:

- Hyprland
- swaync
- Rofi
- Kitty
- Sunshine para acceso remoto con Moonlight sobre Tailscale
- wayvnc como fallback VNC para Wayland
- GNOME Keyring

Hyprland queda como único compositor gestionado por este dot installer. Los wallpapers se gestionan con Hyprpaper usando `~/.config/wallpapers` en orden aleatorio cada 15 minutos.

Para escritorio remoto, la opción recomendada es Sunshine en el VPS y Moonlight en Mac/iPhone, conectando por IP Tailscale o MagicDNS. `wayvnc` queda disponible como fallback más simple.

Remote desktop operational notes:

- On Arch, Sunshine's user unit can be named `app-dev.lizardbyte.app.Sunshine.service`. The installer detects that unit before falling back to another valid Sunshine unit.
- Sunshine must run as the desktop user, not as root. When launching from SSH, enable linger for that user and verify the user service context with `systemctl --user`.
- Hyprland capture requires the user session stack: `pipewire`, `wireplumber`, `xdg-desktop-portal`, and `xdg-desktop-portal-hyprland`.
- If Sunshine is active but the web UI is unreachable, verify listeners with `ss -tlnp | grep -E ':(47984|47989|47990)'` and inspect `journalctl --user -u app-dev.lizardbyte.app.Sunshine.service -b --no-pager`.
- For WayVNC over Tailscale, start it from the active Hyprland session with explicit runtime/display variables and keyboard layout:

  ```bash
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-1}"
  export XKB_DEFAULT_LAYOUT=us
  export XKB_DEFAULT_VARIANT=
  export XKB_DEFAULT_OPTIONS=
  wayvnc --keyboard=us <tailscale-ip>:5900
  ```

- Do not treat Sunshine as remotely usable until listeners exist and are private to Tailscale. Public/all-interface bindings such as `0.0.0.0:47990`, `*:47990`, or `[::]:47990` require firewall/Tailscale exposure review before Moonlight pairing.
- Validate WayVNC keyboard input in `nano` or another real editor. Raw `cat` can show control/ANSI sequences such as `^H` and produce misleading results.
- If Ghostty looks dark or blurred through VNC, disable remote-session opacity/blur settings such as `background-opacity` and `background-blur-radius`, or use a clean test terminal profile.

SSH hardening is intentionally left as a post-verify manual step to avoid locking out a fresh VPS. After confirming a key-based login in a new session, disable password authentication, disable root login, reload `sshd`, and keep the existing session open until the new login succeeds.

### Install software

Lista programas de uso común y solo instala lo seleccionado. Incluye navegadores, Discord con dependencias de compartir pantalla en Wayland, dev tools, terminal tools, multimedia, fuentes, Docker, Neovim, Yazi, MongoDB Compass, Opencode, Claude Code, Codex, Antigravity CLI, IntelliJ, SSH y Zsh con Oh My Zsh/plugins/aliases activados mediante bloque gestionado en `~/.zshrc`.

### Import configs

Copia configs desde el repo hacia `~/.config`.

Reglas:

- compara antes de copiar
- si es igual, omite
- si no existe destino, copia sin backup
- si existe destino y es diferente, pide confirmación
- antes de reemplazar algo diferente, crea backup en:

```bash
~/.config_backups/init-install/<timestamp>/<target>/
```

- elimina el destino de configuración y copia la fuente completa desde el repo
- elimina archivos extra que existan solo en el destino local
- no muestra contenidos de archivos en la confirmación

### Export configs

Copia configs desde este sistema hacia el repo usando la misma lógica de comparación/confirmación.

Backups de configs del repo reemplazadas se guardan en:

```bash
.config_backups/exports/<timestamp>/<target>/
```

Se ignoran carpetas ruidosas o peligrosas durante sync, como `.git`, `node_modules`, `__pycache__` y `.cache`.

> Aviso: `Export configs` no inspecciona el contenido de archivos. Revisa la selección antes de exportar para no copiar datos privados al repo.

## Configs incluidas

- Hyprland/Hyprpaper: `hyprland/configs/`
- Kitty: `kitty/configs/`
- Rofi: `rofi/configs/`
- swaync: `swaync/configs/`
- Neovim: `nvim/configs/`
- Yazi: `yazi/configs/`

## Comandos de actualización

Después de la instalación, estos comandos pueden quedar disponibles en `~/.local/bin/`:

- `update` — actualiza sistema, AUR, Homebrew y herramientas soportadas
- `update_compass` — actualiza MongoDB Compass
- `intellij-update` — actualiza IntelliJ IDEA a la última versión

## Validación de desarrollo

```bash
python3 -m unittest discover -s tests
python3 -m py_compile install.py installer_lib/*.py
bash -n $(find . -name "*.sh" -not -path "./.git/*")
```

## Notas

- Las copias de configs son conservadoras y confirman antes de actualizar diferencias.
- MongoDB Compass se instala desde el binario oficial y usa GNOME Keyring/libsecret para guardar contraseñas.
- IntelliJ IDEA se instala desde la API oficial de JetBrains.
- Codex se instala vía Homebrew (`brew install codex`).
