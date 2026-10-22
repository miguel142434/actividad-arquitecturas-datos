variable "aws_region" {
  description = "Región de AWS donde se desplegarán los recursos"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Nombre base del proyecto"
  type        = string
  default     = "datalake-rss-eltiempo"
}

variable "environment" {
  description = "Entorno de despliegue"
  type        = string
  default     = "dev"
}

variable "bucket_name" {
  description = "Nombre único del bucket S3 para el Data Lake (Bronze, Silver, Gold)"
  type        = string
  default     = "" # Si está vacío, se generará dinámicamente con prefijo
}

variable "instance_type" {
  description = "Tipo de instancia EC2 para Airflow"
  type        = string
  default     = "t3.medium"
}

variable "allowed_cidr_blocks" {
  description = "Dirección IP o rango CIDR autorizado para acceder a Airflow y SSH"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "key_name" {
  description = "Nombre del Key Pair existente en AWS para acceder por SSH a la EC2 (opcional)"
  type        = string
  default     = "mazz-kp"
}
