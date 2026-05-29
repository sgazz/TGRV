#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON="$(command -v python)"
else
  echo "Python 3 is not available on this Mac."
  exit 1
fi

if [ ! -f "touchprint_lab/main.py" ]; then
  echo "Cannot find touchprint_lab/main.py in: $SCRIPT_DIR"
  exit 1
fi

echo "Starting Touchprint Analyzer from: $SCRIPT_DIR"
echo "Using Python: $PYTHON"
exec "$PYTHON" -m touchprint_lab.main
