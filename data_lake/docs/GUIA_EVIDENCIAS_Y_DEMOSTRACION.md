# Guía de Recolección de Evidencias y Demostración

Este documento detalla el paso a paso exacto para recolectar todas las evidencias solicitadas en los **puntos 3 y 4 de la guía**.

---

## PARTE 1: Evidencias de Funcionamiento (Punto 3)

### 1.1 Ejecución del DAG en Airflow
1. Ingresa a la interfaz web de Airflow: `http://<IP_EC2>:8080`.
2. Dirígete al DAG `rss_datalake_eltiempo_pipeline`.
3. **Capturas requeridas**:
   - **Vista Grid**: Muestra la barra de estado de las corridas con los 9 bloques en color verde brillante (`success`).
   - **Vista Graph**: Muestra el flujo completo con las dependencias entre tareas (`task_validate_config` $\to$ `task_extract_to_bronze` $\to$ ... $\to$ `task_log_final_status`).
   - **Log de la Tarea 9 (`task_log_final_status`)**: Haz clic en el cuadro verde de esta tarea y abre la pestaña **Log**. Toma captura del JSON final donde reporta el resumen de fuentes procesadas y el estado `COMPLETED_SUCCESSFULLY`.

---

### 1.2 Archivos de Bronze, Silver y Gold en S3
Ingresa a la consola de AWS S3 o usa la terminal para listar los archivos:

#### A. Capa Bronze (Archivos originales y manifiesto)
- Ingresa a tu bucket S3: `s3://<bucket>/bronze/`.
- Navega dentro de una fuente, por ejemplo: `source=el_tiempo_ciencia/ingestion_date=YYYY-MM-DD/run_id=.../`.
- **Captura**: Muestra la presencia de los dos archivos:
  - `raw_feed.xml` (el XML original descargado).
  - `manifest.json` (abre o descarga este archivo y toma captura de su contenido con el hash SHA-256, URL y timestamp UTC).

#### B. Capa Silver (Tablas Parquet particionadas)
- Navega en S3 a:
  - `s3://<bucket>/silver/news/dt=YYYY-MM-DD/` $\to$ `news_<run_id>.parquet`
  - `s3://<bucket>/silver/news_entities/dt=YYYY-MM-DD/` $\to$ `entities_<run_id>.parquet`
  - `s3://<bucket>/silver/news_key_phrases/dt=YYYY-MM-DD/` $\to$ `key_phrases_<run_id>.parquet`
- **Captura**: Muestra la estructura de carpetas `dt=...` y los archivos Parquet Snappy.

#### C. Capa Gold (Agregaciones analíticas)
- Navega en S3 a:
  - `s3://<bucket>/gold/gold_news_by_day/dt=.../`
  - `s3://<bucket>/gold/gold_top_entities/dt=.../`
  - `s3://<bucket>/gold/gold_top_key_phrases/dt=.../`
  - `s3://<bucket>/gold/gold_entity_trend/dt=.../`
- **Captura**: Muestra las carpetas con los Parquet de las métricas.

---

### 1.3 Resultados de Amazon Comprehend
Debes demostrar que el servicio de procesamiento de lenguaje natural identificó entidades y frases clave:
1. En **Amazon Athena**, selecciona la base de datos `rss_datalake_db`.
2. Ejecuta esta consulta:
   ```sql
   SELECT news_id, entity_text, entity_type, confidence_score, language, analyzed_at_utc 
   FROM rss_datalake_db.silver_news_entities 
   LIMIT 15;
   ```
3. **Captura**: Muestra la tabla de resultados con las columnas de personas, organizaciones, lugares y las puntuaciones de confianza (confidence scores entre 0.8 y 0.99).
4. Ejecuta también la consulta de frases clave:
   ```sql
   SELECT news_id, key_phrase, confidence_score 
   FROM rss_datalake_db.silver_news_key_phrases 
   LIMIT 10;
   ```

---

### 1.4 Tablas y Particiones en AWS Glue Data Catalog
1. En la consola de AWS, busca el servicio **AWS Glue** $\to$ **Data Catalog** $\to$ **Databases**.
2. Selecciona `rss_datalake_db`.
3. Haz clic en **Tables**.
4. **Captura 1**: Lista de las 7 tablas registradas:
   - `silver_news`
   - `silver_news_entities`
   - `silver_news_key_phrases`
   - `gold_news_by_day`
   - `gold_top_entities`
   - `gold_top_key_phrases`
   - `gold_entity_trend`
5. Haz clic en la tabla `silver_news` y entra a la pestaña **Partitions**.
6. **Captura 2**: Muestra la partición detectada `dt=YYYY-MM-DD` apuntando a la ruta correspondiente en S3.

---

### 1.5 Consultas y Resultados en Athena
Abre **Amazon Athena** $\to$ **Query Editor** (asegúrate de que el Workgroup sea el creado por Terraform) y ejecuta las consultas analíticas del archivo `airflow/scripts/athena_queries.sql`:

1. **Top 10 organizaciones en más noticias**:
   ```sql
   SELECT 
       entity_text AS organizacion,
       SUM(distinct_news_count) AS total_noticias_distintas,
       ROUND(AVG(avg_confidence), 4) AS confianza_promedio
   FROM rss_datalake_db.gold_top_entities
   WHERE entity_type = 'ORGANIZATION'
   GROUP BY entity_text
   ORDER BY total_noticias_distintas DESC
   LIMIT 10;
   ```
   - **Captura**: La tabla con las organizaciones más frecuentes.

2. **Frases clave más frecuentes por sección**:
   ```sql
   SELECT 
       section,
       key_phrase,
       SUM(frequency_count) AS total_menciones
   FROM rss_datalake_db.gold_top_key_phrases
   GROUP BY section, key_phrase
   ORDER BY section ASC, total_menciones DESC
   LIMIT 10;
   ```
   - **Captura**: Resultados por sección (ciencia, tecnología, economía).

---

### 1.6 Validación de Calidad, Incrementalidad y Particionamiento

#### A. Calidad de Datos (Unicidad y Reglas de Negocio)
En Athena ejecuta:
```sql
-- Verificar que no haya IDs duplicados en el conjunto vigente (Debe dar 0 filas)
SELECT news_id, COUNT(*) 
FROM rss_datalake_db.silver_news 
WHERE is_active = true 
GROUP BY news_id 
HAVING COUNT(*) > 1;

-- Verificar que no haya títulos ni links nulos (Debe retornar 0)
SELECT COUNT(*) AS errores_nulos 
FROM rss_datalake_db.silver_news 
WHERE title IS NULL OR link IS NULL;
```
- **Captura**: El resultado mostrando que el dataset cumple con las reglas de integridad.

#### B. Optimización de Costos y Particionamiento (Bytes Escaneados)
Ejecuta sucesivamente estas dos consultas en Athena y revisa la pestaña **Execution details** (abajo a la derecha):
```sql
-- Consulta CON partición (escaneo acotado)
SELECT COUNT(*) FROM rss_datalake_db.silver_news WHERE dt = '2026-10-22';

-- Consulta SIN partición (escaneo de todo el directorio)
SELECT COUNT(*) FROM rss_datalake_db.silver_news WHERE pub_date_utc LIKE '2026-10-22%';
```
- **Captura**: Compara el campo **Data scanned** (por ejemplo: `12.5 KB` con partición vs `45.2 KB` sin partición). Esto evidencia la optimización de costos.

---

## PARTE 2: Guía de Demostración (Punto 4)

### 2.1 Demostración 1: Ejecutar una Ingesta Completa
1. En la UI de Airflow, activa el DAG o presiona el botón **Trigger DAG**.
2. Muestra cómo se van encendiendo en verde cada una de las tareas desde la validación de AWS hasta la publicación en S3 y Athena.
3. Explica brevemente: *"El DAG extrae en paralelo los 3 feeds RSS de El Tiempo, persiste el XML crudo en Bronze con su hash SHA-256, limpia HTML y normaliza a UTC en Silver, ejecuta Amazon Comprehend reutilizando el caché de texto, y finalmente calcula los agregados analíticos en Gold."*

---

### 2.2 Demostración 2: Consultar Indicadores y Conciliación Gold vs Silver
En Athena ejecuta la consulta de conciliación:
```sql
WITH silver_counts AS (
    SELECT dt, media, section, COUNT(DISTINCT news_id) AS conteo_silver
    FROM rss_datalake_db.silver_news
    WHERE is_active = true
    GROUP BY dt, media, section
),
gold_counts AS (
    SELECT dt, media, section, total_news AS conteo_gold
    FROM rss_datalake_db.gold_news_by_day
)
SELECT 
    s.dt, s.media, s.section, s.conteo_silver, g.conteo_gold,
    (s.conteo_silver - g.conteo_gold) AS diferencia,
    CASE WHEN s.conteo_silver = g.conteo_gold THEN 'CONCILIADO OK' ELSE 'DESCUADRE' END AS estado
FROM silver_counts s
JOIN gold_counts g ON s.dt = g.dt AND s.media = g.media AND s.section = g.section;
```
- Muestra que la columna `diferencia` es **0** y el estado es **`CONCILIADO OK`**. Esto demuestra que la agregación de Gold concilia perfectamente con los datos atómicos de Silver.

---

### 2.3 Demostración 3: Reprocesar un Lote sin Duplicar Resultados (Idempotencia)
1. Toma el `run_id` de una ejecución previa (por ejemplo: `manual__2026-10-22T12_00_00_000000_00_00`).
2. En Airflow, presiona la flecha al lado del botón Play y selecciona: **Trigger DAG w/ config**.
3. En el campo JSON de configuración escribe:
   ```json
   {
     "reprocess_run_id": "manual__2026-10-22T12_00_00_000000_00_00"
   }
   ```
4. Haz clic en **Trigger**.
5. Abre el log de `task_extract_to_bronze`:
   - Muestra la línea que dice:
     `Modo Reprocesamiento: Consultando S3 existente s3://.../raw_feed.xml`.
   - Explica: *"No se consultó el servidor de El Tiempo, se reutilizó el archivo original de Bronze."*
6. Vuelve a Athena y ejecuta el conteo total de noticias vigentes:
   - Muestra que el total de registros no se duplicó gracias a la escritura idempotente de los archivos Parquet.

---

### 2.4 Demostración 4: Recuperación ante un Fallo Controlado
1. **Provocar el fallo**:
   - En Airflow o temporalmente en el script, simula un fallo (por ejemplo, desconecta momentáneamente el acceso o ingresa un nombre de bucket incorrecto en un test).
   - O más sencillo: mientras corre el DAG, haz clic en una de las tareas intermedias (ej. `task_process_silver`) y selecciónala como **Mark as Failed**.
   - El DAG se detendrá y quedará en rojo en ese paso.
2. **Explicar la trazabilidad**:
   - Muestra cómo los logs de Airflow identifican con exactitud qué tarea, qué lote y qué fuente fallaron, y confirma que las tareas anteriores (Bronze) conservaron su archivo en S3 intacto.
3. **Recuperación**:
   - Corrige el problema o presiona sobre la tarea fallida el botón **Clear task** (con la opción *Downstream* seleccionada).
   - Airflow reanudará la ejecución exactamente desde el punto donde ocurrió el fallo, sin necesidad de repetir la extracción de Bronze ni duplicar datos.
   - Todo el DAG volverá a ponerse en verde.

---

### 2.5 Demostración 5: Explicar una Limitación del Enriquecimiento de Texto

En la sustentación, expón una o dos de las siguientes limitaciones técnicas reales de **Amazon Comprehend**:

1. **Ausencia de Resolución de Entidades (Entity Resolution / Desambiguación)**:
   - *Explicación*: Amazon Comprehend detecta menciones de texto literales. Si en una noticia dice *"Gustavo Petro"* y en otra noticia dice *"el presidente Petro"*, Comprehend extrae dos entidades distintas (`"Gustavo Petro"` y `"Petro"`). El servicio no tiene un grafo de conocimiento interno para unificar ambas menciones en una misma persona. Esto puede dispersar las estadísticas a menos que se aplique una capa de entity resolution o normalización con embeddings.
2. **Límite de Longitud por Documento**:
   - *Explicación*: La API de Comprehend tiene un límite estricto de **5.000 bytes UTF-8** por llamada. Si una noticia tuviera un cuerpo extenso, el texto debe ser fragmentado o truncado, lo que puede causar pérdida de contexto al final del artículo.
3. **Ambigüedad Contextual y Polisemia**:
   - *Explicación*: Palabras con doble significado (como *"Corona"* refiriéndose al virus, a la empresa cervecera o a la monarquía) pueden ser etiquetadas erróneamente como `ORGANIZATION` o `OTHER` dependiendo del contexto inmediato.
