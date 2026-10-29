data "aws_ami" "runner" {
  owners = ["amazon"]
  filter {
    name   = "image-id"
    values = [var.runner_ami_id]
  }
}

resource "aws_key_pair" "runner" {
  key_name   = "${var.project_name}-runner"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

resource "aws_instance" "runner" {
  ami                         = data.aws_ami.runner.id
  instance_type               = "t3.medium"
  subnet_id                   = aws_subnet.runner.id
  vpc_security_group_ids      = [aws_security_group.runner.id]
  associate_public_ip_address = true
  key_name                    = aws_key_pair.runner.key_name
  iam_instance_profile        = aws_iam_instance_profile.runner.name
  user_data                   = file("${path.module}/templates/bootstrap.sh")
  user_data_replace_on_change = true

  # IMDSv2 obligatorio; hop=2 permite obtener el rol desde la red Docker.
  # Sin credenciales estáticas en la instancia ni en los contenedores.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 30
    encrypted             = true
    delete_on_termination = true
  }

  # Evita cargos de créditos de CPU excedentes en esta instancia EC2.
  credit_specification {
    cpu_credits = "standard"
  }

  depends_on = [
    aws_route.internet,
    aws_route_table_association.runner,
    aws_vpc_security_group_egress_rule.https,
  ]
  tags = { Name = "${var.project_name}-runner" }
}
