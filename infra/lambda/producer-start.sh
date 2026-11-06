#!/bin/sh
set -eu
exec gunicorn --workers 1 --timeout 900 --worker-tmp-dir /tmp --bind 0.0.0.0:8080 publication_worker:server
