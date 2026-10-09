#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo "Environnement Python absent. Consulte studio/README.md pour l’installation."
  exit 1
fi
exec .venv/bin/python -m studio.server
