#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
print_success() { echo -e "${GREEN}[OK]${NC} $*"; }
die() { echo -e "${RED}Error: $*${NC}" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || die "Falta curl"
command -v jq >/dev/null 2>&1 || die "Falta jq"
command -v wget >/dev/null 2>&1 || die "Falta wget"
command -v tar >/dev/null 2>&1 || die "Falta tar"

INSTALL_DIR="/opt/mongo/mongoDBCompass"
EXECUTABLE="$INSTALL_DIR/MongoDB Compass"
VERSION_FILE="$INSTALL_DIR/.version"
DESKTOP_FILE="$HOME/.local/share/applications/mongodb-compass.desktop"
TMP_DIR="$(mktemp -d)"

trap 'rm -rf "$TMP_DIR"' EXIT

print_info "Obteniendo última versión de MongoDB Compass..."
URL="$(curl -sL https://api.github.com/repos/mongodb-js/compass/releases/latest | jq -r '.assets[].browser_download_url' | grep -E 'mongodb-compass-[0-9]+\.[0-9]+\.[0-9]+-linux-x64\.tar\.gz$' | grep -v 'isolated' | grep -v 'readonly' | head -n1)"
[ -n "$URL" ] || die "No se pudo obtener la descarga de Compass"

VERSION="$(printf '%s' "$URL" | grep -oP 'mongodb-compass-\K[0-9]+\.[0-9]+\.[0-9]+')"
[ -n "$VERSION" ] || die "No se pudo obtener la versión de Compass"
print_info "Última versión disponible: v$VERSION"

if [ -f "$VERSION_FILE" ] && [ "$(cat "$VERSION_FILE")" = "$VERSION" ] && [ -x "$EXECUTABLE" ]; then
    print_success "MongoDB Compass v$VERSION ya está instalado"
    exit 0
fi

if [ -f "$VERSION_FILE" ] && [ "$(cat "$VERSION_FILE")" = "$VERSION" ] && [ ! -x "$EXECUTABLE" ]; then
    print_info "La versión v$VERSION figura instalada, pero falta el ejecutable. Reinstalando..."
fi

print_info "Descargando MongoDB Compass v$VERSION..."
wget --show-progress -O "$TMP_DIR/compass.tar.gz" "$URL"

print_info "Extrayendo archivos..."
tar -xzf "$TMP_DIR/compass.tar.gz" -C "$TMP_DIR"
EXTRACTED_DIR="$(find "$TMP_DIR" -maxdepth 1 -type d -name '*Compass*' | head -n1)"
[ -n "$EXTRACTED_DIR" ] || die "No se encontró el directorio extraído"

print_info "Instalando en $INSTALL_DIR..."
sudo rm -rf "$INSTALL_DIR"
sudo mkdir -p /opt/mongo
sudo mv "$EXTRACTED_DIR" "$INSTALL_DIR"
[ -x "$EXECUTABLE" ] || die "No se encontró el ejecutable instalado: $EXECUTABLE"
printf '%s\n' "$VERSION" | sudo tee "$VERSION_FILE" >/dev/null

mkdir -p "$HOME/.local/share/applications"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=MongoDB Compass
Comment=The GUI for MongoDB
Exec=env ELECTRON_OZONE_PLATFORM_HINT=auto "$INSTALL_DIR/MongoDB Compass" --ignore-additional-command-line-flags --password-store=gnome-libsecret
Icon=$INSTALL_DIR/resources/app/node_modules/@mongodb-js/compass/dist/main.png
Terminal=false
Type=Application
Categories=Development;Database;
Keywords=mongodb;database;compass;
StartupWMClass=MongoDB Compass
EOF

chmod +x "$DESKTOP_FILE"
