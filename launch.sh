#!/bin/bash
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
pyenv activate argus
uwsgi --socket 127.0.0.1:3031 --wsgi-file launch.py --callable app --processes 1 --threads 2 --buffer-size 20000
