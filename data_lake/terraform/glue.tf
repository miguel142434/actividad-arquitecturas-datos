# Base de datos en AWS Glue Data Catalog
resource "aws_glue_catalog_database" "datalake_db" {
  name        = "rss_datalake_db"
  description = "Base de datos del Data Lake para noticias RSS (Silver y Gold)"
}

# Workgroup de Athena configurado con el bucket S3 para salida de consultas
resource "aws_athena_workgroup" "datalake_workgroup" {
  name = "${var.project_name}-workgroup"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.datalake.bucket}/athena-results/"
      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }

  force_destroy = true
}
