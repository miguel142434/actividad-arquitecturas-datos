-- ==============================================================================
-- CONSULTAS ANALÍTICAS Y DE VALIDACIÓN EN AMAZON ATHENA
-- Base de Datos: rss_datalake_db
-- ==============================================================================

-- 1. Consultar noticias por fecha y sección (Utiliza poda de particiones)
SELECT 
    news_id,
    media,
    section,
    title,
    link,
    pub_date_utc,
    dt
FROM rss_datalake_db.silver_news
WHERE dt = '2026-10-22' 
  AND section = 'tecnologia'
  AND is_active = true
ORDER BY pub_date_utc DESC;


-- 2. Obtener las diez organizaciones presentes en más noticias distintas
-- (A nivel de Gold o Silver directamente con distinct news_id)
SELECT 
    entity_text AS organizacion,
    SUM(distinct_news_count) AS total_noticias_distintas,
    ROUND(AVG(avg_confidence), 4) AS confianza_promedio
FROM rss_datalake_db.gold_top_entities
WHERE entity_type = 'ORGANIZATION'
GROUP BY entity_text
ORDER BY total_noticias_distintas DESC
LIMIT 10;


-- 3. Comparar la presencia de una entidad entre días (Evolución temporal)
-- Ejemplo con la entidad 'Colombia' o 'Gobierno'
SELECT 
    dt AS fecha,
    entity_text AS entidad,
    entity_type AS tipo,
    distinct_news_count AS noticias_asociadas
FROM rss_datalake_db.gold_entity_trend
WHERE LOWER(entity_text) IN ('colombia', 'gobierno', 'inteligencia artificial')
ORDER BY entity_text, dt ASC;


-- 4. Consultar las frases clave más frecuentes por sección
SELECT 
    section,
    key_phrase,
    SUM(frequency_count) AS total_menciones,
    ROUND(AVG(avg_confidence), 4) AS confianza_promedio
FROM rss_datalake_db.gold_top_key_phrases
GROUP BY section, key_phrase
ORDER BY section ASC, total_menciones DESC;


-- 5. Conciliación de indicadores: Comparar métricas calculadas en Gold contra Silver
-- Verifica que el total agregado en Gold coincida exactamente con el recuento directo en Silver
WITH silver_counts AS (
    SELECT 
        dt,
        media,
        section,
        COUNT(DISTINCT news_id) AS conteo_silver
    FROM rss_datalake_db.silver_news
    WHERE is_active = true
    GROUP BY dt, media, section
),
gold_counts AS (
    SELECT 
        dt,
        media,
        section,
        total_news AS conteo_gold
    FROM rss_datalake_db.gold_news_by_day
)
SELECT 
    s.dt,
    s.media,
    s.section,
    s.conteo_silver,
    g.conteo_gold,
    (s.conteo_silver - g.conteo_gold) AS diferencia_conciliacion,
    CASE 
        WHEN s.conteo_silver = g.conteo_gold THEN 'CONCILIADO OK'
        ELSE 'DESCUADRE DETECTADO'
    END AS estado_conciliacion
FROM silver_counts s
JOIN gold_counts g 
  ON s.dt = g.dt AND s.media = g.media AND s.section = g.section;


-- 6. Comparación de Bytes Escaneados (Optimización de costos y particionamiento)
-- Consulta A: CON filtro de partición (Athena lee únicamente la carpeta dt correspondiente)
SELECT COUNT(*) 
FROM rss_datalake_db.silver_news
WHERE dt = '2026-10-22';

-- Consulta B: SIN filtro de partición (Athena escanea todo el dataset en S3)
SELECT COUNT(*) 
FROM rss_datalake_db.silver_news
WHERE pub_date_utc LIKE '2026-10-22%';


-- 7. Pruebas de Calidad de Datos (Data Quality Tests)

-- 7.1 Unicidad del identificador en el conjunto de noticias vigentes
SELECT 
    news_id, 
    COUNT(*) AS ocurrencias
FROM rss_datalake_db.silver_news
WHERE is_active = true
GROUP BY news_id
HAVING COUNT(*) > 1;

-- 7.2 Presencia de campos obligatorios (debe retornar 0 filas)
SELECT COUNT(*) AS registros_con_nulos
FROM rss_datalake_db.silver_news
WHERE title IS NULL 
   OR title = '' 
   OR link IS NULL 
   OR link = '';

-- 7.3 Ausencia de entidades huérfanas (sin una noticia existente en silver_news)
SELECT COUNT(*) AS entidades_huerfanas
FROM rss_datalake_db.silver_news_entities e
LEFT JOIN rss_datalake_db.silver_news n ON e.news_id = n.news_id
WHERE n.news_id IS NULL;

-- 7.4 Ausencia de frases clave huérfanas
SELECT COUNT(*) AS frases_huerfanas
FROM rss_datalake_db.silver_news_key_phrases k
LEFT JOIN rss_datalake_db.silver_news n ON k.news_id = n.news_id
WHERE n.news_id IS NULL;
