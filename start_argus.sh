#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"
export CQLENG_ALLOW_SCHEMA_MANAGEMENT=1

if [[ ! -d "/tmp/promdb-argus-metrics" ]]; then
    mkdir /tmp/promdb-argus-metrics
fi

exec uv run uwsgi --master --ini uwsgi.ini --need-app
