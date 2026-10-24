#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "First run: installing packages, this takes a minute..."
  python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt || { echo "Install failed: need Python 3.10+ and internet."; exit 1; }
fi
exec .venv/bin/python run.py "$@"
