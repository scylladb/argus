#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"

if [[ ! -d "/tmp/promdb-argus-metrics" ]]; then
    mkdir /tmp/promdb-argus-metrics
fi

exec uv run gunicorn -c gunicorn.conf.py 'argus_backend:create_app()'
