#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"
export CQLENG_ALLOW_SCHEMA_MANAGEMENT=1
poetry run uwsgi --ini uwsgi.ini
