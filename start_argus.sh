#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"
export CQLENG_ALLOW_SCHEMA_MANAGEMENT=1
exec uv run uwsgi --master --ini uwsgi.ini --need-app
