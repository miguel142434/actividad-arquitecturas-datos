#!/usr/bin/env python3
"""Ejecuta Terraform con contraseñas efímeras, introducida sin eco ni historial."""

import getpass
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("plan", "apply", "destroy"):
        raise SystemExit("Uso: python3 scripts/terraform_rds.py {plan|apply|destroy} [argumentos Terraform]")
    names = (("rds_master_password", "RDS"), ("documentdb_master_password", "DocumentDB"), ("redshift_master_password", "Redshift"))
    env = os.environ.copy()
    for variable, label in names:
        key = f"TF_VAR_{variable}"
        if not sys.stdin.isatty() and not env.get(key):
            raise SystemExit("Ejecutar desde una terminal interactiva para introducir las tres contraseñas sin eco.")
        password = env.get(key) or getpass.getpass(f"Contraseña {label} (guardada por ti; no se mostrará): ")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", password):
            raise SystemExit(f"{label}: usar de 16 a 64 letras, números, guiones o guiones bajos.")
        if variable == "redshift_master_password" and not all(re.search(pattern, password) for pattern in (r"[A-Z]", r"[a-z]", r"[0-9]")):
            raise SystemExit("Redshift: incluir mayúscula, minúscula y número.")
        env[key] = password
    env["AWS_REGION"] = "us-east-1"
    env["AWS_DEFAULT_REGION"] = "us-east-1"
    for key in list(env):
        if key.startswith("TF_LOG"):
            env.pop(key)
    old_mask = os.umask(0o077)
    try:
        result = subprocess.run(["terraform", f"-chdir={ROOT / 'infra/terraform'}", *sys.argv[1:]], env=env)
    finally:
        os.umask(old_mask)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
