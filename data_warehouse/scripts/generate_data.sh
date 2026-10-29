#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_python
load_env_file
printf 'Generating source data...\n'
run_source generate_data "$@"
