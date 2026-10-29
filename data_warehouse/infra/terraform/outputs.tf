output "aws_region" {
  value = "us-east-1"
}

output "runner_public_ip" {
  value = aws_instance.runner.public_ip
}

output "runner_instance_id" {
  value = aws_instance.runner.id
}

output "ssh_target" {
  value = "ec2-user@${aws_instance.runner.public_ip}"
}

output "rds_endpoint" {
  value = aws_db_instance.mysql.address
}

output "rds_database" {
  value = aws_db_instance.mysql.db_name
}

output "rds_username" {
  value = aws_db_instance.mysql.username
}

output "private_subnet_ids" {
  value = [for subnet in aws_subnet.database : subnet.id]
}

output "documentdb_endpoint" {
  description = "Endpoint del clúster privado; usar desde EC2, con TLS y replicaSet rs0."
  value       = aws_docdb_cluster.sources.endpoint
}

output "documentdb_port" {
  value = aws_docdb_cluster.sources.port
}

output "documentdb_username" {
  value = aws_docdb_cluster.sources.master_username
}

output "documentdb_database" {
  description = "Nombre usado por los scripts; se materializa al escribir, no al crear el clúster."
  value       = "ecommerce"
}
