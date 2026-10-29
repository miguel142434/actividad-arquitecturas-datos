SELECT
    sales.sale_sk,
    dates.date AS fecha,
    products.category AS categoria,
    channels.sales_channel AS canal,
    sales.quantity AS cantidad,
    CAST(sales.subtotal AS DECIMAL(18, 2)) AS subtotal
FROM marts.fct_sales AS sales
JOIN marts.dim_date AS dates ON dates.date_sk = sales.date_sk
JOIN marts.dim_product AS products ON products.product_sk = sales.product_sk
JOIN marts.dim_sales_channel AS channels ON channels.sales_channel_sk = sales.sales_channel_sk
