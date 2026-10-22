# Diccionario de Datos del Data Lake

## 1. Capa Bronze (Metadatos del Manifiesto)

**Ubicación**: `s3://<bucket>/bronze/source=<source>_<section>/ingestion_date=YYYY-MM-DD/run_id=<run_id>/manifest.json`

| Campo | Tipo | Descripción |
|---|---|---|
| `run_id` | STRING | Identificador único de la corrida de extracción |
| `media` | STRING | Nombre del medio (`El Tiempo`) |
| `source` | STRING | Identificador de la fuente (`el_tiempo`) |
| `section` | STRING | Sección temática (`ciencia`, `tecnologia`, `economia`) |
| `url` | STRING | URL del feed consultado |
| `ingestion_timestamp_utc` | STRING (ISO 8601) | Marca temporal de la ingesta en UTC |
| `http_status` | INTEGER | Código de respuesta HTTP (ejemplo: 200) |
| `content_hash` | STRING (SHA-256) | Hash criptográfico del payload XML original |
| `s3_bucket` | STRING | Nombre del bucket del Data Lake |
| `s3_raw_key` | STRING | Ruta al archivo XML original almacenado |
| `records_detected` | INTEGER | Cantidad de elementos `<item>` extraídos |
| `is_reprocessing` | BOOLEAN | Indica si provino de una nueva consulta o de reprocesamiento |

---

## 2. Capa Silver

### 2.1 Tabla `silver_news`
**Ubicación**: `s3://<bucket>/silver/news/dt=YYYY-MM-DD/`  
**Granularidad**: Una fila por noticia vigente.

| Columna | Tipo de Dato | Partición | Descripción |
|---|---|---|---|
| `news_id` | STRING | No | Identificador único (GUID del feed o hash del enlace) |
| `source` | STRING | No | Identificador de la fuente (`el_tiempo`) |
| `media` | STRING | No | Nombre del medio de comunicación (`El Tiempo`) |
| `section` | STRING | No | Sección de la noticia (`ciencia`, `tecnologia`, `economia`) |
| `title` | STRING | No | Título limpio de la noticia sin etiquetas HTML |
| `description` | STRING | No | Resumen/cuerpo disponible limpio de etiquetas HTML |
| `link` | STRING | No | URL pública del artículo |
| `pub_date_original`| STRING | No | Fecha tal como venía en el XML (RFC 822) |
| `pub_date_utc` | STRING | No | Fecha y hora normalizada en formato UTC (`YYYY-MM-DD HH:MM:SS`) |
| `content_hash` | STRING | No | Hash SHA-256 del texto (título + descripción) para detección de cambios |
| `bronze_source_file`| STRING | No | Ruta en S3 al archivo de origen en Bronze |
| `run_id` | STRING | No | Lote o corrida de Airflow que procesó la noticia |
| `is_active` | BOOLEAN | No | `true` si es la versión vigente de la noticia |
| `dt` | STRING | **Sí (Hive)** | Fecha de partición analítica (`YYYY-MM-DD`) |

### 2.2 Tabla `silver_news_entities`
**Ubicación**: `s3://<bucket>/silver/news_entities/dt=YYYY-MM-DD/`  
**Granularidad**: Una fila por entidad distinta detectada en cada noticia vigente.

| Columna | Tipo de Dato | Partición | Descripción |
|---|---|---|---|
| `news_id` | STRING | No | Llave foránea hacia `silver_news` |
| `entity_text` | STRING | No | Texto de la mención detectada (ej. `Google`, `Colombia`) |
| `entity_type` | STRING | No | Categoría: `PERSON`, `ORGANIZATION`, `LOCATION` |
| `confidence_score`| DOUBLE | No | Puntuación de certeza devuelta por Amazon Comprehend (0 a 1) |
| `language` | STRING | No | Código del idioma analizado (`es`) |
| `analyzed_text_hash`| STRING | No | Hash del texto evaluado |
| `analyzed_at_utc` | STRING | No | Timestamp UTC de cuando se ejecutó el análisis |
| `run_id` | STRING | No | Identificador del lote de procesamiento |
| `dt` | STRING | **Sí (Hive)** | Fecha de partición analítica (`YYYY-MM-DD`) |

### 2.3 Tabla `silver_news_key_phrases`
**Ubicación**: `s3://<bucket>/silver/news_key_phrases/dt=YYYY-MM-DD/`  
**Granularidad**: Una fila por frase clave distinta detectada en cada noticia vigente.

| Columna | Tipo de Dato | Partición | Descripción |
|---|---|---|---|
| `news_id` | STRING | No | Llave foránea hacia `silver_news` |
| `key_phrase` | STRING | No | Frase clave detectada por Amazon Comprehend |
| `confidence_score`| DOUBLE | No | Nivel de confianza devuelto por el servicio |
| `language` | STRING | No | Código del idioma analizado (`es`) |
| `analyzed_text_hash`| STRING | No | Hash del texto evaluado |
| `analyzed_at_utc` | STRING | No | Timestamp UTC del análisis |
| `run_id` | STRING | No | Identificador del lote |
| `dt` | STRING | **Sí (Hive)** | Fecha de partición analítica (`YYYY-MM-DD`) |

---

## 3. Capa Gold

### 3.1 Tabla `gold_news_by_day`
**Ubicación**: `s3://<bucket>/gold/gold_news_by_day/dt=YYYY-MM-DD/`  
**Granularidad**: Conteo de noticias por día, medio y sección.

| Columna | Tipo de Dato | Partición | Descripción |
|---|---|---|---|
| `media` | STRING | No | Nombre del medio (`El Tiempo`) |
| `section` | STRING | No | Sección temática |
| `total_news` | BIGINT | No | Número de noticias únicas vigentes publicadas |
| `run_id` | STRING | No | Lote de generación |
| `dt` | STRING | **Sí** | Fecha de publicación |

### 3.2 Tabla `gold_top_entities`
**Ubicación**: `s3://<bucket>/gold/gold_top_entities/dt=YYYY-MM-DD/`  
**Granularidad**: Presencia de entidades en noticias distintas por día y tipo.

| Columna | Tipo de Dato | Partición | Descripción |
|---|---|---|---|
| `entity_text` | STRING | No | Nombre de la entidad |
| `entity_type` | STRING | No | `PERSON`, `ORGANIZATION`, `LOCATION` |
| `distinct_news_count` | BIGINT | No | Conteo de noticias distintas donde aparece la entidad |
| `avg_confidence` | DOUBLE | No | Promedio del score de confianza |
| `run_id` | STRING | No | Lote de generación |
| `dt` | STRING | **Sí** | Fecha de publicación |

### 3.3 Tabla `gold_top_key_phrases`
**Ubicación**: `s3://<bucket>/gold/gold_top_key_phrases/dt=YYYY-MM-DD/`  
**Granularidad**: Frecuencia de frases clave por día y sección.

| Columna | Tipo de Dato | Partición | Descripción |
|---|---|---|---|
| `section` | STRING | No | Sección temática |
| `key_phrase` | STRING | No | Frase clave detectada |
| `frequency_count` | BIGINT | No | Cantidad de noticias distintas que contienen la frase |
| `avg_confidence` | DOUBLE | No | Puntuación de confianza promedio |
| `run_id` | STRING | No | Lote de generación |
| `dt` | STRING | **Sí** | Fecha de publicación |

### 3.4 Tabla `gold_entity_trend`
**Ubicación**: `s3://<bucket>/gold/gold_entity_trend/dt=YYYY-MM-DD/`  
**Granularidad**: Evolución temporal de una entidad para comparación entre días.

| Columna | Tipo de Dato | Partición | Descripción |
|---|---|---|---|
| `entity_text` | STRING | No | Nombre de la entidad |
| `entity_type` | STRING | No | Tipo de entidad |
| `distinct_news_count` | BIGINT | No | Cantidad de noticias distintas en ese día |
| `run_id` | STRING | No | Lote de generación |
| `dt` | STRING | **Sí** | Fecha de observación |
