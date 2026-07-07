#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
print_success() { echo -e "${GREEN}[OK]${NC} $*"; }
die() { echo -e "${RED}Error: $*${NC}" >&2; exit 1; }

INSTALL_URL="https://antigravity.google/cli/install.sh"
LOCAL_BIN_DIR="$HOME/.local/bin"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Falta el comando requerido: $1"
}

append_if_missing() {
    local file="$1"
    local line="$2"

    touch "$file"

    if ! grep -Fqx "$line" "$file"; then
        printf '\n%s\n' "$line" >> "$file"
        print_info "Agregada configuración en $file"
    fi
}

require_cmd curl
require_cmd bash

if command -v agy >/dev/null 2>&1; then
    print_info "Antigravity CLI ya está instalado: $(command -v agy)"
else
    print_info "Instalando Antigravity CLI con el instalador oficial..."
    curl -fsSL https://antigravity.google/cli/install.sh | bash
fi

mkdir -p "$LOCAL_BIN_DIR"

if [[ ":$PATH:" != *":$LOCAL_BIN_DIR:"* ]]; then
    append_if_missing "$HOME/.zshrc" "$PATH_LINE"
    append_if_missing "$HOME/.bashrc" "$PATH_LINE"
fi

if command -v agy >/dev/null 2>&1; then
    print_success "Antigravity CLI listo para usar"
    agy --version
else
    die "La instalación terminó pero el comando 'agy' no está disponible todavía. Abre una nueva shell o revisa $LOCAL_BIN_DIR."
fi
