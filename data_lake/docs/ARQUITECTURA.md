# Arquitectura del Data Lake Medallón para Noticias RSS

## 1. Visión General

El proyecto implementa una arquitectura de Data Lake tipo Medallón (Bronze, Silver, Gold) sobre Amazon Web Services (AWS) para recopilar, procesar, enriquecer y consultar noticias provenientes de los feeds RSS del periódico **El Tiempo**.

Todo el ciclo de vida del dato se orquesta mediante **Apache Airflow** desplegado sobre una instancia **Amazon EC2** con contenedores Docker. El almacenamiento físico se centraliza en un **único bucket de Amazon S3** con separación lógica por prefijos.

```mermaid
flowchart TD
    subgraph Fuentes["Fuentes Externas (RSS El Tiempo)"]
        F1["Ciencia (vida_ciencia.xml)"]
        F2["Tecnología (tecnosfera.xml)"]
        F3["Economía (economia.xml)"]
    end

    subgraph EC2["Amazon EC2 (Airflow & Python ETL)"]
        A_T1["Task 1: Validación de Conexión"]
        A_T2["Task 2: Extracción y Hash"]
        A_T3["Task 3-5: Limpieza, Deduplicación & Parquet"]
        A_T6["Task 6: Agregaciones Gold"]
        A_T7["Task 7: Sincronización Glue"]
        A_T8["Task 8: Validaciones Athena"]
        A_T9["Task 9: Auditoría del Lote"]
    end

    subgraph S3["Amazon S3 (Data Lake Único)"]
        B["bronze/\n(XML Original + Metadatos)"]
        Q["quarantine/\n(Registros con errores)"]
        S["silver/\n(Parquet particionado por dt)"]
        G["gold/\n(Agregaciones analíticas)"]
        R["athena-results/\n(Salida de consultas)"]
    end

    subgraph AWS_Services["Servicios Gestionados de AWS"]
        COMP["Amazon Comprehend\n(Entidades & Frases Clave)"]
        GLUE["AWS Glue Data Catalog\n(rss_datalake_db)"]
        ATHENA["Amazon Athena\n(Consultas SQL Serverless)"]
    end

    F1 & F2 & F3 -->|HTTP GET| A_T2
    A_T2 -->|Escribe XML crudo + Manifest| B
    B -->|Lee XML crudo| A_T3
    A_T3 -->|Textos para NLP con Caché| COMP
    COMP -->|Entidades y Scores| A_T3
    A_T3 -->|Registros inválidos| Q
    A_T3 -->|Escribe Parquet limpio| S
    S -->|Calcula métricas| A_T6
    A_T6 -->|Escribe Parquet analítico| G
    A_T7 -->|Registra tablas y particiones| GLUE
    GLUE -.->|Metadatos de esquemas| ATHENA
    ATHENA -->|Escanea Parquet| S
    ATHENA -->|Escanea Parquet| G
    ATHENA -->|Guarda resultados| R
```

---

## 2. Capas del Data Lake (Single Bucket Architecture)

1. **Bronze (`bronze/`)**:
   - Almacena el payload XML original recibido de cada feed RSS sin ninguna modificación estructural.
   - Guarda un archivo manifiesto JSON con la metadata del lote: `run_id`, URL consultada, fecha y hora UTC, código de estado HTTP, hash SHA-256 del contenido y cantidad de registros detectados.
   - Permite la reproducibilidad completa y el reprocesamiento sin volver a consumir los servidores del medio de comunicación.

2. **Silver (`silver/`)**:
   - Datos estructurados, limpiados, normalizados y deduplicados en formato columnar **Parquet** con compresión Snappy.
   - Enriquecidos con **Amazon Comprehend** para detectar personas, organizaciones, lugares y frases clave.
   - Tablas resultantes:
     - `silver_news`: Una fila por noticia vigente.
     - `silver_news_entities`: Una fila por entidad única detectada por noticia vigente.
     - `silver_news_key_phrases`: Una fila por frase clave única detectada por noticia vigente.
   - Particionamiento físico en S3 mediante la convención Hive: `dt=YYYY-MM-DD`.

3. **Cuarentena (`quarantine/`)**:
   - Registros defectuosos (XML malformado, ausencia de título o enlace).
   - Registra el motivo del rechazo y trazabilidad hacia el lote de Bronze.

4. **Gold (`gold/`)**:
   - Modelos analíticos preagregados y optimizados para responder directamente a las preguntas de negocio.
   - Formato Parquet particionado por `dt=YYYY-MM-DD`.
   - Tablas resultantes:
     - `gold_news_by_day`: Volumen de noticias por día, medio y sección.
     - `gold_top_entities`: Ranking de personas, organizaciones y ubicaciones presentes en más noticias distintas.
     - `gold_top_key_phrases`: Frecuencia de frases clave agrupadas por sección.
     - `gold_entity_trend`: Evolución diaria de mención de entidades clave.

5. **Resultados Athena (`athena-results/`)**:
   - Espacio dedicado para que Amazon Athena almacene los resultados de las consultas analíticas y DDL sin contaminar las capas analíticas.

---

## 3. Seguridad y Despliegue sin Secretos

- Toda la infraestructura está codificada en **Terraform**.
- **Cero llaves AWS quemadas**: La máquina EC2 utiliza un **IAM Instance Profile** (`aws_iam_instance_profile`) con permisos mínimos (Principio de Menor Privilegio) para acceder a S3, Comprehend, Glue y Athena.
- El bucket S3 tiene bloqueo total de acceso público (`aws_s3_bucket_public_access_block`) y encriptación en reposo del lado del servidor (`AES256`).
