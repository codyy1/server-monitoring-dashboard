#!/usr/bin/env bash
# Starts the WSL2 Server Monitoring Web Application in Ubuntu-22.04
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
fi

echo "Starting WSL2 Server Monitoring Dashboard on http://localhost:8080 ..."
exec python3 "$PROJECT_DIR/backend/app.py"
