resource "aws_docdb_subnet_group" "sources" {
  name       = "${var.project_name}-documentdb"
  subnet_ids = [for subnet in aws_subnet.database : subnet.id]
}

resource "aws_docdb_cluster_parameter_group" "sources" {
  name   = "${var.project_name}-documentdb50"
  family = "docdb5.0"

  parameter {
    name         = "tls"
    value        = "enabled"
    apply_method = "pending-reboot"
  }
}

resource "aws_docdb_cluster" "sources" {
  cluster_identifier              = "${var.project_name}-documentdb"
  engine                          = "docdb"
  engine_version                  = "5.0.0"
  master_username                 = "dwadmin"
  master_password_wo              = var.documentdb_master_password
  master_password_wo_version      = var.documentdb_password_version
  port                            = 27017
  db_subnet_group_name            = aws_docdb_subnet_group.sources.name
  db_cluster_parameter_group_name = aws_docdb_cluster_parameter_group.sources.name
  vpc_security_group_ids          = [aws_security_group.documentdb.id]
  storage_encrypted               = true
  storage_type                    = "standard"
  backup_retention_period         = 1
  preferred_backup_window         = "07:00-07:30"
  preferred_maintenance_window    = "sun:08:00-sun:08:30"
  allow_major_version_upgrade     = false

  # Datos sintéticos reproducibles: eliminar sin snapshot final al cerrar el laboratorio.
  deletion_protection = false
  skip_final_snapshot = true
  tags                = { Name = "${var.project_name}-documentdb" }
}

resource "aws_docdb_cluster_instance" "sources" {
  identifier                 = "${var.project_name}-documentdb-1"
  cluster_identifier         = aws_docdb_cluster.sources.id
  engine                     = "docdb"
  instance_class             = "db.t3.medium"
  availability_zone          = "us-east-1a"
  auto_minor_version_upgrade = false
  copy_tags_to_snapshot      = true
  tags                       = { Name = "${var.project_name}-documentdb-1" }
}
