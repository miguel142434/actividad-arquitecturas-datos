#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_python
load_env_file
[[ "$#" -eq 2 && "$1" == "--batch-id" ]] || {
  printf 'Usage: %s --batch-id NUMBER\n' "$0" >&2
  exit 2
}
printf 'Appending daily source batch %s...\n' "$2"
run_source append_batch "$@"
