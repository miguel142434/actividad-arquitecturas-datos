# Arquitecturas de Datos - Ingeniería de Datos (EIA)

Este repositorio contiene la implementación práctica de arquitecturas empresariales para procesamiento analítico de datos: **Data Lake** y **Data Warehouse**.

---

## 📁 Estructura del Repositorio

```text
actividad_arquitecturas/
├── data_lake/                      # Módulo 1: Data Lake Medallón con AWS y Apache Airflow
│   ├── airflow/                   # Orquestación y pipelines ETL en Apache Airflow
│   │   ├── dags/                  # DAGs (rss_datalake_pipeline.py)
│   │   ├── scripts/               # Scripts de capas Bronze, Silver, Gold y Glue
│   │   ├── docker-compose.yaml    # Servicios de Airflow (Webserver, Scheduler, Postgres)
│   │   ├── Dockerfile             # Imagen Docker con dependencias
│   │   ├── requirements.txt       # Librerías Python (boto3, pandas, pyarrow)
│   │   └── .env.example           # Plantilla de variables de entorno
│   ├── terraform/                 # Infraestructura como Código (IaC) para Data Lake
│   │   ├── main.tf                # Configuración de proveedores AWS
│   │   ├── s3.tf                  # Bucket S3 único para arquitectura Medallón
│   │   ├── iam.tf                 # Políticas y roles IAM
│   │   ├── glue.tf                # Base de datos Glue Catalog y Athena Workgroup
│   │   ├── ec2.tf                 # Instancia EC2 con Docker para Airflow
│   │   ├── variables.tf           # Parámetros de despliegue
│   │   ├── outputs.tf             # Outputs de infraestructura
│   │   └── terraform.tfvars.example
│   └── docs/                      # Documentación técnica de arquitectura
│       ├── ARQUITECTURA.md        # Diagramas y decisiones de diseño
│       ├── DICCIONARIO_DATOS.md   # Catálogo y esquemas Bronze, Silver y Gold
│       ├── REGLAS_Y_ESTRATEGIAS.md# Reglas de negocio, deduplicación y calidad
│       ├── GUIA_DESPLIEGUE_Y_COSTOS.md
│       └── GUIA_EVIDENCIAS_Y_DEMOSTRACION.md
│
└── data_warehouse/                 # Módulo 2: Data Warehouse
    └── .gitkeep
```

---

## 🌊 Módulo Data Lake

El módulo `data_lake/` implementa una arquitectura medallón sobre Amazon S3 con enriquecimiento mediante Procesamiento de Lenguaje Natural (PLN con Amazon Comprehend), orquestada por Apache Airflow y catalogada con AWS Glue / Amazon Athena.

Para más detalles sobre el despliegue, componentes y operación del Data Lake, consulta:
- [data_lake/docs/ARQUITECTURA.md](file:///data_lake/docs/ARQUITECTURA.md)
- [data_lake/docs/GUIA_DESPLIEGUE_Y_COSTOS.md](file:///data_lake/docs/GUIA_DESPLIEGUE_Y_COSTOS.md)
- [data_lake/docs/DICCIONARIO_DATOS.md](file:///data_lake/docs/DICCIONARIO_DATOS.md)

---

## 🏛️ Módulo Data Warehouse

Espacio reservado para la implementación del modelado dimensional (estrella/copo de nieve), scripts DDL/DML, pipelines de carga y consultas OLAP correspondientes al módulo de Data Warehouse.
