import os

# Configuración de AWS y Data Lake
DATALAKE_BUCKET = os.getenv("DATALAKE_BUCKET", "datalake-rss-eltiempo-dev")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
GLUE_DATABASE = os.getenv("GLUE_DATABASE", "rss_datalake_db")
ATHENA_WORKGROUP = os.getenv("ATHENA_WORKGROUP", "datalake-rss-eltiempo-workgroup")

# Fuentes RSS seleccionadas de El Tiempo
RSS_FEEDS = [
    {
        "source": "el_tiempo",
        "section": "ciencia",
        "name": "El Tiempo - Ciencia",
        "url": "https://www.eltiempo.com/rss/vida_ciencia.xml"
    },
    {
        "source": "el_tiempo",
        "section": "tecnologia",
        "name": "El Tiempo - Tecnósfera",
        "url": "https://www.eltiempo.com/rss/tecnosfera.xml"
    },
    {
        "source": "el_tiempo",
        "section": "economia",
        "name": "El Tiempo - Economía",
        "url": "https://www.eltiempo.com/rss/economia.xml"
    }
]

# Headers para evitar bloqueos por WAF o User-Agent
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*"
}
