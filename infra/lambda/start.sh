#!/bin/sh
set -eu
mkdir -p "$COPPERSUSHI_DATA_DIR/jao"
cp data/jao/element-ends.csv "$COPPERSUSHI_DATA_DIR/jao/element-ends.csv"
if [ "${COPPERSUSHI_HANDLER:-app:server}" = "app:server" ]; then
  python -m coppersushi.data_sources.runtime_data check
fi
exec gunicorn --workers 1 --timeout "${GUNICORN_TIMEOUT:-120}" --worker-tmp-dir /tmp --bind 0.0.0.0:8080 "${COPPERSUSHI_HANDLER:-app:server}"
