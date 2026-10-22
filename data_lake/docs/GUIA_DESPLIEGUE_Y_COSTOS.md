# Guía Reproducible de Despliegue, Operación y Estimación de Costos

Esta guía detalla el paso a paso exacto para desplegar toda la infraestructura en AWS con Terraform, ejecutar el pipeline en Apache Airflow, verificar los datos en Athena y finalmente destruir los recursos para no incurrir en costos posteriores.

---

## 1. Despliegue de Infraestructura con Terraform

### 1.1 Configurar variables
1. Ingresa a la carpeta `terraform/`:
   ```bash
   cd terraform
   ```
2. Crea tu archivo de variables locales a partir del ejemplo:
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```
3. Edita `terraform.tfvars`:
   - `aws_region`: `"us-east-1"` (o la región de tu cuenta de laboratorio).
   - `key_name`: Nombre de tu par de llaves EC2 en AWS (ejemplo: `"vockey"` si usas AWS Academy).
   - `allowed_cidr_blocks`: Puedes colocar `["TU_IP_PUBLICA/32"]` para mayor seguridad o `["0.0.0.0/0"]`.

### 1.2 Inicializar y desplegar
Ejecuta los siguientes comandos:
```bash
terraform init
terraform plan
terraform apply -auto-approve
```

Al finalizar, Terraform mostrará en la terminal los **Outputs**:
- `s3_bucket_name`: Nombre del bucket S3 generado.
- `ec2_public_ip`: Dirección IP pública de la instancia EC2.
- `airflow_ui_url`: Enlace directo a la interfaz web de Airflow (`http://<IP>:8080`).
- `glue_database_name`: `rss_datalake_db`.
- `athena_workgroup_name`: Nombre del workgroup para las consultas.

---

## 2. Puesta en Marcha de Apache Airflow en la EC2

### 2.1 Conectarse a la instancia EC2
Usa el comando SSH proporcionado en los outputs de Terraform:
```bash
ssh -i /ruta/a/tu-llave.pem ubuntu@<ec2_public_ip>
```

> **Nota**: El script `user_data` de Terraform instala Docker y Docker Compose automáticamente al arrancar la instancia. Puedes verificar que haya terminado revisando:
> ```bash
> cat /var/log/user_data_status.log
> # Debe decir: Setup completed successfully
> ```

### 2.2 Copiar los archivos de Airflow a la EC2
Desde tu máquina local (en otra terminal), copia la carpeta `airflow/` hacia la EC2:
```bash
scp -i /ruta/a/tu-llave.pem -r airflow/* ubuntu@<ec2_public_ip>:/home/ubuntu/airflow_app/
```

### 2.3 Iniciar los contenedores de Airflow
Dentro de la sesión SSH en la EC2:
```bash
cd /home/ubuntu/airflow_app
# Iniciar los servicios de Airflow en segundo plano
docker compose up -d
```

Verifica que los contenedores estén levantados con:
```bash
docker compose ps
```

---

## 3. Ejecución del Pipeline y Recolección de Evidencias

1. Abre tu navegador e ingresa a `http://<ec2_public_ip>:8080`.
2. Inicia sesión con:
   - **Usuario**: `admin`
   - **Contraseña**: `admin`
3. En la lista de DAGs, busca: `rss_datalake_eltiempo_pipeline`.
4. Activa el toggle (Unpause) y haz clic en el botón **Play (Trigger DAG)** para iniciar una ejecución inmediata.
5. Haz clic en la corrida y observa la vista **Graph** para ver la ejecución secuencial de las 9 tareas:
   - `task_validate_config`
   - `task_extract_to_bronze`
   - `task_process_silver`
   - `task_build_gold`
   - `task_sync_glue`
   - `task_validate_athena`
   - `task_log_final_status`

---

## 4. Demostración de Escenarios Requeridos por la Rúbrica

| Escenario Solicitado | Cómo Demostrarlo y Evidenciarlo |
|---|---|
| **Carga inicial** | Ejecutar el DAG por primera vez. Tomar captura de Airflow en verde, de los archivos en S3 (`bronze/`, `silver/`, `gold/`) y de la primera consulta en Athena con resultados. |
| **Registros defectuosos** | Revisar la carpeta `quarantine/` en S3 y mostrar el archivo JSON con el motivo de rechazo (por ejemplo, artículos con HTML roto o sin título). |
| **Repetición de lote exitoso (Idempotencia)** | Reejecutar el DAG con el mismo ID de lote. Comprobar en Athena que el número total de noticias en `silver_news` y en las métricas de `gold_news_by_day` no se duplican. |
| **Nuevo lote incremental** | Disparar una segunda corrida 30 minutos después. Verificar que solo se añaden los registros nuevos sin sobreescribir los existentes. |
| **Reprocesamiento desde Bronze** | En Airflow, presionar "Trigger DAG w/ config" e ingresar: `{"reprocess_run_id": "<id_lote_anterior>"}`. En los logs de la tarea 2 se evidenciará que lee de S3 sin consultar a `eltiempo.com`. |
| **Comparación de Bytes Escaneados en Athena** | Ejecutar la Consulta A (con `WHERE dt = '...'`) y luego la Consulta B (sin filtro de partición). Tomar captura de la pestaña "Query Details" en Athena mostrando la reducción drástica de datos escaneados. |

---

## 5. Estimación de Costos del Laboratorio en AWS

La siguiente tabla presenta los costos calculados para la ejecución de este laboratorio en la región `us-east-1`:

| Servicio AWS | Recurso y Dimensión | Costo Unitario Estimado | Costo Total del Lab (4 horas de prueba) |
|---|---|---|---|
| **Amazon EC2** | 1x `t3.medium` (2 vCPU, 4 GiB RAM) | \$0.0416 por hora | **~\$0.17 USD** |
| **Amazon EBS** | 30 GB gp3 | \$0.08 por GB-mes | **~\$0.01 USD** |
| **Amazon S3** | < 50 MB de datos (Bronze, Silver, Gold, Athena) | \$0.023 por GB-mes | **<\$0.01 USD** |
| **Amazon Comprehend** | ~100 noticias analizadas (~150 unidades de 100 caracteres) | \$0.0001 por unidad | **~\$0.02 USD** |
| **AWS Glue Data Catalog** | 1 base de datos, 7 tablas (< 1.000 solicitudes) | Gratis (Capa gratuita: primer millón de objetos/solicitudes) | **\$0.00 USD** |
| **Amazon Athena** | ~10 consultas de prueba (< 100 MB escaneados) | \$5.00 por TB escaneado | **<\$0.01 USD** |
| **Total Estimado** | | | **~\$0.21 USD** |

> [!TIP]
> Gracias a la estrategia de **caché de hash** implementada en `process_silver.py`, las noticias repetidas entre corridas no vuelven a enviarse a Amazon Comprehend, protegiendo el presupuesto del laboratorio.

---

## 6. Eliminación Completa de Recursos (Teardown)

Una vez completado el laboratorio y capturadas todas las evidencias requeridas:
1. En tu terminal local, ingresa a la carpeta `terraform/`:
   ```bash
   cd terraform
   terraform destroy -auto-approve
   ```
2. Terraform se encargará de:
   - Vaciar y eliminar el bucket S3 (gracias a `force_destroy = true`).
   - Terminar la instancia EC2 y liberar su IP pública.
   - Destruir el Security Group, el Rol IAM y el Instance Profile.
   - Eliminar el Workgroup de Athena y la base de datos de AWS Glue Catalog.
3. Verifica que la consola de AWS no tenga ningún recurso remanente activo.
