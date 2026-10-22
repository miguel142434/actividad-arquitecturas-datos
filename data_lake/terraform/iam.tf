# Rol IAM asumible por la instancia EC2
resource "aws_iam_role" "ec2_airflow_role" {
  name = "${var.project_name}-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

# Política con los permisos necesarios para el pipeline: S3, Comprehend, Glue y Athena
resource "aws_iam_policy" "airflow_pipeline_policy" {
  name        = "${var.project_name}-pipeline-policy"
  description = "Permisos necesarios para Airflow: S3, Comprehend, Glue y Athena sin secretos expuestos"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3DataLakeAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:DeleteObject",
          "s3:GetBucketLocation",
          "s3:ListBucketMultipartUploads",
          "s3:ListMultipartUploadParts",
          "s3:AbortMultipartUpload"
        ]
        Resource = [
          aws_s3_bucket.datalake.arn,
          "${aws_s3_bucket.datalake.arn}/*"
        ]
      },
      {
        Sid    = "ComprehendAccess"
        Effect = "Allow"
        Action = [
          "comprehend:DetectEntities",
          "comprehend:DetectKeyPhrases",
          "comprehend:DetectDominantLanguage"
        ]
        Resource = "*"
      },
      {
        Sid    = "GlueCatalogAccess"
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetDatabases",
          "glue:CreateTable",
          "glue:UpdateTable",
          "glue:DeleteTable",
          "glue:GetTable",
          "glue:GetTables",
          "glue:GetPartition",
          "glue:GetPartitions",
          "glue:CreatePartition",
          "glue:BatchCreatePartition",
          "glue:BatchDeletePartition"
        ]
        Resource = "*"
      },
      {
        Sid    = "AthenaAccess"
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:StopQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:GetWorkGroup",
          "athena:GetDataCatalog",
          "athena:GetDatabase"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "airflow_attach" {
  role       = aws_iam_role.ec2_airflow_role.name
  policy_arn = aws_iam_policy.airflow_pipeline_policy.arn
}

# Para poder conectarse por AWS Systems Manager (SSM) en caso de que no se use SSH
resource "aws_iam_role_policy_attachment" "ssm_attach" {
  role       = aws_iam_role.ec2_airflow_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Instance profile para asociar el rol a la instancia EC2
resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${var.project_name}-instance-profile"
  role = aws_iam_role.ec2_airflow_role.name
}
