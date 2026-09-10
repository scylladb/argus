#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"
exec uv run python -m argus.backend.cli scan-jenkins
