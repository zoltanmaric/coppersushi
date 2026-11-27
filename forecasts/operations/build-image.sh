#!/usr/bin/env bash
set -euo pipefail
: "${1:?Supply an image tag}" "${2:?Supply the exact git revision}"
revision=$(git rev-parse --verify "$2^{commit}")
context=$(mktemp -d)
trap 'rm -rf "$context"' EXIT
git archive "$revision" pyproject.toml pixi.lock forecasts coppersushi/__init__.py coppersushi/pipelines/__init__.py coppersushi/pipelines/market_day.py coppersushi/pipelines/market_data coppersushi/pipelines/data_model coppersushi/pipelines/data_sources | tar -x -C "$context"
printf '%s\n' "$revision" > "$context/REVISION"
docker build --platform linux/amd64 --provenance=false --progress=plain \
    --label "org.opencontainers.image.revision=$revision" -f "$context/forecasts/operations/Dockerfile" -t "$1" "$context"
