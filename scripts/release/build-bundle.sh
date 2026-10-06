#!/usr/bin/env bash
# build-bundle.sh — assemble the self-contained Argus release bundle.
#
# Run this INSIDE a manylinux_2_34 container so every native wheel keeps a
# glibc 2.34 floor (RHEL/Rocky 9+, Ubuntu 22.04+):
#
#   yarn install --frozen-lockfile && NODE_ENV=production yarn build   # on the host, first
#   docker run --rm -v "$PWD:/io" -w /io quay.io/pypa/manylinux_2_34_x86_64 \
#       bash scripts/release/build-bundle.sh 1.2.3
#
# The bundle takes its architecture from the container. Use the _aarch64 image
# for an arm64 bundle. Build on a native runner: emulation is slow and the
# release workflow has no reason to use it.
#
# The bundle carries its own CPython, so it needs no Python, no uv and no
# network on the target host. The frontend is built on the host beforehand,
# because this container has no Node. Extract the bundle and start the units.
#
# Layout, which is the contract with roles/argus in scylladb/qatools
# (tasks/QATOOLS-393/spec.md here and there):
#   argus/ argusAI/ argus_backend.py gunicorn.conf.py templates/ public/
#             the application, the worker and their assets
#   scripts/migration/   the dated data migrations an operator runs by hand
#   config/   empty; the deployment links argus_web.yaml here, the first path
#             the application's loader tries
#   python/   relocatable CPython. It finds its stdlib next to its own binary.
#   lib/      every locked dependency of the web-backend and ai extras
#   bin/      argus-web, argus-cli, argus-ai-worker. Each one resolves its own
#             location, so the tree works at any path and through a symlink.
# A .pth file in python/ adds lib/ and the tree root through relative paths.
set -euo pipefail

VERSION="${1:?usage: build-bundle.sh <version>}"

PYTHON_VERSION="${PYTHON_VERSION:-3.13}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

DIST="$REPO_ROOT/dist"
BUNDLE="$DIST/argus-${VERSION}"

export UV_INSTALL_DIR="${UV_INSTALL_DIR:-$DIST/.uv-bin}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$DIST/.uv-python}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$DIST/.uv-cache}"
# Copies, not hard links, from the cache into the tree. uv hard-links by
# default, and anything that rewrites a file in the tree in place — strip
# preserves hard links by writing into the shared inode — then rewrites the
# cache too, and every later build reuses the damage.
export UV_LINK_MODE=copy
export PATH="$UV_INSTALL_DIR:$PATH"

# The container runs as root while the checkout belongs to the runner user.
git config --global --add safe.directory "$REPO_ROOT"

# Before anything is downloaded: the one input this script cannot make.
if [ ! -f "$REPO_ROOT/public/dist/main.bundle.js" ]; then
    echo "error: public/dist/main.bundle.js is missing." >&2
    echo "       Build the frontend on the host first:" >&2
    echo "       yarn install --frozen-lockfile && NODE_ENV=production yarn build" >&2
    exit 1
fi

command -v uv >/dev/null || \
    curl --proto '=https' --tlsv1.2 -LsSf https://astral.sh/uv/install.sh | sh

rm -rf "$BUNDLE"
mkdir -p "$BUNDLE"

echo "==> Source tree"
# git archive keeps build leftovers, caches and untracked files out of the
# bundle. It reads the last commit, so commit before you build.
#
# WHAT A HOST RUNS, and nothing else: the package, the worker, the factory,
# gunicorn's configuration, the templates, the static tree and the dated
# migration scripts an operator runs by hand. The test suites, the worker's
# eval harness and its hand-written unit file describe the repository to a
# developer and stay out. storage/ is not listed on purpose: the deployment
# links the persistent uploads at that path, and a directory there would stop
# it.
git archive --format=tar HEAD -- \
    argus argusAI argus_backend.py gunicorn.conf.py templates public scripts/migration \
    ':(exclude)argus/backend/tests' \
    ':(exclude)argusAI/eval' \
    ':(exclude)argusAI/tests' \
    ':(exclude)argusAI/deployment' \
    ':(exclude)argusAI/logs' \
    | tar -x -C "$BUNDLE"

echo "==> Frontend"
# Built on the host by `yarn build`, into a directory git ignores. Copied
# rather than archived for that reason.
cp -a "$REPO_ROOT/public/dist" "$BUNDLE/public/dist"

echo "==> Interpreter"
uv python install --managed-python "$PYTHON_VERSION"
PYTHON_SRC="$(find "$UV_PYTHON_INSTALL_DIR" -maxdepth 1 -type d \
    -name "cpython-${PYTHON_VERSION}.*" | sort | tail -1)"
[ -n "$PYTHON_SRC" ] || { echo "error: no managed CPython found" >&2; exit 1; }
cp -a "$PYTHON_SRC" "$BUNDLE/python"
BUNDLE_PYTHON="$BUNDLE/python/bin/python${PYTHON_VERSION}"

echo "==> Dependencies"
# Both extras: the web application and the argusAI worker run from one tree.
# --locked, not --frozen: frozen reads uv.lock as it is, locked also checks it
# against pyproject.toml and fails when an extra gained a package nobody ran
# `uv lock` for — the bundle would otherwise ship without it and the import
# would fail on the production host, past the self-check's top-level modules.
#
# The default `health` group comes along: it carries qatools-health, which the
# health process the gunicorn master starts imports. It is a path source in
# this repository, locked as editable, and an editable install into lib/ is a
# link back to this checkout — a path that exists here and on no host.
# --no-editable exports it as a plain path, which uv builds and installs into
# lib/ like any other dependency.
uv export --locked --no-dev --no-editable --no-emit-project --extra web-backend --extra ai \
    --format requirements.txt -o "$DIST/requirements.txt"
if grep -q '^-e ' "$DIST/requirements.txt"; then
    echo "error: the export still carries an editable requirement:" >&2
    grep '^-e ' "$DIST/requirements.txt" >&2
    exit 1
fi
# --target, not the interpreter's own site-packages: uv refuses to write into a
# Python it manages. The .pth below puts this directory back on sys.path.
uv pip install --python "$BUNDLE_PYTHON" --target "$BUNDLE/lib" \
    --requirements "$DIST/requirements.txt"
# The console scripts uv wrote carry the build interpreter's absolute path in
# their shebang. The shims below replace them.
rm -rf "$BUNDLE/lib/bin"

echo "==> Path wiring"
SITE="$BUNDLE/python/lib/python${PYTHON_VERSION}/site-packages"
# site-packages -> python3.13 -> lib -> python -> bundle root. The root is on
# the path too: argus_backend.py and the argus and argusAI packages live there,
# and argusAI has no __init__.py, so it resolves as a namespace package from
# whatever root the path names.
cat > "$SITE/argus-bundle.pth" <<'PTH'
../../../../lib
../../../..
PTH

echo "==> Console scripts"
mkdir -p "$BUNDLE/bin" "$BUNDLE/config"
# Hand-written shims. `readlink -f` resolves the shim through a symlink, so
# /opt/argus/current/bin/argus-web finds the release it lives in. The two the
# application runs through change into the tree, because it reads
# .argus_version and writes storage/ relative to its working directory. The
# worker's does not: its sanitizer log lands relative to the working
# directory, and the unit gives it a writable one of its own.
write_shim() {
    local name="$1" enter="$2"
    shift 2
    {
        printf '#!/bin/sh\n'
        printf '# Generated by scripts/release/build-bundle.sh. Do not edit.\n'
        printf 'set -eu\n'
        printf 'root=$(CDPATH= cd -- "$(dirname -- "$(readlink -f "$0")")/.." && pwd)\n'
        if [ "$enter" = "cd" ]; then
            printf 'cd "$root"\n'
        fi
        printf 'exec "$root/python/bin/python%s" %s "$@"\n' "$PYTHON_VERSION" "$*"
    } > "$BUNDLE/bin/$name"
    chmod 0755 "$BUNDLE/bin/$name"
}
write_shim argus-web cd '-m gunicorn -c "$root/gunicorn.conf.py" '"'"'argus_backend:create_app()'"'"''
write_shim argus-cli cd '-m argus.backend.cli'
write_shim argus-ai-worker stay '-m argusAI.event_similarity_processor_v2'

printf '%s\n' "$VERSION" > "$BUNDLE/VERSION"
git rev-parse HEAD > "$BUNDLE/COMMIT"
# What /api/v1/version answers: the application reads this file when
# `git rev-parse HEAD` fails, which it does in a tree with no .git.
cp "$BUNDLE/COMMIT" "$BUNDLE/.argus_version"

echo "==> Pruning"
# Drop what a server never runs: the stdlib self-test suite, the GUI stack,
# build headers, static libraries and installer scaffolding.
rm -rf \
    "$BUNDLE/python/include" \
    "$BUNDLE/python/share" \
    "$BUNDLE/python/lib/python${PYTHON_VERSION}/test" \
    "$BUNDLE/python/lib/python${PYTHON_VERSION}/idlelib" \
    "$BUNDLE/python/lib/python${PYTHON_VERSION}/tkinter" \
    "$BUNDLE/python/lib/python${PYTHON_VERSION}/turtledemo" \
    "$BUNDLE/python/lib/python${PYTHON_VERSION}/ensurepip" \
    "$BUNDLE/python/lib/python${PYTHON_VERSION}/config-${PYTHON_VERSION}"*
find "$BUNDLE/python/lib" -maxdepth 1 -name '*.a' -delete
rm -rf "$SITE/pip" "$SITE"/pip-*.dist-info
# The Tcl/Tk runtime, which deleting the tkinter package does not touch.
rm -rf \
    "$BUNDLE/python/lib"/libtcl*.so \
    "$BUNDLE/python/lib"/libtk*.so \
    "$BUNDLE/python/lib"/tcl* \
    "$BUNDLE/python/lib"/tk* \
    "$BUNDLE/python/lib"/itcl* \
    "$BUNDLE/python/lib"/thread*
# Console scripts for packages that are no longer here.
rm -f \
    "$BUNDLE/python/bin"/idle3* \
    "$BUNDLE/python/bin"/pip* \
    "$BUNDLE/python/bin"/pydoc3* \
    "$BUNDLE/python/bin"/2to3* \
    "$BUNDLE/python/bin"/*-config
# Dependency test suites. Nothing imports them, and the self-check below is
# what proves that: it imports the application and the worker after this runs.
find "$BUNDLE/lib" -type d \( -name tests -o -name testing \) -prune \
    -exec rm -rf {} + 2>/dev/null || true
# Debug symbols are dead weight in production — but only the interpreter's
# own are stripped. The wheels under lib/ were repaired by auditwheel, and
# binutils' strip corrupts some of the libraries it vendored: numpy's OpenBLAS
# came back with "ELF load command address/offset not properly aligned", which
# the self-check below caught. Those are already stripped by their builders.
find "$BUNDLE/python" -type f -name '*.so*' -exec strip --strip-unneeded {} + 2>/dev/null || true

echo "==> Bytecode"
# The release tree is read-only on the host, so Python cannot write bytecode
# there: whatever is compiled here is the only bytecode there will be, and
# every worker start would otherwise recompile the tree from source.
"$BUNDLE_PYTHON" -m compileall -q -j 0 "$BUNDLE/argus" "$BUNDLE/argusAI" "$BUNDLE/lib" >/dev/null

echo "==> Self-check"
# From another path than the build path, so an absolute path baked into the
# tree fails here rather than on the production host. Moved, not copied: the
# tree is large, and the checks read it in place.
RELOCATED="$DIST/selfcheck/argus-${VERSION}"
rm -rf "$DIST/selfcheck"
mkdir -p "$DIST/selfcheck"
mv "$BUNDLE" "$RELOCATED"
(
    cd /
    "$RELOCATED/bin/argus-cli" --help >/dev/null
    echo "argus-cli        : ok"
    "$RELOCATED/python/bin/python${PYTHON_VERSION}" -c "
import sys
import argus_backend, argusAI.event_similarity_processor_v2
import cassandra, coodie, chromadb, gunicorn, uvicorn
# What the gunicorn master runs as the health process, and the package it
# imports. A link back to the build checkout would resolve here only if this
# tree had not moved, which is why the check runs from the relocated path.
import argus.backend.service.health.__main__, qatools_health
assert '$RELOCATED' in qatools_health.__file__, qatools_health.__file__
print('python           :', sys.version.split()[0])
print('argus_backend    :', argus_backend.__file__)
print('argusAI worker   :', argusAI.event_similarity_processor_v2.__file__)
print('qatools_health   :', qatools_health.__file__)
"
    [ -f "$RELOCATED/public/dist/main.bundle.js" ] || { echo "error: the built frontend is not in the bundle" >&2; exit 1; }
    [ -f "$RELOCATED/templates/base.html.j2" ] || { echo "error: the templates are not in the bundle" >&2; exit 1; }
    [ "$(cat "$RELOCATED/VERSION")" = "$VERSION" ] || { echo "error: VERSION disagrees with $VERSION" >&2; exit 1; }
    [ ! -e "$RELOCATED/storage" ] || { echo "error: the bundle carries storage/, which the deployment links" >&2; exit 1; }
    echo "assets, version  : ok"
)
mv "$RELOCATED" "$BUNDLE"
rmdir "$DIST/selfcheck"

echo "==> Done: $BUNDLE"
du -sh "$BUNDLE"
