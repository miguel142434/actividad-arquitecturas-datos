#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$PROJECT_ROOT/.venv/bin/python}"

require_python() {
  command -v "$PYTHON_BIN" >/dev/null 2>&1 || {
    printf 'Error: prepare .venv with requirements-sources.txt or set PYTHON_BIN.\n' >&2
    exit 1
  }
}

load_env_file() {
  if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # Archivo propio de configuración, nunca la configuración de DE-DW.
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
  fi
}

run_source() {
  local module="$1"
  shift
  PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
    "$PYTHON_BIN" -m "ecommerce_dw.sources.$module" "$@"
}

COMPOSE_FILE="$PROJECT_ROOT/docker/docker-compose.yml"
compose() {
  docker compose --project-directory "$PROJECT_ROOT" --env-file "$PROJECT_ROOT/.env" -f "$COMPOSE_FILE" "$@"
}
require_docker() {
  command -v docker >/dev/null 2>&1 || { printf 'Error: Docker is required.\n' >&2; exit 1; }
  docker compose version >/dev/null 2>&1 || { printf 'Error: Docker Compose v2 is required.\n' >&2; exit 1; }
}
require_env_file() {
  [[ -f "$PROJECT_ROOT/.env" ]] || { printf 'Error: configure .env first.\n' >&2; exit 1; }
}
