# Arquitecturas de Datos - Ingenieria de Datos

Repositorio correspondiente a la implementacion practica de arquitecturas analiticas empresariales en Amazon Web Services (AWS) para el curso de Ingenieria de Datos (Universidad EIA):
- **Modulo 1: Data Lake Medallon** (Ingesta y procesamiento NLP de fuentes no estructuradas/semiestructuradas).
- **Modulo 2: Data Warehouse Empresarial** (Modelado dimensional, transformaciones con dbt y reporteria BI sobre fuentes hibridas transaccionales y NoSQL).

Autores:
- Martin Restrepo Coral
- Miguel Angel Zuleta

Repositorio: https://github.com/miguel142434/actividad-arquitecturas-datos.git

---

## Estructura del Repositorio

```text
actividad_arquitecturas/
|-- data_lake/                              # Modulo 1: Data Lake Medallon (AWS S3 + Airflow + Comprehend + Athena)
|   |-- airflow/                           # Orquestacion y scripts de ingesta/transformacion
|   |   |-- dags/                          # DAG principal (rss_datalake_pipeline.py)
|   |   |-- scripts/                       # Modulos de procesamiento (Bronze, Silver, Gold, Glue)
|   |   |-- docker-compose.yaml            # Despliegue de Airflow (LocalExecutor + PostgreSQL)
|   |   |-- Dockerfile                     # Imagen personalizada con librerias Python
|   |   |-- requirements.txt               # Dependencias Python (boto3, pandas, pyarrow)
|   |   `-- .env.example                   # Plantilla de variables de entorno
|   |-- terraform/                         # Infraestructura como Codigo (IaC) de Data Lake
|   |   |-- main.tf                        # Proveedores AWS
|   |   |-- s3.tf                          # Bucket S3 unico para capas Medallon
|   |   |-- iam.tf                         # Roles y politicas IAM para EC2
|   |   |-- glue.tf                        # Base de datos Glue Catalog y Athena Workgroup
|   |   |-- ec2.tf                         # Instancia EC2 para orquestador
|   |   |-- variables.tf                   # Definicion de variables
|   |   |-- outputs.tf                     # Valores de salida del despliegue
|   |   `-- terraform.tfvars.example       # Plantilla de configuracion
|   `-- docs/                              # Documentacion tecnica del Data Lake
|       |-- ARQUITECTURA.md                # Diseno de capas y flujo de datos
|       |-- DICCIONARIO_DATOS.md           # Esquemas formales de Bronze, Silver y Gold
|       |-- REGLAS_Y_ESTRATEGIAS.md        # Calidad, deduplicacion, cache y SCD-1
|       `-- GUIA_DESPLIEGUE_Y_COSTOS.md    # Procedimientos y estimacion de costos
|
|-- data_warehouse/                         # Modulo 2: Data Warehouse (RDS + DocumentDB + Redshift + dbt + QuickSight)
|   |-- docker/                            # Entornos de ejecucion y contenedores
|   |   |-- Dockerfile                     # Imagen para ejecucion de tareas
|   |   `-- docker-compose.yml             # Servicios auxiliares locales
|   |-- docs/                              # Diagramas tecnicos y especificaciones
|   |   `-- diagramas/                     # Diagramas de arquitectura AWS (SVG/DOT)
|   |-- infra/
|   |   `-- terraform/                     # IaC del Data Warehouse (VPC, RDS, DocDB, Redshift, QuickSight)
|   |       |-- compute.tf                 # Instancia EC2 runner
|   |       |-- documentdb.tf              # Cluster Amazon DocumentDB
|   |       |-- network.tf                 # VPC, subredes publicas/privadas y Security Groups
|   |       |-- outputs.tf                 # Endpoints y referencias de infraestructura
|   |       |-- quicksight.tf              # Recursos de QuickSight y VPC Connection
|   |       |-- rds.tf                     # Instancia Amazon RDS MySQL
|   |       |-- redshift.tf                # Redshift Serverless (Namespace y Workgroup)
|   |       |-- s3.tf                      # Bucket privado para staging de datos crudos
|   |       |-- variables.tf               # Parametros de configuracion
|   |       |-- versions.tf                # Versiones de Terraform y proveedores
|   |       `-- templates/bootstrap.sh     # Inicializacion automatica del runner
|   |-- scripts/                           # Automatizaciones y validaciones operativas
|   |   |-- common.sh                      # Funciones comunes de shell
|   |   |-- configure_environment.sh       # Configuracion del entorno en EC2
|   |   |-- prepare_terraform_rds.py       # Preparacion de variables de despliegue
|   |   |-- run_pipeline.sh                # Ejecucion del pipeline completo
|   |   |-- setup_quicksight.py            # Creacion de data sources y datasets en QuickSight
|   |   |-- terraform_rds.py               # Wrapper de Terraform con manejo de secretos
|   |   `-- verify_terraform_sources.py    # Verificacion de conectividad y esquemas fuente
|   `-- src/                               # Codigo fuente de pipelines y transformaciones
|       |-- airflow/                       # DAGs de orquestacion para el Data Warehouse
|       |-- dbt/                           # Proyecto dbt para modelado dimensional en Redshift
|       |   |-- dbt_project.yml            # Configuracion del proyecto dbt
|       |   |-- profiles.yml               # Perfil de conexion a Redshift
|       |   |-- models/
|       |   |   |-- intermediate/          # Limpieza, deduplicacion y validaciones de calidad
|       |   |   |-- marts/                 # Tablas de hechos y dimensiones (modelo estrella)
|       |   |   `-- quarantine/            # Registros defectuosos aislados
|       |   |-- seeds/                     # Catalogos estaticos (municipios, festivos)
|       |   |-- snapshots/                 # Historicos SCD Tipo 2 (clientes y productos)
|       |   `-- tests/                     # Pruebas automatizadas de consistencia e integridad
|       |-- ecommerce_dw/                  # Modulos Python de ingesta, generacion y puente
|       `-- quicksight/                    # Consultas SQL para capas de consumo analitico
|
|-- .gitignore                             # Exclusion de credenciales, binarios y temporales
`-- README.md                              # Documentacion general del repositorio
```

---

## Modulo 1: Data Lake Medallon

### Descripcion Tecnica
El modulo `data_lake/` implementa una arquitectura tipo Medallon en Amazon S3 orientada a la ingesta periodica, saneamiento, enriquecimiento con Inteligencia Artificial/PLN y consulta analitica de fuentes noticiosas en formato RSS (Ciencia, Tecnologia y Economia del diario El Tiempo).

Componentes principales:
1. **Capa Bronze**: Almacenamiento inmutable del payload XML original con particionamiento temporal (`ingestion_date=AAAA-MM-DD/run_id=<id>/`) y manifiestos de metadatos con hash SHA-256. Soporta reprocesamiento historico desacoplado de las fuentes web externas.
2. **Capa Silver**: Normalizacion estructurada en formato columnar Apache Parquet particionado por fecha (`dt=AAAA-MM-DD`). Incluye limpieza de marcado HTML, tipado fuerte, aislamiento de registros invalidos a zona de cuarentena y deduplicacion con trazabilidad de vigencia bajo SCD Tipo 1 (`is_active`).
3. **Enriquecimiento con Amazon Comprehend**: Extraccion de entidades nombradas (personas, organizaciones, ubicaciones) y frases clave con puntuaciones de confianza estadistica. Cuenta con una capa de cache en memoria basada en hash de contenido (`content_hash`) para evitar llamadas redundantes y optimizar costos.
4. **Capa Gold**: Datasets analiticos agregados en Parquet para medicion de volumen por seccion, rankings de organizaciones y auditorias de calidad.
5. **Catalogo y Consultas**: Registro serverless en AWS Glue Data Catalog (`rss_datalake_db`) y motor de consultas SQL interactivo mediante Amazon Athena.
6. **Orquestacion**: Pipeline de 7 tareas implementado en Apache Airflow bajo Docker en Amazon EC2, operando mediante IAM Instance Profile (despliegue sin credenciales embebidas).

Para instrucciones de despliegue, esquemas y reglas de negocio del Data Lake:
- Documento de arquitectura: `data_lake/docs/ARQUITECTURA.md`
- Diccionario de datos: `data_lake/docs/DICCIONARIO_DATOS.md`
- Reglas y estrategias tecnicas: `data_lake/docs/REGLAS_Y_ESTRATEGIAS.md`
- Guia de despliegue y costos: `data_lake/docs/GUIA_DESPLIEGUE_Y_COSTOS.md`

---

## Modulo 2: Data Warehouse Empresarial

### Descripcion Tecnica
El modulo `data_warehouse/` implementa una plataforma de analitica e-commerce de extremo a extremo que consolida informacion desde fuentes transaccionales relacionales y no relacionales hacia un Data Warehouse centralizado en Amazon Redshift Serverless, modelado con dbt y consumido mediante tableros de Business Intelligence en Amazon QuickSight con SPICE.

Componentes principales:
1. **Fuentes de Datos Hibridas**:
   - **Amazon RDS MySQL**: Almacena entidades relacionales del core transaccional (clientes, productos, pedidos, items de pedidos).
   - **Amazon DocumentDB**: Motor compatible con MongoDB para datos semiestructurados en documentos BSON/JSON (eventos de navegacion web y resenas de productos).
2. **Ingesta y Staging en S3**:
   - Modulo Python de extraccion segura sobre conexiones TLS hacia Amazon S3 privado.
   - Particionamiento jerarquico por fuente, entidad y lote de ejecucion, respaldado por manifiestos de control de carga.
3. **Almacenamiento y Carga (Data Warehouse)**:
   - **Amazon Redshift Serverless**: Motor de almacenamiento columnar masivamente paralelo.
   - Mecanismo de carga optimizado mediante sentencias `COPY` directas desde S3 utilizando roles IAM delegados sin exposicion de claves de acceso.
4. **Transformacion y Modelado con dbt (Data Build Tool)**:
   - Capa `intermediate`: Estandarizacion, deduplicacion, conversion de zonas horarias a tiempo local de negocio (`America/Bogota`) y saneamiento de defectos controlados.
   - Capa `marts`: Modelo dimensional (esquema estrella) con tablas de hechos (`fct_sales`, `fct_navigation_events`, `fct_reviews`) y dimensiones conformadas (`dim_customer`, `dim_product`, `dim_date`, `dim_geography`, `dim_sales_channel`, `dim_event_type`).
   - Dimensiones de Cambio Lento (SCD Tipo 2): Snapshots automaticos sobre `dim_customer` y `dim_product` para preservacion historica de atributos con vigencias `dbt_valid_from` y `dbt_valid_to`.
   - Control de Calidad: Segregacion de registros anomalos en esquemas de cuarentena y suite de pruebas automatizadas (`dbt test`).
5. **Orquestacion Centralizada**:
   - Apache Airflow ejecutado sobre una instancia EC2 dentro de la VPC privada, coordinando la secuencia de extraccion, carga a Redshift, transformaciones de dbt y refresco programado de QuickSight.
6. **Consumo y Visualizacion en Amazon QuickSight**:
   - Conexion privada hacia Redshift mediante QuickSight VPC Connection.
   - Ingesta en memoria acelerada mediante SPICE para analisis interactivo de KPIs comerciales, volumen de ventas y tendencias mensuales.

Para instrucciones de despliegue y operacion del Data Warehouse:
- Guia tecnica integral: `data_warehouse/README.md`
- Diagramas de arquitectura: `data_warehouse/docs/diagramas/`

---

## Politica de Seguridad y Exclusion en Control de Versiones

El archivo `.gitignore` centraliza la proteccion del repositorio para garantizar que ningun artefacto sensible, binario o temporal sea publicado:
- Credenciales y variables de entorno: `.env`, `*.env`, `*.pem`, `credentials.json`.
- Archivos de estado de infraestructura: `*.tfstate`, `*.tfstate.*`, `*.tfplan`, `terraform.tfvars`.
- Documentos binarios y reportes locales: `*.pdf`, `*.docx`, `*.png`, `*.jpg`.
- Archivos de log y entornos virtuales: `logs/`, `__pycache__/`, `.venv/`, `airflow.db`.
