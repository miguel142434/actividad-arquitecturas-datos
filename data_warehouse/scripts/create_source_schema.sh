#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_python
load_env_file
printf 'Creating source tables and collections in RDS and DocumentDB...\n'
run_source create_source_schema "$@"
