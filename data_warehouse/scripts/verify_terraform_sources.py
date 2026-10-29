#!/usr/bin/env python3
"""Plan diagnóstico de solo lectura; borra el plan y nunca ejecuta apply."""

import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1] / "infra/terraform"
PASSWORD_NAMES = ("rds_master_password", "documentdb_master_password", "redshift_master_password")


def require(condition, message):
    if not condition:
        raise SystemExit(f"Diagnóstico no aprobado: {message}")


def inspect_plan(raw, passwords):
    require(all(value.encode() not in raw for value in passwords), "secreto en el JSON del plan")
    data = json.loads(raw)
    require(not any(name in data["variables"] for name in PASSWORD_NAMES), "variable efímera persistida")
    changes = data["resource_changes"]
    require(all(item["change"]["actions"] in (["create"], ["read"]) for item in changes),
            "se esperaban únicamente altas/lecturas en esta preparación")
    resources = {item["address"]: item["change"]["after"] for item in changes}
    cluster = resources["aws_docdb_cluster.sources"]
    require(cluster["master_password_wo"] is None and cluster.get("master_password") is None,
            "contraseña DocumentDB persistida")
    require(cluster["storage_encrypted"] and cluster["skip_final_snapshot"]
            and not cluster["deletion_protection"], "cifrado/eliminación DocumentDB")
    require(cluster["engine_version"] == "5.0.0" and cluster["backup_retention_period"] == 1,
            "motor/respaldo DocumentDB")
    mysql = resources["aws_db_instance.mysql"]
    require(mysql["password_wo"] is None and not mysql["publicly_accessible"], "secreto/privacidad RDS")
    ssh = resources["aws_vpc_security_group_ingress_rule.ssh"]
    require(ssh["cidr_ipv4"] == "0.0.0.0/0" and ssh["ip_protocol"] == "tcp"
            and ssh["from_port"] == ssh["to_port"] == 22, "SSH global solo TCP 22")
    rule = resources["aws_vpc_security_group_ingress_rule.documentdb"]
    require(rule["from_port"] == rule["to_port"] == 27017 and rule["ip_protocol"] == "tcp"
            and rule.get("cidr_ipv4") is None and rule.get("cidr_ipv6") is None,
            "puerto/regla privada DocumentDB")
    require(resources["aws_docdb_cluster_parameter_group.sources"]["parameter"] == [
        {"apply_method": "pending-reboot", "name": "tls", "value": "enabled"}], "TLS obligatorio")
    config = {item["address"]: item for item in data["configuration"]["root_module"]["resources"]}
    references = config["aws_vpc_security_group_ingress_rule.documentdb"]["expressions"][
        "referenced_security_group_id"]["references"]
    require("aws_security_group.runner.id" in references, "origen exclusivo SG EC2")
    references = config["aws_vpc_security_group_egress_rule.documentdb"]["expressions"][
        "referenced_security_group_id"]["references"]
    require("aws_security_group.documentdb.id" in references, "salida EC2 al SG DocumentDB")
    if "aws_redshiftserverless_namespace.warehouse" in resources:
        namespace = resources["aws_redshiftserverless_namespace.warehouse"]
        require(namespace["admin_user_password_wo"] is None and namespace.get("admin_user_password") is None,
                "secreto Redshift persistido")
        workgroup = resources["aws_redshiftserverless_workgroup.warehouse"]
        require(not workgroup["publicly_accessible"] and workgroup["enhanced_vpc_routing"],
                "Redshift debe ser privado y con EVR")
        require(workgroup["base_capacity"] == workgroup["max_capacity"] == 4, "capacidad Redshift")
        require(any(item["parameter_key"] == "require_ssl" and item["parameter_value"] == "true"
                    for item in workgroup["config_parameter"]), "TLS Redshift")
        limit = resources["aws_redshiftserverless_usage_limit.daily"]
        require(limit["amount"] == 16 and limit["period"] == "daily" and limit["breach_action"] == "deactivate",
                "límite diario Redshift")
    return sum(item["change"]["actions"] == ["create"] for item in changes)


def main():
    env = os.environ.copy()
    passwords = ["Aa1_" + secrets.token_urlsafe(24) for _ in PASSWORD_NAMES]
    for name, value in zip(PASSWORD_NAMES, passwords):
        env[f"TF_VAR_{name}"] = value
    for name in list(env):
        if name.startswith("TF_LOG"):
            env.pop(name)
    env["AWS_REGION"] = env["AWS_DEFAULT_REGION"] = "us-east-1"
    old_mask = os.umask(0o077)
    try:
        with tempfile.TemporaryDirectory(prefix="taller4-diagnostic-") as directory:
            plan = Path(directory) / "diagnostic.tfplan"
            result = subprocess.run(
                ["terraform", f"-chdir={ROOT}", "plan", "-input=false", "-no-color", f"-out={plan}"],
                env=env, capture_output=True, text=True)
            if result.returncode:
                output = result.stderr
                for value in passwords:
                    output = output.replace(value, "<redacted>")
                print(output)
                raise SystemExit(result.returncode)
            raw = subprocess.check_output(
                ["terraform", f"-chdir={ROOT}", "show", "-json", str(plan)], env=env)
            count = inspect_plan(raw, passwords)
    finally:
        os.umask(old_mask)
    print(f"Diagnóstico: {count} altas, sin cambios ni eliminaciones.")
    print("Comprobados: secretos efímeros ausentes del JSON; write-only nulos; RDS privado; "
          "SSH global solo TCP 22; DocumentDB cifrado, TLS obligatorio, respaldo 1 día, "
          "sin snapshot final y SG exclusivo EC2 con salida correspondiente.")
    print("Redshift: contraseña write-only nula, privado, EVR, TLS, base/máximo 4 RPU y límite diario 16 RPU-h.")
    print("Plan temporal eliminado. No reutilizable para despliegue.")


if __name__ == "__main__":
    main()
