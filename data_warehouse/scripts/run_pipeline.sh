#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_docker
require_env_file
existing=false
batch_id=''
kind=initial
source_batch=''
generation_args=()
selection_count=0
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --existing-sources) existing=true; shift ;;
    --batch-id) batch_id="${2:?Falta --batch-id}"; shift 2 ;;
    --source-batch-id) source_batch="${2:?Falta --source-batch-id}"; kind=incremental; selection_count=$((selection_count+1)); shift 2 ;;
    --changes-only) kind=changes; selection_count=$((selection_count+1)); shift ;;
    --reconcile) kind=reconcile; selection_count=$((selection_count+1)); shift ;;
    --) shift; generation_args+=("$@"); break ;;
    *) generation_args+=("$1"); shift ;;
  esac
done
[[ "$batch_id" =~ ^[A-Za-z0-9_-]{1,64}$ && "$selection_count" -le 1 ]] || {
  printf 'Uso: run_pipeline.sh --batch-id ID [--existing-sources] [--source-batch-id N | --changes-only | --reconcile] [argumentos originales del generador]\n' >&2
  exit 2
}
if [[ "$existing" == true && "${#generation_args[@]}" -gt 0 ]] || [[ "$existing" == false && "$kind" != initial ]]; then
  printf 'Usar --existing-sources para lotes/cambios/conciliación, sin argumentos de generación.\n' >&2
  exit 2
fi
if [[ "$kind" == incremental ]]; then
  [[ "$source_batch" =~ ^[0-9]+$ ]] && (( 10#$source_batch >= 1 && 10#$source_batch <= 365 )) || {
    printf 'source-batch-id debe estar entre 1 y 365.\n' >&2; exit 2;
  }
fi
if [[ "$existing" == true ]]; then
  compose up -d
else
  "$PROJECT_ROOT/scripts/start_infrastructure.sh"
fi
runtime=/home/airflow/dbt-venv/bin/python
# Validar/reservar antes de la carga destructiva inicial. Un lote publicado
# debe repetirse con --existing-sources, nunca regenerarse silenciosamente.
if [[ "$existing" == false ]]; then
  compose exec -T airflow-scheduler "$runtime" -c '
import sys
from ecommerce_dw.orchestration.tasks import store_client
store=store_client()
request,published=store.claim(sys.argv[1],None,"initial")
if published: raise SystemExit("El lote ya está publicado; repetir con --existing-sources.")
' "$batch_id"
  compose exec -T airflow-scheduler "$runtime" -m ecommerce_dw.sources.create_source_schema
  compose exec -T airflow-scheduler "$runtime" -m ecommerce_dw.sources.generate_data "${generation_args[@]}"
fi
ready=false
for _ in {1..60}; do
  if compose exec -T airflow-scheduler python -c 'from airflow.models.dag import DagModel; from airflow.settings import Session; s=Session(); ready=s.query(DagModel).filter(DagModel.dag_id.in_(["ecommerce_pipeline","extract_to_raw","transform_warehouse"])).count()==3; s.close(); raise SystemExit(0 if ready else 1)' >/dev/null 2>&1; then
    ready=true; break
  fi
  sleep 2
done
[[ "$ready" == true ]] || { printf 'Los tres DAGs no están registrados; revisar scheduler.\n' >&2; exit 1; }
compose exec -T airflow-scheduler airflow dags unpause --yes --treat-dag-id-as-regex '^(ecommerce_pipeline|extract_to_raw|transform_warehouse)$' >/dev/null
conf="$(python3 - "$batch_id" "$kind" "$source_batch" <<'PY'
import json,sys
value={'batch_id':sys.argv[1],'kind':sys.argv[2],'source_batch_id':int(sys.argv[3]) if sys.argv[3] else None}
print(json.dumps(value))
PY
)"
execution_date="$(date -u +'%Y-%m-%dT%H:%M:%S+00:00')"
compose exec -T airflow-scheduler airflow dags trigger --exec-date "$execution_date" --conf "$conf" ecommerce_pipeline >/dev/null
# Airflow 2.11 agrega ", {conf}" después del estado si existe dag_run.conf.
for _ in {1..360}; do
  state="$(compose exec -T airflow-scheduler airflow dags state ecommerce_pipeline "$execution_date" 2>/dev/null | tail -n 1 | cut -d ',' -f 1 | tr -d '\r')"
  case "$state" in
    success) printf 'batch_id=%s: ecommerce_pipeline completado.\n' "$batch_id"; exit 0 ;;
    failed) printf 'batch_id=%s: fallo; revisar logs de tarea y conservar archivos/marcas.\n' "$batch_id" >&2; exit 1 ;;
  esac
  sleep 5
done
printf 'batch_id=%s: no terminó dentro de 30 minutos; no se canceló ni confirmó automáticamente.\n' "$batch_id" >&2
exit 1
