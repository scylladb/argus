#!/bin/bash
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
export CQLENG_ALLOW_SCHEMA_MANAGEMENT=1
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
pyenv activate argus
uwsgi --ini uwsgi.ini
