-- Mismos datos y filtro de categoría que el dashboard.
-- Parámetros psycopg2: (categoria, categoria); (None, None) representa Todas.
WITH ventas AS (
    SELECT
        sales.sale_sk,
        products.category AS categoria,
        sales.subtotal
    FROM marts.fct_sales AS sales
    JOIN marts.dim_date AS dates ON dates.date_sk = sales.date_sk
    JOIN marts.dim_product AS products ON products.product_sk = sales.product_sk
    JOIN marts.dim_sales_channel AS channels ON channels.sales_channel_sk = sales.sales_channel_sk
)
SELECT COUNT(*) AS filas, COALESCE(SUM(subtotal), 0) AS ventas_totales
FROM ventas
WHERE (%s::VARCHAR IS NULL OR categoria = %s)
