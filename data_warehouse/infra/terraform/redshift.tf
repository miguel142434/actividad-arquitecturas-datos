# Tercera AZ exclusivamente para Redshift con Enhanced VPC Routing.
resource "aws_subnet" "warehouse" {
  vpc_id                  = aws_vpc.main.id
  availability_zone       = "us-east-1c"
  cidr_block              = "10.42.12.0/24"
  map_public_ip_on_launch = false
  tags                    = { Name = "${var.project_name}-redshift-c" }
}

resource "aws_route_table_association" "warehouse" {
  subnet_id      = aws_subnet.warehouse.id
  route_table_id = aws_route_table.private.id
}

resource "aws_security_group" "redshift" {
  name        = "${var.project_name}-redshift"
  description = "Redshift privado, SQL solo desde EC2"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "redshift" {
  security_group_id            = aws_security_group.redshift.id
  referenced_security_group_id = aws_security_group.runner.id
  ip_protocol                  = "tcp"
  from_port                    = 5439
  to_port                      = 5439
}

resource "aws_vpc_security_group_egress_rule" "redshift_sql" {
  security_group_id            = aws_security_group.runner.id
  referenced_security_group_id = aws_security_group.redshift.id
  ip_protocol                  = "tcp"
  from_port                    = 5439
  to_port                      = 5439
}

resource "aws_vpc_security_group_egress_rule" "redshift_s3" {
  security_group_id = aws_security_group.redshift.id
  prefix_list_id    = aws_vpc_endpoint.s3.prefix_list_id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_iam_role" "redshift" {
  name = "${var.project_name}-redshift-copy"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = ["redshift.amazonaws.com", "redshift-serverless.amazonaws.com"] }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "redshift_copy" {
  name = "read-raw-batches"
  role = aws_iam_role.redshift.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:ListBucket"]
      Resource = [aws_s3_bucket.raw.arn]
      }, {
      Effect   = "Allow"
      Action   = ["s3:GetObject"]
      Resource = ["${aws_s3_bucket.raw.arn}/raw/*", "${aws_s3_bucket.raw.arn}/control/batches/*"]
    }]
  })
}

resource "aws_redshiftserverless_namespace" "warehouse" {
  namespace_name                 = "${var.project_name}-warehouse"
  db_name                        = "ecommerce"
  admin_username                 = "dwadmin"
  admin_user_password_wo         = var.redshift_master_password
  admin_user_password_wo_version = var.redshift_password_version
  iam_roles                      = [aws_iam_role.redshift.arn]
  default_iam_role_arn           = aws_iam_role.redshift.arn
  # Sin snapshot final configurado: laboratorio sintético reproducible.
}

resource "aws_redshiftserverless_workgroup" "warehouse" {
  workgroup_name       = "${var.project_name}-warehouse"
  namespace_name       = aws_redshiftserverless_namespace.warehouse.namespace_name
  base_capacity        = 4
  max_capacity         = 4
  enhanced_vpc_routing = true
  publicly_accessible  = false
  port                 = 5439
  subnet_ids           = concat([for subnet in aws_subnet.database : subnet.id], [aws_subnet.warehouse.id])
  security_group_ids   = [aws_security_group.redshift.id]
  config_parameter {
    parameter_key   = "require_ssl"
    parameter_value = "true"
  }
  config_parameter {
    parameter_key   = "max_query_execution_time"
    parameter_value = "300"
  }
  depends_on = [aws_route_table_association.warehouse, aws_vpc_endpoint.s3, aws_iam_role_policy.redshift_copy]
}

resource "aws_redshiftserverless_usage_limit" "daily" {
  resource_arn  = aws_redshiftserverless_workgroup.warehouse.arn
  usage_type    = "serverless-compute"
  amount        = 16 # RPU-h por día; no es un límite de gasto total.
  period        = "daily"
  breach_action = "deactivate"
}

output "redshift_host" {
  value = aws_redshiftserverless_workgroup.warehouse.endpoint[0].address
}

output "redshift_database" {
  value = aws_redshiftserverless_namespace.warehouse.db_name
}

output "redshift_copy_role_arn" {
  value = aws_iam_role.redshift.arn
}
