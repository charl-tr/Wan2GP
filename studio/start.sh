#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo "Environnement Python absent. Consulte studio/README.md pour l’installation."
  exit 1
fi
if .venv/bin/python - <<'CHECK'
import json, sys, urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:7861/api/health', timeout=1) as response:
        healthy = json.load(response).get('ok') is True
    sys.exit(0 if healthy else 1)
except Exception:
    sys.exit(1)
CHECK
then
  echo "AFTER tourne déjà : http://127.0.0.1:7861"
  exit 0
fi
echo "AFTER : http://127.0.0.1:7861 — garde ce terminal ouvert."
exec .venv/bin/python -m studio.server
