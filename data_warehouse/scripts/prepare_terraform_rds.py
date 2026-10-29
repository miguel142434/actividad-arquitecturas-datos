#!/usr/bin/env python3
"""Prepara variables sin secretos: cuenta y SSH desde cualquier IPv4 con clave."""

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "infra/terraform/terraform.tfvars.json"
KEY = Path.home() / ".ssh/id_ed25519.pub"


def main():
    if TARGET.exists() or TARGET.with_name("terraform.tfvars").exists():
        raise SystemExit("Ya hay variables locales. Revisarlas manualmente; no se sobrescribieron.")
    if not KEY.is_file():
        raise SystemExit("Falta ~/.ssh/id_ed25519.pub, la clave pública elegida para este proyecto.")
    account = subprocess.check_output([
        "aws", "sts", "get-caller-identity", "--profile", "default", "--region", "us-east-1",
        "--query", "Account", "--output", "text", "--no-cli-pager",
    ], text=True).strip()
    if len(account) != 12 or not account.isdigit():
        raise SystemExit("No se pudo validar la cuenta del perfil default.")
    values = {"aws_account_id": account, "ssh_allowed_cidr": "0.0.0.0/0", "ssh_public_key_path": str(KEY)}
    with TARGET.open("x", encoding="utf-8") as handle:
        json.dump(values, handle, indent=2)
        handle.write("\n")
    TARGET.chmod(0o600)
    print("Creado infra/terraform/terraform.tfvars.json con cuenta, SSH desde cualquier IPv4 y ruta de clave pública; sin contraseñas.")


if __name__ == "__main__":
    main()
