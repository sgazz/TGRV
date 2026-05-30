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
  PYTHON_BIN="$VENV_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  PYTHON_BIN="$(command -v python)"
fi

echo "Running Touchprint test suite"
echo "Python path: $PYTHON_BIN"

env MPLCONFIGDIR="$MPLCONFIGDIR" XDG_CACHE_HOME="$XDG_CACHE_HOME" "$PYTHON_BIN" - <<'PY'
import importlib
import sys
print(f"Python version: {sys.version.split()[0]}")
try:
    QtCore = importlib.import_module("PyQt6.QtCore")
    print(f"PyQt6 available: yes ({QtCore.QT_VERSION_STR})")
except Exception as exc:
    print(f"PyQt6 available: no ({exc})")
PY

exec env MPLCONFIGDIR="$MPLCONFIGDIR" XDG_CACHE_HOME="$XDG_CACHE_HOME" "$PYTHON_BIN" -m unittest discover -s touchprint_lab/tests -p 'test_*.py'
