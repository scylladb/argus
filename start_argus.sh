#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"
export PROMETHEUS_MULTIPROC_DIR="/tmp/promdb-argus-metrics"

if [[ ! -d "${PROMETHEUS_MULTIPROC_DIR}" ]]; then
    mkdir "${PROMETHEUS_MULTIPROC_DIR}"
fi

exec uv run gunicorn -c gunicorn.conf.py 'argus_backend:create_app()'
