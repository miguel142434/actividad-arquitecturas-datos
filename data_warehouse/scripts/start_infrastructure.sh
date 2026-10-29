#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_docker
require_env_file
# Arranca solo Airflow/PostgreSQL locales en EC2; nunca ejecuta Terraform ni fuentes.
compose config --quiet
compose up --build -d
compose ps
