#!/usr/bin/env bash
# Create .venv/ from environment.yml, which stays the single source of
# dependency pins. Conda/Mamba users do not need this; see the README.
set -euo pipefail
cd "$(dirname "$0")/.."

# `  - pandas =3.0.5  # comment` -> `pandas==3.0.5`; skips channels and python
pins() {
    awk '/^[[:space:]]*-[[:space:]]/ {
        sub(/#.*/, "")
        gsub(/[[:space:]]/, "")
        sub(/^-/, "")
        split($0, dep, "=")
        if (dep[2] != "" && dep[1] != "python") print dep[1] "==" dep[2]
    }' environment.yml
}

python_pin() {
    awk -F= '/^[[:space:]]*-[[:space:]]*python[[:space:]]*=/ {
        gsub(/[[:space:]]/, "", $2); print $2
    }' environment.yml
}

# --allow-existing keeps a re-run idempotent instead of wiping the venv
uv venv --allow-existing --python "$(python_pin)"
# word splitting is intended: one shell word per pin
# shellcheck disable=SC2046
uv pip install $(pins)
