resource "aws_db_subnet_group" "mysql" {
  name       = "${var.project_name}-mysql"
  subnet_ids = [for subnet in aws_subnet.database : subnet.id]
}

resource "aws_db_parameter_group" "mysql" {
  name   = "${var.project_name}-mysql84"
  family = "mysql8.4"

  parameter {
    name         = "require_secure_transport"
    value        = "1"
    apply_method = "immediate"
  }
}

resource "aws_db_instance" "mysql" {
  identifier                   = "${var.project_name}-mysql"
  engine                       = "mysql"
  engine_version               = var.rds_engine_version
  engine_lifecycle_support     = "open-source-rds-extended-support-disabled"
  instance_class               = "db.t4g.micro"
  allocated_storage            = 20
  storage_type                 = "gp3"
  storage_encrypted            = true
  db_name                      = "ecommerce"
  username                     = "dwadmin"
  password_wo                  = var.rds_master_password
  password_wo_version          = var.rds_password_version
  port                         = 3306
  db_subnet_group_name         = aws_db_subnet_group.mysql.name
  parameter_group_name         = aws_db_parameter_group.mysql.name
  vpc_security_group_ids       = [aws_security_group.rds.id]
  availability_zone            = "us-east-1a"
  publicly_accessible          = false
  multi_az                     = false
  auto_minor_version_upgrade   = false
  backup_retention_period      = 1
  copy_tags_to_snapshot        = true
  delete_automated_backups     = true
  monitoring_interval          = 0
  performance_insights_enabled = false

  # Laboratorio de datos sintéticos: destroy elimina los datos sin snapshot final.
  deletion_protection = false
  skip_final_snapshot = true
  tags                = { Name = "${var.project_name}-mysql" }
}
