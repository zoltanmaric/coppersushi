#!/bin/sh
set -eu
mkdir -p "$COPPERSUSHI_DATA_DIR/jao"
cp data/jao/element-ends.csv "$COPPERSUSHI_DATA_DIR/jao/element-ends.csv"
exec gunicorn --workers 1 --timeout 120 --worker-tmp-dir /tmp --bind 0.0.0.0:8080 app:server
