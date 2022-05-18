#!/bin/bash
poetry run supervisord -c ./docker/config/supervisord.conf -n
