# VPC por defecto para el entorno de laboratorio
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# AMI más reciente de Ubuntu 24.04 LTS
data "aws_ami" "ubuntu" {
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  owners = ["099720109477"] # Canonical
}

# Security Group para la instancia EC2
resource "aws_security_group" "airflow_sg" {
  name        = "${var.project_name}-ec2-sg"
  description = "Reglas de acceso para Airflow Webserver y SSH"
  vpc_id      = data.aws_vpc.default.id

  # Acceso a Airflow UI (puerto 8080)
  ingress {
    description = "Airflow Web UI"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  # Acceso SSH (puerto 22)
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  # Salida libre a Internet (para descargar feeds RSS, librerías y acceder a AWS APIs)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-ec2-sg"
  }
}

# Instancia EC2 para Apache Airflow
resource "aws_instance" "airflow_node" {
  ami                  = data.aws_ami.ubuntu.id
  instance_type        = var.instance_type
  subnet_id            = element(data.aws_subnets.default.ids, 0)
  vpc_security_group_ids = [aws_security_group.airflow_sg.id]
  iam_instance_profile = aws_iam_instance_profile.ec2_profile.name
  key_name             = var.key_name != "" ? var.key_name : null

  root_block_device {
    volume_size           = 30
    volume_type           = "gp3"
    delete_on_termination = true
  }

  # Script de inicialización para preparar el entorno de Airflow
  user_data = <<-EOF
              #!/bin/bash
              set -e
              apt-get update -y || true

              # Verificar si Docker ya se encuentra instalado en la AMI
              if ! command -v docker &> /dev/null; then
                echo "Docker no detectado. Instalando Docker y Docker Compose..."
                apt-get install -y ca-certificates curl gnupg lsb-release git unzip python3-pip
                install -m 0755 -d /etc/apt/keyrings
                curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
                chmod a+r /etc/apt/keyrings/docker.gpg
                echo \
                  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
                  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
                  tee /etc/apt/sources.list.d/docker.list > /dev/null
                apt-get update -y
                apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
              else
                echo "Docker ya está presente en el sistema. Omitiendo instalación."
              fi

              # Asegurar que el servicio de Docker esté iniciado y habilitado
              systemctl enable docker || true
              systemctl start docker || true

              # Configurar usuario ubuntu para usar docker sin sudo
              usermod -aG docker ubuntu || true

              # Crear directorio de trabajo para Airflow
              mkdir -p /home/ubuntu/airflow_app
              chown -R ubuntu:ubuntu /home/ubuntu/airflow_app

              # Guardar variables de entorno para que el pipeline las consuma
              cat << 'ENVFILE' > /home/ubuntu/airflow_app/.env
              DATALAKE_BUCKET=${aws_s3_bucket.datalake.bucket}
              AWS_DEFAULT_REGION=${var.aws_region}
              GLUE_DATABASE=rss_datalake_db
              ATHENA_WORKGROUP=${aws_athena_workgroup.datalake_workgroup.name}
              AIRFLOW_UID=50000
              ENVFILE
              chown ubuntu:ubuntu /home/ubuntu/airflow_app/.env

              echo "Setup completed successfully" > /var/log/user_data_status.log
              EOF

  tags = {
    Name = "${var.project_name}-airflow-ec2"
  }
}
