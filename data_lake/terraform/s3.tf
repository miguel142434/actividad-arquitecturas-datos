locals {
  actual_bucket_name = var.bucket_name != "" ? var.bucket_name : "${var.project_name}-${var.environment}-${random_id.suffix.hex}"
}

# Bucket único para todas las capas del Data Lake (Bronze, Silver, Gold, Cuarentena y Resultados de Athena)
resource "aws_s3_bucket" "datalake" {
  bucket        = local.actual_bucket_name
  force_destroy = true # Facilita la limpieza completa del laboratorio al destruir con terraform
}

resource "aws_s3_bucket_versioning" "datalake_versioning" {
  bucket = aws_s3_bucket.datalake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "datalake_encryption" {
  bucket = aws_s3_bucket.datalake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "datalake_public_block" {
  bucket                  = aws_s3_bucket.datalake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Creación simbólica de los prefijos de la arquitectura medallón
resource "aws_s3_object" "bronze_folder" {
  bucket = aws_s3_bucket.datalake.id
  key    = "bronze/"
}

resource "aws_s3_object" "silver_folder" {
  bucket = aws_s3_bucket.datalake.id
  key    = "silver/"
}

resource "aws_s3_object" "gold_folder" {
  bucket = aws_s3_bucket.datalake.id
  key    = "gold/"
}

resource "aws_s3_object" "quarantine_folder" {
  bucket = aws_s3_bucket.datalake.id
  key    = "quarantine/"
}

resource "aws_s3_object" "athena_results_folder" {
  bucket = aws_s3_bucket.datalake.id
  key    = "athena-results/"
}
