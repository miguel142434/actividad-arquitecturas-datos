#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_python
load_env_file
printf 'Applying repeatable source changes...\n'
run_source simulate_changes "$@"
