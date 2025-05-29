#!/bin/bash
uv run supervisord -c ./docker/config/supervisord.conf -n
