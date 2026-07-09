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
- WayVNC como escritorio remoto normal sobre Tailscale
- GNOME Keyring

Hyprland queda como único compositor gestionado por este dot installer. Los wallpapers se gestionan con Hyprpaper usando `~/.config/wallpapers` en orden aleatorio cada 15 minutos.

Para escritorio remoto, la opción normal es WayVNC enlazado solo a la IP Tailscale del equipo. Sunshine se conserva instalado como material de rollback, pero el instalador normal lo desactiva porque el VPS actual no ofrece una ruta gráfica/GPU fiable para Sunshine.

Remote desktop operational notes:

- Install from the menu: `Install desktop / bar -> WayVNC`. The installer creates `~/.local/bin/init-install-wayvnc` and `~/.config/systemd/user/wayvnc.service`.
- Reruns are least-privilege: if `wayvnc`, `tailscale`, and an enabled/active `tailscaled.service` are already present, the installer skips privileged package/service remediation. Fresh hosts still need non-interactive `sudo` for missing packages or inactive/disabled `tailscaled.service`.
- The launcher discovers the current Tailscale IPv4 dynamically, waits for the active Hyprland/Wayland session, targets `Virtual-1`, uses `--keyboard=us`, and binds only to `<tailscale-ip>:5900`.
- Verify and recover with:

  ```bash
  systemctl --user status wayvnc.service --no-pager
  journalctl --user -u wayvnc.service -b --no-pager
  ss -tlnp | grep ':5900'
  systemctl --user restart wayvnc.service
  systemctl --user disable --now wayvnc.service
  ```

- If the managed service must be rolled back over SSH, stop it first and start a temporary WayVNC process with the same managed launcher/session discovery:

  ```bash
  systemctl --user disable --now wayvnc.service
  WAYVNC_SOCKET_ROLE=rollback WAYVNC_BIND_PORT=5900 ~/.local/bin/init-install-wayvnc
  ```

  The installer never uses the default WayVNC control socket. Its control sockets are derived from strict launcher roles (`probe`, `managed`, `rollback`) and live under `$XDG_RUNTIME_DIR/init-install-wayvnc/` with mode `0700`, so manual WayVNC processes can keep using `$XDG_RUNTIME_DIR/wayvncctl` or `/tmp/wayvncctl-$UID` untouched. If a previous managed socket exists, the launcher removes it only after proving it is the exact installer-owned socket, `wayvncctl -S` is not responsive, and `ss -xap` shows no live Unix socket process referencing the exact path; ambiguous cases fail closed. Same-user pathname sockets still have an unavoidable time-of-check/time-of-use race, so the launcher rechecks immediately before unlinking.

  If the launcher itself is unavailable, use the same non-default control socket shape manually after confirming the active Tailscale IP and Hyprland session:

  ```bash
  tailscale ip -4
  hyprctl instances -j
  hyprctl monitors -j
  mkdir -p "$XDG_RUNTIME_DIR/init-install-wayvnc"
  chmod 700 "$XDG_RUNTIME_DIR/init-install-wayvnc"
  wayvnc -S "$XDG_RUNTIME_DIR/init-install-wayvnc/manual-5900-$$.sock" -L info --keyboard=us --output=Virtual-1 <tailscale-ip>:5900
  ```

- Re-enable Sunshine only as an explicit rollback path after stopping WayVNC and accepting the current VPS graphics limitations:

  ```bash
  systemctl --user disable --now wayvnc.service
  systemctl --user enable --now app-dev.lizardbyte.app.Sunshine.service
  journalctl --user -u app-dev.lizardbyte.app.Sunshine.service -b --no-pager
  ss -tlnp | grep -E ':(47984|47989|47990)'
  ```

- Listener verification must show the current Tailscale IP only, for example `100.x.y.z:5900`; public/all-interface bindings such as `0.0.0.0:5900`, `*:5900`, `[::]:5900`, localhost-only, or unexpected addresses are rejected.
- The installer disables known Sunshine user units (`app-dev.lizardbyte.app.Sunshine.service`, `sunshine.service`) and removes only the managed `~/.config/systemd/user/sunshine.service` symlink when it points at the packaged unit. It does not remove the Sunshine package, `~/.config/sunshine`, credentials, apps, logs, or state.
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
