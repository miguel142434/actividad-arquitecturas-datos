# Data Warehouse en AWS

Warehouse de comercio electrónico en AWS: RDS MySQL y DocumentDB → S3 → Redshift Serverless → QuickSight con SPICE. Airflow, los scripts Python y dbt se ejecutan en una misma EC2; las transformaciones SQL se ejecutan en Redshift. Se conservan los generadores, defectos deliberados, reglas de negocio, modelo dimensional y snapshots SCD tipo 2 de la versión local.

Esta guía permite desplegar un entorno nuevo, procesar datos y eliminarlo. Todos los comandos parten de un clon propio; no requieren endpoints, recursos ni archivos de ejecuciones anteriores. Los recursos de la demostración original fueron retirados.

## 1. Requisitos y clonación

En el equipo local se necesitan Git, Python 3.11 o posterior, AWS CLI v2, Terraform >= 1.11 y < 2, OpenSSH y `tar`. Docker se instala en EC2 mediante el bootstrap. El proveedor AWS está fijado en Terraform y sus dependencias se resuelven con `terraform init`.

Se usa exclusivamente `us-east-1` y el perfil `default`. Configura ese perfil con tu mecanismo habitual de autenticación AWS; no guardes claves AWS en el repositorio ni en el `.env` de EC2. La identidad debe poder administrar los servicios del laboratorio y los roles definidos por Terraform, incluido `iam:PassRole`; QuickSight requiere además permisos de administración de sus activos y una identidad administradora dentro del servicio. Si una operación devuelve `AccessDenied`, revisa la acción concreta con el administrador antes de modificar permisos.

Sustituye la URL por la del repositorio publicado. La solución está en `data_warehouse/`, dentro de `actividad-arquitecturas-datos`.

```bash
git clone https://github.com/USUARIO/REPOSITORIO.git
cd REPOSITORIO/data_warehouse

aws --version
terraform version
python3 --version
aws sts get-caller-identity --profile default --region us-east-1

python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-ingestion.txt
```

Usa la clave pública `~/.ssh/id_ed25519.pub`. Si todavía no existe ese par, créalo; no sobrescribas una clave existente.

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

El laboratorio permite SSH TCP 22 desde cualquier IPv4 (`0.0.0.0/0`), exclusivamente como `ec2-user` mediante clave. Root, contraseñas y autenticación interactiva quedan deshabilitados. Las bases permanecen privadas; el puerto de Airflow solo escucha en loopback.

Antes de crear recursos, revisa las tarifas vigentes de EC2/EBS/IPv4, RDS, DocumentDB, Redshift Serverless, S3 y QuickSight para el tiempo previsto de uso. No se presupone free tier. Los USD 50 son una referencia de presupuesto, no un límite automático. Los límites de Redshift no cubren el costo de los demás servicios. La suscripción QuickSight se activa más adelante y se cancela por separado.

## 2. Preparar y desplegar la infraestructura base — equipo local

Terraform prepara la VPC, subredes, grupos de seguridad, endpoint S3, bucket privado, EC2, RDS MySQL, DocumentDB y Redshift Serverless. Inicialmente QuickSight está desactivado. Las bases usan cifrado y conexiones TLS; RDS y DocumentDB solo reciben tráfico desde EC2.

Comprueba que las versiones y clases configuradas siguen disponibles antes de desplegar. Las consultas siguientes son de solo lectura; una respuesta vacía requiere revisar la configuración antes de continuar.

```bash
aws rds describe-orderable-db-instance-options \
  --engine mysql --engine-version 8.4.11 --db-instance-class db.t4g.micro \
  --profile default --region us-east-1 \
  --query 'OrderableDBInstanceOptions[].{Version:EngineVersion,Class:DBInstanceClass}'

aws docdb describe-orderable-db-instance-options \
  --engine docdb --engine-version 5.0.0 --db-instance-class db.t3.medium \
  --profile default --region us-east-1 \
  --query 'OrderableDBInstanceOptions[].{Version:EngineVersion,Class:DBInstanceClass}'

python3 scripts/prepare_terraform_rds.py
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform validate
python3 scripts/terraform_rds.py plan -out=deployment.tfplan
terraform -chdir=infra/terraform show -no-color deployment.tfplan
```

La preparación obtiene tu cuenta mediante STS y crea las variables locales con la clave SSH. Si ese archivo ya existe, revísalo; el script no lo sobrescribe. No mantengas simultáneamente dos archivos de variables con los mismos valores.

El wrapper `terraform_rds.py` solicita sin eco las tres contraseñas: RDS, DocumentDB y Redshift. Guarda cada una en tu gestor de contraseñas y utiliza los mismos valores en plan, apply, configuración y retirada. Deben tener entre 16 y 64 caracteres de `A-Z`, `a-z`, `0-9`, `_` o `-`; la de Redshift debe incluir mayúscula, minúscula y número. Se transmiten como variables efímeras y atributos de escritura del proveedor; no se escriben en código, planes ni estado.

Revisa cuenta, región, costos, accesos y operaciones del plan. Para un entorno nuevo debe crear recursos, sin eliminar recursos ajenos. El siguiente comando sí crea infraestructura y empieza a generar costos:

```bash
python3 scripts/terraform_rds.py apply deployment.tfplan
terraform -chdir=infra/terraform output
rm infra/terraform/deployment.tfplan

DW_SSH_TARGET="$(terraform -chdir=infra/terraform output -raw ssh_target)"
DW_RUNNER_ID="$(terraform -chdir=infra/terraform output -raw runner_instance_id)"
DW_ACCOUNT="$(aws sts get-caller-identity --profile default --region us-east-1 --query Account --output text)"
```

Conserva el estado Terraform en el equipo que administra el despliegue, protegido y fuera de Git. Es necesario para retirar correctamente los recursos. No reutilices planes antiguos después de cambiar la configuración o la infraestructura.

## 3. Verificar EC2 y transferir código — equipo local

Obtén la huella SSH publicada por el bootstrap y compárala con la que presenta el primer acceso. Si todavía no aparece, espera a que termine el arranque y consulta de nuevo.

```bash
aws ec2 get-console-output --instance-id "$DW_RUNNER_ID" --latest \
  --profile default --region us-east-1 --query Output --output text \
  | sed -n '/BEGIN SSH HOST KEY FINGERPRINTS/,/END SSH HOST KEY FINGERPRINTS/p'

ssh -i ~/.ssh/id_ed25519 "$DW_SSH_TARGET"
```

En la sesión EC2:

```bash
cloud-init status --wait
python3.11 --version
docker compose version
docker info --format '{{.ServerVersion}}'
test -s /opt/de-dw-aws/certs/global-bundle.pem && echo 'CA disponible'
sudo /usr/sbin/sshd -T \
  | grep -E '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication|allowusers|authenticationmethods) '
```

Se espera bootstrap terminado, Docker accesible y SSH con `permitrootlogin no`, `passwordauthentication no`, `kbdinteractiveauthentication no`, `allowusers ec2-user` y `authenticationmethods publickey`.

Desde otra terminal del equipo local, en la raíz del proyecto, empaqueta únicamente el código necesario:

```bash
tar --exclude='__pycache__' --exclude='*.pyc' --exclude='target' \
  --exclude='dbt_packages' --exclude='logs' \
  -czf /tmp/de-dw-aws-code.tar.gz \
  src scripts docker requirements-sources.txt requirements-ingestion.txt \
  requirements-warehouse.txt .env.example .dockerignore

scp -i ~/.ssh/id_ed25519 /tmp/de-dw-aws-code.tar.gz "$DW_SSH_TARGET:/tmp/"
rm /tmp/de-dw-aws-code.tar.gz
```

No se transfieren `.env`, credenciales AWS, estado Terraform, dependencias instaladas ni datos locales. En EC2:

```bash
cd /opt/de-dw-aws
tar -xzf /tmp/de-dw-aws-code.tar.gz
rm /tmp/de-dw-aws-code.tar.gz
bash scripts/install_docker_buildx.sh
bash scripts/configure_environment.sh
vi .env
chmod 600 .env
```

El instalador de Buildx verifica su descarga; es necesario para construir con la versión de Compose instalada. La configuración crea el `.env` y genera únicamente los secretos locales vacíos de Airflow/PostgreSQL, conservando los valores existentes.

## 4. Configurar conexiones y arrancar Airflow — EC2

Completa el `.env` privado usando los outputs de tu despliegue:

| Variable | Valor |
| --- | --- |
| `MYSQL_HOST` | Output `rds_endpoint`, sin puerto |
| `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER` | `3306`, `ecommerce`, `dwadmin` |
| `MYSQL_PASSWORD` | Contraseña de RDS introducida en Terraform |
| `MYSQL_SSL_CA` | `/opt/de-dw-aws/certs/global-bundle.pem` |
| `MONGO_DATABASE` | `ecommerce` |
| `MONGODB_URI` | `mongodb://dwadmin:CONTRASENA_URL_ENCODED@ENDPOINT_CLUSTER:27017/?authSource=admin`, entre comillas simples |
| `MONGO_TLS_CA_FILE` | `/opt/de-dw-aws/certs/global-bundle.pem` |
| `S3_RAW_BUCKET` | Output `raw_bucket` |
| `REDSHIFT_HOST` | Output `redshift_host`, sin esquema ni puerto |
| `REDSHIFT_DATABASE`, `REDSHIFT_USER` | `ecommerce`, `dwadmin` |
| `DBT_ENV_SECRET_REDSHIFT_PASSWORD` | Contraseña de Redshift introducida en Terraform |
| `REDSHIFT_COPY_ROLE_ARN` | Output `redshift_copy_role_arn` |
| `QUICKSIGHT_ACCOUNT_ID`, `QUICKSIGHT_DATASET_ID` | Vacías hasta completar la configuración de QuickSight |

En la URI usa la contraseña de DocumentDB codificada para URL y el endpoint del clúster. El conector Python establece TLS obligatorio, CA, `replicaSet=rs0` y `retryWrites=false`. No desactives la validación de certificados. Compose adapta las rutas de CA al interior del contenedor y configura el ejecutable dbt; conserva los valores generados de Airflow.

Define esta función en la terminal EC2. Si abres otra sesión, vuelve a entrar en `/opt/de-dw-aws` y a definirla:

```bash
compose() {
  docker compose --project-directory . --env-file .env \
    -f docker/docker-compose.yml "$@"
}

compose config --quiet
compose build airflow-scheduler
compose up -d
compose ps -a
compose exec -T airflow-scheduler airflow jobs check --job-type SchedulerJob --local
compose exec -T airflow-scheduler airflow dags list-import-errors
compose exec -T airflow-scheduler airflow dags list
```

Se espera PostgreSQL saludable, `airflow-init` terminado con código 0, scheduler vivo y tres DAGs importados: `ecommerce_pipeline`, `extract_to_raw` y `transform_warehouse`. La lista de errores de importación debe estar vacía. Si el scheduler acaba de iniciar, repite su comprobación cuando termine de arrancar.

Comprueba las cuatro conexiones sin generar datos:

```bash
compose exec -T airflow-scheduler /home/airflow/dbt-venv/bin/python - <<'PY'
from contextlib import closing
from ecommerce_dw.sources.mysql_connection import connect_mysql
from ecommerce_dw.sources.documentdb_connection import connect_documentdb
from ecommerce_dw.warehouse.connection import connect_redshift
from ecommerce_dw.orchestration.tasks import store_client

for name, factory in [('RDS MySQL', connect_mysql), ('Redshift', connect_redshift)]:
    with closing(factory()) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            assert cursor.fetchone()[0] == 1
    print(name + ': OK')
with closing(connect_documentdb()) as client:
    assert client.admin.command('ping')['ok'] == 1
print('DocumentDB: OK')
store = store_client()
store.client.head_bucket(Bucket=store.bucket)
print('S3 mediante rol EC2: OK')
PY
```

Para abrir Airflow, ejecuta en una terminal local separada y mantenla abierta:

```bash
ssh -N -i ~/.ssh/id_ed25519 -L 8080:127.0.0.1:8080 "$DW_SSH_TARGET"
```

Visita `http://localhost:8080` e inicia sesión con el usuario y contraseña de administración de tu `.env`. No publiques el puerto 8080 ni muestres ese archivo en capturas.

## 5. Ejecutar la carga inicial — EC2

Ejecuta este comando una sola vez sobre un entorno nuevo:

```bash
bash scripts/run_pipeline.sh --batch-id inicial_001 -- --seed 42
```

Crea el esquema de fuentes y llama al generador original: primero MySQL y después DocumentDB. El generador inicial **borra los datos previos de ambas fuentes**; no sirve para agregar un lote incremental. Conserva sus argumentos, validadores y defectos deliberados para cuarentena.

El wrapper dispara el DAG maestro y espera su resultado. Airflow valida parámetros y conexiones, extrae las fuentes, publica CSV y manifiesto en S3, ejecuta COPY a Redshift y llama a dbt: semillas, intermediate, quarantine, snapshots, marts y pruebas. Al superar calidad confirma el lote. QuickSight se omite mientras sus variables estén vacías.

Los objetos se organizan como `raw/<fuente>/<entidad>/batch_id=<id>/`. El manifiesto identifica fecha, archivos y conteos. S3 conserva lo necesario para reprocesar sin consultar las fuentes. Las capas raw, intermediate, quarantine y marts son esquemas de Redshift; no carpetas adicionales obligatorias del bucket.

Comprueba resultado y marcas:

```bash
compose exec -T airflow-scheduler /home/airflow/dbt-venv/bin/python - <<'PY'
from contextlib import closing
from ecommerce_dw.orchestration.tasks import store_client
from ecommerce_dw.warehouse.connection import connect_redshift

state, _ = store_client().state()
print('S3:', state)
with closing(connect_redshift()) as connection:
    with connection.cursor() as cursor:
        cursor.execute('SELECT batch_id, status, loaded_at, validated_at FROM control.batches ORDER BY sequence_no')
        for row in cursor.fetchall():
            print(row)
        cursor.execute('SELECT COUNT(*), COALESCE(SUM(subtotal), 0) FROM marts.fct_sales')
        print('Ventas y total:', cursor.fetchone())
PY
```

Se espera el DAG maestro y sus hijos en `success`, las pruebas dbt aprobadas, SQL `VALIDATED`, `accepted=inicial_001` y `pending=null`. `LOADED` solo confirma raw: las marcas de aceptación avanzan después de calidad. La cantidad exacta de filas se verifica contra la ejecución actual, no contra una salida histórica.

## 6. Crear el dashboard QuickSight con SPICE

### Alta y conexión privada — equipo local

Entra en la consola QuickSight/Amazon Quick de `us-east-1` y crea o utiliza una suscripción Enterprise compatible con conexiones VPC. Usa tu correo, un único administrador y cifrado administrado por AWS. Revisa el rol y las condiciones económicas que muestra el alta: una prueba gratuita puede vencer o no estar disponible; no presupongas que el servicio seguirá siendo gratuito ni actives planes adicionales para este laboratorio.

Comprueba la cuenta y sus usuarios antes de continuar:

```bash
DW_ACCOUNT="$(aws sts get-caller-identity --profile default --region us-east-1 --query Account --output text)"
DW_OWNER_ARN="$(aws sts get-caller-identity --profile default --region us-east-1 --query Arn --output text)"

aws quicksight describe-account-subscription --aws-account-id "$DW_ACCOUNT" \
  --profile default --region us-east-1
aws quicksight list-users --aws-account-id "$DW_ACCOUNT" --namespace default \
  --profile default --region us-east-1 \
  --query 'UserList[].{User:UserName,Role:Role}'
```

Espera a `ACCOUNT_CREATED`. El script reutiliza el usuario que coincide con la identidad IAM o el único administrador existente; no crea asientos adicionales. Si no puede identificar al administrador, resuelve esa identidad en QuickSight antes de ejecutarlo.

Habilita la infraestructura de consumo:

```bash
python3 - <<'PY'
import json
from pathlib import Path
path = Path('infra/terraform/terraform.tfvars.json')
values = json.loads(path.read_text())
values['enable_quicksight'] = True
path.write_text(json.dumps(values, indent=2) + '\n')
path.chmod(0o600)
PY

python3 scripts/terraform_rds.py plan -out=quicksight.tfplan
terraform -chdir=infra/terraform show -no-color quicksight.tfplan
python3 scripts/terraform_rds.py apply quicksight.tfplan
rm infra/terraform/quicksight.tfplan

DW_SSH_TARGET="$(terraform -chdir=infra/terraform output -raw ssh_target)"
DW_REDSHIFT_HOST="$(terraform -chdir=infra/terraform output -raw redshift_host)"
DW_VPC_ARN="$(terraform -chdir=infra/terraform output -raw quicksight_vpc_connection_arn)"

.venv/bin/python scripts/setup_quicksight.py \
  --account-id "$DW_ACCOUNT" \
  --notification-email 'TU_CORREO' \
  --owner-iam-arn "$DW_OWNER_ARN" \
  --ssh-target "$DW_SSH_TARGET" \
  --redshift-host "$DW_REDSHIFT_HOST" \
  --vpc-arn "$DW_VPC_ARN"
```

Revisa el segundo plan antes de aplicarlo: debe incorporar la conexión VPC, reglas de red y permisos de consumo previstos, sin reemplazar las bases. El script prepara un lector SQL limitado a cuatro tablas de marts, transmite su contraseña por SSH sin persistirla localmente y crea datasource, dataset SPICE, análisis y dashboard. Muestra la URL privada al finalizar. El dashboard incluye ventas totales, ventas mensuales y filtro de categoría.

### Activar la actualización después de cada lote — EC2

Edita privadamente el `.env` y completa `QUICKSIGHT_ACCOUNT_ID` con tu cuenta y `QUICKSIGHT_DATASET_ID=de-dw-aws-sales`. Hazlo después de crear el lector y los activos: dbt también utiliza esta configuración para conservar los permisos del lector al reconstruir tablas.

```bash
vi .env
compose up -d --no-build airflow-scheduler airflow-webserver
compose exec -T airflow-scheduler /home/airflow/dbt-venv/bin/python \
  -m ecommerce_dw.consumption.refresh --batch-id inicial_001
```

Tras cada nuevo lote validado, la última tarea del maestro, `refresh_spice`, solicita un `FULL_REFRESH` del dataset. La extracción y el warehouse siguen siendo incrementales; SPICE vuelve a importar el conjunto analítico pequeño. Se espera `COMPLETED`, filas ingeridas iguales a SQL y cero descartes. El recibo se guarda en `control/consumption/<dataset>/<batch_id>.json` en S3.

## 7. Procesar novedades, repetir y recuperar — EC2

Para generar el primer lote adicional en ambas fuentes y procesarlo hasta el dashboard:

```bash
compose exec -T airflow-scheduler /home/airflow/dbt-venv/bin/python \
  -m ecommerce_dw.sources.append_batch --batch-id 1
bash scripts/run_pipeline.sh --batch-id incremental_001 \
  --existing-sources --source-batch-id 1
```

En el siguiente lote usa `--batch-id 2` en el generador, `--source-batch-id 2` y un identificador de extracción nuevo, por ejemplo `incremental_002`. El número del generador identifica las novedades de origen; el `batch_id` textual identifica de forma estable la extracción y su procesamiento. No ejecutes escritores de fuentes durante una extracción.

Para repetir un lote ya publicado, conserva su identificador y selección. No vuelvas a generar datos:

```bash
bash scripts/run_pipeline.sh --batch-id inicial_001 --existing-sources
bash scripts/run_pipeline.sh --batch-id incremental_001 \
  --existing-sources --source-batch-id 1
```

La repetición reutiliza los archivos de S3 y reconoce el control de procesamiento para evitar duplicar hechos o versiones históricas. Un lote antiguo no sustituye el corte más reciente de SPICE.

Para demostrar un cambio historizado con el simulador original:

```bash
compose exec -T airflow-scheduler /home/airflow/dbt-venv/bin/python \
  -m ecommerce_dw.sources.simulate_changes
bash scripts/run_pipeline.sh --batch-id cambios_001 --existing-sources --changes-only
```

Comprueba el cierre de la versión anterior, la nueva versión SCD2 y una única versión vigente por clave en los snapshots de clientes y productos. Para una conciliación completa, por ejemplo tras eliminaciones deliberadas en las fuentes, existe `--reconcile`; no interpretes la ausencia de una fila en un delta como eliminación:

```bash
bash scripts/run_pipeline.sh --batch-id conciliacion_001 --existing-sources --reconcile
```

Si una tarea falla, revisa en Airflow el lote, la tarea y su log, corrige la causa y reejecuta el mismo lote con `--existing-sources` y los mismos selectores. Conserva el manifiesto y los archivos publicados; no borres las marcas para forzar una carga ni inicies otro lote mientras exista uno pendiente. Un timeout del wrapper solo termina la espera de la terminal: revisa Airflow antes de lanzar otro intento.

Si falla únicamente SPICE, el warehouse ya validado se conserva. Reintenta solo consumo, sustituyendo el identificador por el último lote aceptado:

```bash
compose exec -T airflow-scheduler /home/airflow/dbt-venv/bin/python \
  -m ecommerce_dw.consumption.refresh --batch-id cambios_001
```

El refresco reutiliza ingestiones en curso o completadas y permite hasta tres intentos por lote. Si no hay un recibo exitoso, no declares actualizado el dashboard aunque las transformaciones hayan terminado.

## 8. Validar el indicador del dashboard — EC2

Ejecuta el SQL con el mismo filtro del dashboard y después del refresco confirmado. `None` representa todas las categorías; para una categoría cambia la variable por su texto exacto.

```bash
compose exec -T airflow-scheduler /home/airflow/dbt-venv/bin/python - <<'PY'
from contextlib import closing
from ecommerce_dw.consumption.assets import VALIDATION_SQL
from ecommerce_dw.warehouse.connection import connect_redshift

categoria = None
with closing(connect_redshift()) as connection:
    with connection.cursor() as cursor:
        cursor.execute(VALIDATION_SQL, (categoria, categoria))
        filas, total = cursor.fetchone()
        print({'categoria': categoria, 'filas': filas, 'ventas_totales_COP': str(total)})
PY
```

Contrasta el total con el KPI visible en QuickSight y conserva ambos resultados con el mismo corte y filtro. La consulta de ingestión comprueba filas y estado, pero no devuelve la suma de SPICE. El éxito del pipeline, las pruebas dbt, los rechazos, las comparaciones de lotes y las versiones SCD2 se comprueban por separado; una conexión exitosa no demuestra estos resultados.

## 9. Eliminar los recursos

La retirada elimina los datos sintéticos. Primero descarga a tu equipo cualquier resultado o captura que quieras conservar. Mantén el estado Terraform y los permisos de administración hasta finalizar. Detener Docker o EC2 no elimina las bases, el almacenamiento ni la suscripción QuickSight.

### Detener ejecuciones — EC2

Cuando no haya ejecuciones activas:

```bash
cd /opt/de-dw-aws
bash scripts/stop_infrastructure.sh
```

### Eliminar los activos QuickSight — equipo local

Si no habilitaste QuickSight, omite este bloque. Mantén la suscripción activa hasta que Terraform elimine la conexión VPC. Los comandos afectan únicamente a los identificadores del laboratorio; no deben reutilizarse en una cuenta donde esos identificadores pertenezcan a otro proyecto.

```bash
DW_ACCOUNT="$(aws sts get-caller-identity --profile default --region us-east-1 --query Account --output text)"

aws quicksight delete-dashboard --aws-account-id "$DW_ACCOUNT" \
  --dashboard-id de-dw-aws-sales --profile default --region us-east-1
aws quicksight delete-analysis --aws-account-id "$DW_ACCOUNT" \
  --analysis-id de-dw-aws-sales --force-delete-without-recovery \
  --profile default --region us-east-1
aws quicksight delete-data-set --aws-account-id "$DW_ACCOUNT" \
  --data-set-id de-dw-aws-sales --profile default --region us-east-1
aws quicksight delete-data-source --aws-account-id "$DW_ACCOUNT" \
  --data-source-id de-dw-aws-redshift --profile default --region us-east-1
```

`ResourceNotFoundException` indica que ese activo ya no existe. Un error de permisos no confirma su eliminación.

### Vaciar el bucket y destruir la infraestructura — equipo local

El bucket usa `force_destroy=false`, por lo que debes vaciarlo explícitamente. Obtén su nombre del estado antes de destruirlo. Este bloque elimina objetos, versiones, marcadores de borrado y cargas multipart incompletas del bucket del laboratorio:

```bash
export DW_BUCKET="$(terraform -chdir=infra/terraform output -raw raw_bucket)"
.venv/bin/python - <<'PY'
import os
import boto3

client = boto3.Session(profile_name='default', region_name='us-east-1').client('s3')
bucket = os.environ['DW_BUCKET']
for page in client.get_paginator('list_object_versions').paginate(Bucket=bucket):
    objects = [
        {'Key': entry['Key'], 'VersionId': entry['VersionId']}
        for group in ('Versions', 'DeleteMarkers') for entry in page.get(group, [])
    ]
    for offset in range(0, len(objects), 1000):
        result = client.delete_objects(Bucket=bucket, Delete={'Objects': objects[offset:offset + 1000]})
        if result.get('Errors'):
            raise RuntimeError('No se pudieron eliminar todos los objetos; revisar permisos.')
for page in client.get_paginator('list_multipart_uploads').paginate(Bucket=bucket):
    for upload in page.get('Uploads', []):
        client.abort_multipart_upload(Bucket=bucket, Key=upload['Key'], UploadId=upload['UploadId'])
print('Bucket vaciado:', bucket)
PY

python3 scripts/terraform_rds.py plan -destroy -out=destroy.tfplan
terraform -chdir=infra/terraform show -no-color destroy.tfplan
python3 scripts/terraform_rds.py apply destroy.tfplan
rm infra/terraform/destroy.tfplan
terraform -chdir=infra/terraform state list
```

Revisa el plan antes de aplicar la eliminación. Conserva `enable_quicksight=true` si se desplegó esa parte: Terraform necesita gestionar también sus recursos. DocumentDB puede tardar varios minutos en retirarse; espera el resultado final. Si falla, corrige la causa y prepara un plan nuevo sobre el mismo estado. No borres el estado ni uses `state rm` como sustituto de eliminar recursos.

La configuración del laboratorio omite snapshots finales y elimina respaldos automáticos de RDS al retirar la instancia. Los snapshots, respaldos, discos u otros recursos creados manualmente pueden quedar fuera de Terraform. Comprueba en `us-east-1`: EC2 y volúmenes/EIP/ENI, RDS y DocumentDB con sus snapshots y respaldos, Redshift Serverless y snapshots, S3 y la red del proyecto. El estado sin recursos administrados no acredita por sí solo la ausencia de recursos manuales.

### Cancelar la suscripción QuickSight y revisar cargos

Después de retirar los activos y la conexión VPC, entra con el administrador de QuickSight en **Manage account → Account settings → Unsubscribe / Delete account**. Si está habilitada la protección de terminación, desactívala y confirma la cuenta que quieres cancelar. Esta acción cancela la cuenta del servicio QuickSight, no la cuenta AWS. Si la suscripción se comparte con otros proyectos, conserva esos usos y revisa sus cargos en lugar de cancelar toda la cuenta.

La consola debe confirmar la baja. La API puede mostrar temporalmente `UNSUBSCRIBE_IN_PROGRESS` durante el cierre:

```bash
aws quicksight describe-account-subscription --aws-account-id "$DW_ACCOUNT" \
  --profile default --region us-east-1 \
  --query 'AccountInfo.AccountSubscriptionStatus'
```

La cancelación evita uso futuro, pero no elimina importes ya devengados. Revisa **Billing and Cost Management → Bills** y el desglose por servicio; la información de facturación puede actualizarse con retraso.

El alta en consola también puede crear roles y políticas de servicio fuera de Terraform. En IAM revisa `aws-quicksight-service-role-v0` y sus políticas asociadas: retira únicamente los recursos creados para este laboratorio y sin otros usuarios o servicios dependientes. No elimines políticas administradas por AWS ni identidades o permisos preexistentes de tu cuenta.

Conserva el código y los resultados locales necesarios. No subas a Git `.env`, variables privadas, claves SSH, planes ni estados Terraform.
