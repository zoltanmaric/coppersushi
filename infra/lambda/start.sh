#!/bin/sh
set -eu
exec gunicorn --workers 1 --timeout 120 --worker-tmp-dir /tmp --bind 0.0.0.0:8080 app:server
