#!/usr/bin/env bash
# Entrypoint: starts as root so we can fix ownership of freshly-mounted
# named volumes (Docker creates those root-owned regardless of the image),
# hydrates /home/ftg/.venv from the immutable seed at /opt/gtg-venv on
# first run, reconciles deps, then drops to user ftg to run the bot.

set -euo pipefail

SEED=/opt/gtg-venv
RUNTIME_VENV=${VIRTUAL_ENV:-/home/ftg/.venv}
DATA_DIR=/home/ftg/.local/share/friendly-telegram

# 0. Heal volume ownership while we're still root. Docker mounts named
#    volumes with root:root, ignoring whatever owner the mount point had
#    in the image — so on every fresh-volume boot ftg can't write here
#    until we chown. Also covers volumes created by an older Dockerfile
#    that didn't pre-chown the mount point.
if [ "$(id -u)" = "0" ]; then
    chown -R ftg:ftg "$RUNTIME_VENV" "$DATA_DIR" 2>/dev/null || true
fi

# 1. First run: volume is empty (just created by docker). Copy the seed.
if [ ! -e "$RUNTIME_VENV/bin/python" ]; then
    echo "🌱 Seeding venv from $SEED → $RUNTIME_VENV ..."
    # Use cp -a to preserve permissions and symlinks. The trailing /. copies
    # the seed *contents* into the existing volume mount point, not as a
    # subdirectory.
    runuser -u ftg -- cp -a "$SEED/." "$RUNTIME_VENV/"
fi

# 2. Reconcile with pyproject.toml + uv.lock — fast no-op if nothing changed,
#    pulls in deltas after `pip` upgrades, fixes broken installs from
#    interrupted .loadmod runs. Note: --frozen so we never silently update
#    transitive deps; bump uv.lock in source if you want new versions.
echo "🔄 Reconciling venv with uv.lock ..."
runuser -u ftg -- env \
    "VIRTUAL_ENV=$RUNTIME_VENV" \
    "UV_PROJECT_ENVIRONMENT=$RUNTIME_VENV" \
    "PATH=$RUNTIME_VENV/bin:$PATH" \
    uv sync --frozen --no-dev --project /home/ftg

# 3. Hand off to the real command as ftg (defaults to ``gtg --port 8888``
#    from the Dockerfile CMD).
exec runuser -u ftg -- "$@"
