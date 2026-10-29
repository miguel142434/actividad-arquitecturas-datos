# Activar únicamente después de revisar costos, suscripción e IAM con el usuario.
variable "enable_quicksight" {
  description = "Habilita la conexión privada y los permisos propuestos de 3.6; false no crea recursos."
  type        = bool
  default     = false
}

resource "aws_security_group" "quicksight" {
  count       = var.enable_quicksight ? 1 : 0
  name        = "${var.project_name}-quicksight"
  description = "QuickSight privado hacia Redshift TCP 5439"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_egress_rule" "quicksight_redshift" {
  count                        = var.enable_quicksight ? 1 : 0
  security_group_id            = aws_security_group.quicksight[0].id
  referenced_security_group_id = aws_security_group.redshift.id
  ip_protocol                  = "tcp"
  from_port                    = 5439
  to_port                      = 5439
}

resource "aws_vpc_security_group_ingress_rule" "redshift_quicksight" {
  count                        = var.enable_quicksight ? 1 : 0
  security_group_id            = aws_security_group.redshift.id
  referenced_security_group_id = aws_security_group.quicksight[0].id
  ip_protocol                  = "tcp"
  from_port                    = 5439
  to_port                      = 5439
}

resource "aws_iam_role" "quicksight_vpc" {
  count = var.enable_quicksight ? 1 : 0
  name  = "${var.project_name}-quicksight-vpc"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "quicksight.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = var.aws_account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "quicksight_vpc" {
  count = var.enable_quicksight ? 1 : 0
  name  = "manage-quicksight-network-interfaces"
  role  = aws_iam_role.quicksight_vpc[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups", "ec2:CreateNetworkInterface",
        "ec2:ModifyNetworkInterfaceAttribute", "ec2:DeleteNetworkInterface"
      ]
      Resource = "*"
    }]
  })
}

resource "aws_quicksight_vpc_connection" "warehouse" {
  count              = var.enable_quicksight ? 1 : 0
  aws_account_id     = var.aws_account_id
  vpc_connection_id  = "${var.project_name}-warehouse"
  name               = "${var.project_name}-warehouse"
  role_arn           = aws_iam_role.quicksight_vpc[0].arn
  subnet_ids         = [for subnet in aws_subnet.database : subnet.id]
  security_group_ids = [aws_security_group.quicksight[0].id]
  depends_on = [
    aws_iam_role_policy.quicksight_vpc,
    aws_vpc_security_group_egress_rule.quicksight_redshift,
    aws_vpc_security_group_ingress_rule.redshift_quicksight
  ]
}

resource "aws_iam_role_policy" "runner_quicksight_refresh" {
  count = var.enable_quicksight ? 1 : 0
  name  = "refresh-sales-spice"
  role  = aws_iam_role.runner.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["quicksight:CreateIngestion", "quicksight:DescribeIngestion"]
      Resource = [
        "arn:aws:quicksight:us-east-1:${var.aws_account_id}:dataset/${var.project_name}-sales",
        "arn:aws:quicksight:us-east-1:${var.aws_account_id}:dataset/${var.project_name}-sales/ingestion/*"
      ]
    }]
  })
}

output "quicksight_vpc_connection_arn" {
  value = var.enable_quicksight ? aws_quicksight_vpc_connection.warehouse[0].arn : null
}
