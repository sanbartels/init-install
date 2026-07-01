#!/bin/bash

set -euo pipefail

if ! command -v opencode >/dev/null 2>&1; then
    curl -fsSL https://opencode.ai/install | bash
fi
