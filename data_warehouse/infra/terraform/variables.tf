variable "aws_profile" {
  description = "Perfil local para desplegar; nunca incluir claves AWS en Terraform."
  type        = string
  default     = "default"
}

variable "aws_account_id" {
  description = "Cuenta esperada: evita desplegar accidentalmente en otra cuenta."
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "Se requiere el identificador de cuenta AWS de 12 dígitos."
  }
}

variable "project_name" {
  type        = string
  description = "Prefijo exclusivo de recursos de este laboratorio."
  default     = "de-dw-aws"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,29}[a-z0-9]$", var.project_name)) && !strcontains(var.project_name, "--")
    error_message = "Usar 4 a 31 caracteres: letras minúsculas, números y guiones simples."
  }
}

variable "ssh_allowed_cidr" {
  description = "Origen IPv4 de SSH: /32 para una IP o 0.0.0.0/0 para este laboratorio con claves."
  type        = string
  validation {
    condition     = can(cidrnetmask(var.ssh_allowed_cidr)) && (endswith(var.ssh_allowed_cidr, "/32") || var.ssh_allowed_cidr == "0.0.0.0/0")
    error_message = "Usar una dirección IPv4 /32 o 0.0.0.0/0 para SSH con claves en el laboratorio."
  }
}

variable "ssh_public_key_path" {
  description = "Ruta a la clave PÚBLICA; no se carga ni copia la clave privada."
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
  validation {
    condition     = endswith(var.ssh_public_key_path, ".pub") && fileexists(pathexpand(var.ssh_public_key_path))
    error_message = "Indicar un archivo .pub existente. Nunca usar la clave privada."
  }
}

variable "runner_ami_id" {
  description = "AMI Amazon Linux 2023 x86_64 fijada y comprobada en us-east-1."
  type        = string
  default     = "ami-0d6e34c14757a048b"
}

variable "rds_engine_version" {
  description = "MySQL 8.4, como en DE-DW; versión regional comprobada."
  type        = string
  default     = "8.4.11"
  validation {
    condition     = startswith(var.rds_engine_version, "8.4.")
    error_message = "Esta configuración usa la familia mysql8.4."
  }
}

variable "rds_master_password" {
  description = "Contraseña temporal de entrada: no se guarda en plan ni estado. Guardarla en un gestor personal."
  type        = string
  sensitive   = true
  ephemeral   = true
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{16,64}$", var.rds_master_password))
    error_message = "Usar entre 16 y 64 letras, números, guiones o guiones bajos."
  }
}

variable "rds_password_version" {
  description = "Incrementar solo al cambiar intencionadamente la contraseña de RDS."
  type        = number
  default     = 1
  validation {
    condition     = var.rds_password_version >= 1 && floor(var.rds_password_version) == var.rds_password_version
    error_message = "La versión de contraseña debe ser un entero positivo."
  }
}

variable "documentdb_master_password" {
  description = "Entrada efímera de DocumentDB: no guardar en código, plan ni estado."
  type        = string
  sensitive   = true
  ephemeral   = true
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{16,64}$", var.documentdb_master_password))
    error_message = "Usar entre 16 y 64 letras, números, guiones o guiones bajos."
  }
}

variable "documentdb_password_version" {
  description = "Incrementar solo al rotar intencionadamente la contraseña de DocumentDB."
  type        = number
  default     = 1
  validation {
    condition     = var.documentdb_password_version >= 1 && floor(var.documentdb_password_version) == var.documentdb_password_version
    error_message = "La versión de contraseña debe ser un entero positivo."
  }
}

variable "redshift_master_password" {
  description = "Contraseña efímera Redshift; no guardar en plan/estado ni archivos de variables."
  type        = string
  sensitive   = true
  ephemeral   = true
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{16,64}$", var.redshift_master_password)) && can(regex("[A-Z]", var.redshift_master_password)) && can(regex("[a-z]", var.redshift_master_password)) && can(regex("[0-9]", var.redshift_master_password))
    error_message = "Usar 16–64 letras/números/guiones; incluir mayúscula, minúscula y número."
  }
}

variable "redshift_password_version" {
  type        = number
  default     = 1
  description = "Incrementar solo al rotar intencionalmente la contraseña Redshift."
  validation {
    condition     = var.redshift_password_version >= 1 && floor(var.redshift_password_version) == var.redshift_password_version
    error_message = "Usar un entero positivo."
  }
}
