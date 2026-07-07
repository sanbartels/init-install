#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
print_success() { echo -e "${GREEN}[OK]${NC} $*"; }
die() { echo -e "${RED}Error: $*${NC}" >&2; exit 1; }

INSTALL_URL="https://claude.ai/install.sh"
LOCAL_BIN_DIR="$HOME/.local/bin"
CLAUDE_BIN="$LOCAL_BIN_DIR/claude"
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

if command -v claude >/dev/null 2>&1; then
    CLAUDE_BIN="$(command -v claude)"
    print_info "Claude Code ya está instalado: $CLAUDE_BIN"
else
    print_info "Instalando Claude Code con el instalador oficial..."
    curl -fsSL "$INSTALL_URL" | bash
fi

mkdir -p "$LOCAL_BIN_DIR"

if [ -x "$LOCAL_BIN_DIR/claude" ]; then
    CLAUDE_BIN="$LOCAL_BIN_DIR/claude"
    print_info "Claude Code disponible en $CLAUDE_BIN"
fi

if [[ ":$PATH:" != *":$LOCAL_BIN_DIR:"* ]]; then
    append_if_missing "$HOME/.zshrc" "$PATH_LINE"
    append_if_missing "$HOME/.bashrc" "$PATH_LINE"
fi

if [ -x "$CLAUDE_BIN" ]; then
    export PATH="$LOCAL_BIN_DIR:$PATH"
    print_success "Claude Code listo para usar"
    "$CLAUDE_BIN" --version
else
    die "La instalación terminó pero no se encontró un binario ejecutable de Claude Code"
fi
