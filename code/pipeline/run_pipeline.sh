#!/usr/bin/env bash
# Portable bundle entry point. No PID files or historical result polling.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE="${LLM_MT_BUNDLE:-$HERE}"
while [ ! -f "$BUNDLE/code/run_pipeline.py" ]; do
    PARENT="$(dirname "$BUNDLE")"
    if [ "$PARENT" = "$BUNDLE" ]; then
        echo "Cannot locate the bundle; set LLM_MT_BUNDLE to its root." >&2
        exit 2
    fi
    BUNDLE="$PARENT"
done
PY="${PYTHON:-python}"
command -v "$PY" >/dev/null 2>&1 || PY=python3
exec "$PY" "$BUNDLE/code/run_pipeline.py" "$@"
