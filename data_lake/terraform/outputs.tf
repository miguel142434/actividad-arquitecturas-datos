output "s3_bucket_name" {
  description = "Nombre del bucket S3 creado para el Data Lake"
  value       = aws_s3_bucket.datalake.bucket
}

output "ec2_public_ip" {
  description = "Dirección IP pública de la instancia EC2 donde corre Airflow"
  value       = aws_instance.airflow_node.public_ip
}

output "airflow_ui_url" {
  description = "URL para acceder a la consola web de Apache Airflow"
  value       = "http://${aws_instance.airflow_node.public_ip}:8080"
}

output "glue_database_name" {
  description = "Nombre de la base de datos en AWS Glue Data Catalog"
  value       = aws_glue_catalog_database.datalake_db.name
}

output "athena_workgroup_name" {
  description = "Nombre del Workgroup de Athena"
  value       = aws_athena_workgroup.datalake_workgroup.name
}

output "ssh_connection_command" {
  description = "Comando para conectarse por SSH a la instancia EC2"
  value       = "ssh -i <mazz-kp.pem> ubuntu@${aws_instance.airflow_node.public_ip}"
}
