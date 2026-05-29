#!/bin/zsh
set -euo pipefail

PROJECT_ROOT="/Volumes/External2TB/Xcode/TGRV"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
CACHE_ROOT="$PROJECT_ROOT/.cache"
MPLCONFIGDIR="$CACHE_ROOT/matplotlib"
XDG_CACHE_HOME="$CACHE_ROOT"

cd "$PROJECT_ROOT"
mkdir -p "$MPLCONFIGDIR" "$XDG_CACHE_HOME"

if [ -x "$VENV_PYTHON" ]; then
  exec env MPLCONFIGDIR="$MPLCONFIGDIR" XDG_CACHE_HOME="$XDG_CACHE_HOME" "$VENV_PYTHON" -m touchprint_lab.tests.runner
fi

if command -v python3 >/dev/null 2>&1; then
  exec env MPLCONFIGDIR="$MPLCONFIGDIR" XDG_CACHE_HOME="$XDG_CACHE_HOME" python3 -m touchprint_lab.tests.runner
fi

exec env MPLCONFIGDIR="$MPLCONFIGDIR" XDG_CACHE_HOME="$XDG_CACHE_HOME" python -m touchprint_lab.tests.runner
