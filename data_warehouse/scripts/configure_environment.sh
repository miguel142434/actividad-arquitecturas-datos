#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
ENV_TEMPLATE="$PROJECT_ROOT/.env.example"

[[ -f "$ENV_TEMPLATE" ]] || {
  printf 'Error: environment template is missing: %s\n' "$ENV_TEMPLATE" >&2
  exit 1
}

if [[ -e "$ENV_FILE" ]]; then
  printf 'Environment file already exists; keeping current values.\n'
else
  cp "$ENV_TEMPLATE" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  printf 'Created .env from .env.example. Set RDS and DocumentDB connection values.\n'
fi

python3 "$PROJECT_ROOT/scripts/prepare_airflow_environment.py"
