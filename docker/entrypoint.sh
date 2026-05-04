#!/usr/bin/env bash
# Entrypoint: hydrate /home/ftg/.venv (a docker volume) from the immutable
# seed at /opt/gtg-venv on first run, then keep it in sync with the project's
# pyproject.toml/uv.lock on every start, then exec the real command.

set -euo pipefail

SEED=/opt/gtg-venv
RUNTIME_VENV=${VIRTUAL_ENV:-/home/ftg/.venv}

# 1. First run: volume is empty (just created by docker). Copy the seed.
if [ ! -e "$RUNTIME_VENV/bin/python" ]; then
    echo "🌱 Seeding venv from $SEED → $RUNTIME_VENV ..."
    # Use cp -a to preserve permissions and symlinks. The trailing /. copies
    # the seed *contents* into the existing volume mount point, not as a
    # subdirectory.
    cp -a "$SEED/." "$RUNTIME_VENV/"
fi

# 2. Reconcile with pyproject.toml + uv.lock — fast no-op if nothing changed,
#    pulls in deltas after `pip` upgrades, fixes broken installs from
#    interrupted .loadmod runs. Note: --frozen so we never silently update
#    transitive deps; bump uv.lock in source if you want new versions.
echo "🔄 Reconciling venv with uv.lock ..."
uv sync --frozen --no-dev --project /home/ftg

# 3. Hand off to the real command (defaults to ``gtg --port 8888`` from the
#    Dockerfile CMD).
exec "$@"
