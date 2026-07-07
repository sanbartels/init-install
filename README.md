# init-install

Scripts bash/Python modulares para replicar y mantener el setup real del usuario sobre Arch Linux.

## Uso

```bash
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
- GNOME Keyring

Hyprland queda como único compositor gestionado por este dot installer. Los wallpapers se gestionan con Hyprpaper usando `~/.config/wallpapers` en orden aleatorio cada 15 minutos.

### Install software

Lista programas de uso común y solo instala lo seleccionado. Incluye navegadores, Discord con dependencias de compartir pantalla en Wayland, dev tools, terminal tools, multimedia, fuentes, Docker, Neovim, Yazi, MongoDB Compass, Opencode, Claude Code, Codex, IntelliJ, SSH y Zsh con Oh My Zsh/plugins/aliases activados mediante bloque gestionado en `~/.zshrc`.

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
