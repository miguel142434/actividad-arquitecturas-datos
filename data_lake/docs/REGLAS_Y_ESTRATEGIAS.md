# Reglas de Negocio, Calidad y Estrategias Técnicas

## 1. Fuentes RSS Seleccionadas

Se seleccionaron tres feeds temáticos del diario **El Tiempo**:
1. **Ciencia**: `https://www.eltiempo.com/rss/vida_ciencia.xml`
2. **Tecnología**: `https://www.eltiempo.com/rss/tecnosfera.xml`
3. **Economía**: `https://www.eltiempo.com/rss/economia.xml`

**Criterio de configuración**:
- Cada feed está mapeado en `config.py` con atributos `source`, `section`, `name` y `url`.
- Se implementan headers HTTP (`User-Agent`) y timeouts defensivos de 20 segundos para evitar bloqueos por WAF.

---

## 2. Estrategia de Identificación Única y Deduplicación

### 2.1 Identificador Único (`news_id`)
1. Se extrae el elemento `<guid>` del XML.
2. Si el GUID no está presente o viene vacío, se calcula un hash determinístico:
   $$\text{news\_id} = \text{SHA-256}(\text{trim}(\text{link}))$$
3. **Limitación conocida**: Si un mismo artículo es sindicado en dos secciones distintas con diferentes URLs canónicas, generará dos IDs. Sin embargo, en el mismo feed o en ejecuciones subsecuentes, el hash garantiza la unicidad.

### 2.2 Deduplicación Dentro del Lote y Entre Lotes
- **Dentro del lote**: Un `Set` en memoria descarta ocurrencias repetidas del mismo `news_id` antes de emitir a Silver.
- **Entre lotes**: Cada registro calcula un `content_hash = SHA-256(titulo_limpio + " " + descripcion_limpia)`.
- Si llega un nuevo lote con una noticia ya existente y su `content_hash` es idéntico, se considera no modificada.

---

## 3. Optimización y Control de Costos en Amazon Comprehend

Amazon Comprehend cobra por unidades de texto procesadas (lotes de 100 caracteres). Para cumplir con la restricción de **no realizar llamadas innecesarias a Comprehend cuando el texto no haya cambiado**:

1. **Estrategia de Caché por Hash**:
   - Antes de llamar a `detect_entities` o `detect_key_phrases`, se consulta la memoria o estado con la clave `content_hash`.
   - Si el hash coincide, se reutilizan las anotaciones previamente calculadas.
2. **Tratamiento de Longitud**:
   - El límite estricto de la API de Comprehend es de 5.000 bytes en UTF-8 por documento.
   - Todo texto resultante de la unión de título y descripción se valida; si excede 4.800 bytes, se trunca de forma segura a nivel de bytes decodificando con bandera de ignorar caracteres incompletos.
3. **Textos Vacíos o Inválidos**:
   - Si el texto está vacío o contiene solo espacios, no se invoca a Comprehend y se descarta o pasa a cuarentena según su gravedad.

---

## 4. Calidad de Datos y Manejo de Cuarentena

### 4.1 Criterios de Rechazo a Cuarentena (`quarantine/`)
Un registro se desvía a la ruta `quarantine/date=YYYY-MM-DD/run_id=<id>/invalid_records.json` cuando:
1. El XML descargado está malformado y no pudo ser interpretado por el parser.
2. El título (`<title>`) está vacío o es nulo.
3. El enlace (`<link>`) está ausente o mal formado.

Cada registro en cuarentena conserva:
- Motivo exacto del rechazo.
- Fuente y sección de procedencia.
- Referencia al archivo crudo en Bronze.
- Marca temporal del rechazo.

---

## 5. Estrategia de Incrementalidad, Idempotencia y Recuperación

### 5.1 Idempotencia
- Todos los archivos Parquet en Silver y Gold se nombran con sufijo `_{run_id}.parquet`.
- En caso de que falle una tarea y deba reintentarse, la reejecución sobre el mismo `run_id` sobreescribe de manera atómica el archivo en S3 sin generar duplicados.

### 5.2 Reprocesamiento sin Consultar Fuentes Externas
- El DAG de Airflow expone el parámetro de ejecución `reprocess_run_id`.
- Si este parámetro se suministra con el ID de una corrida previa, el extractor de Bronze omite la llamada HTTP a `eltiempo.com` y lee directamente el archivo `raw_feed.xml` que fue archivado en S3.
- Esto permite reconstruir completamente las capas Silver y Gold en caso de cambios en la lógica de negocio sin depender de la disponibilidad del medio externo.

### 5.3 Tratamiento de Noticias sin Fecha Válida
- Si el campo `pubDate` viene ausente o con un formato incompatible con RFC 822:
  - Se almacena el valor original como texto en `pub_date_original`.
  - Se asigna como valor por defecto en `dt` la fecha de ingesta (`ingestion_date`).
  - Esto evita la pérdida de información y asegura que la partición Hive de S3 no quede vacía.
