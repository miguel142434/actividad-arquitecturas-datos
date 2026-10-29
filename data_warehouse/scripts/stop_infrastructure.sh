#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_docker
require_env_file
compose stop
# No elimina volúmenes ni recursos AWS; no equivale a detener la facturación AWS.
