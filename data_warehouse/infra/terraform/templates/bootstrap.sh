#!/usr/bin/env bash
set -euo pipefail
umask 027

# Aplicar antes de instalar paquetes: solo ec2-user y autenticación con clave.
install -d -m 0755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/00-de-dw-aws.conf <<'SSH_CONFIG'
PubkeyAuthentication yes
AuthenticationMethods publickey
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PermitRootLogin no
AllowUsers ec2-user
SSH_CONFIG
chmod 0600 /etc/ssh/sshd_config.d/00-de-dw-aws.conf
# OpenSSH usa el primer valor: cargar nuestra configuración al inicio.
sed -i '\|^Include /etc/ssh/sshd_config.d/00-de-dw-aws.conf$|d' /etc/ssh/sshd_config
sed -i '1i Include /etc/ssh/sshd_config.d/00-de-dw-aws.conf' /etc/ssh/sshd_config
/usr/sbin/sshd -t
ssh_effective=$(/usr/sbin/sshd -T -C user=ec2-user,host=localhost,addr=127.0.0.1)
for setting in 'pubkeyauthentication yes' 'authenticationmethods publickey' \
  'passwordauthentication no' 'kbdinteractiveauthentication no' \
  'permitemptypasswords no' 'permitrootlogin no' 'allowusers ec2-user'; do
  if ! grep -Fxq "$setting" <<< "$ssh_effective"; then
    echo "Configuración SSH inesperada: $setting" >&2
    exit 1
  fi
done
systemctl reload sshd

dnf install -y python3.11 python3.11-pip docker
# Instalación futura en EC2; versión fija de Compose y checksum oficial.
compose_version=v2.40.3
compose_asset=docker-compose-linux-x86_64
compose_tmp=$(mktemp -d)
trap 'rm -rf "$compose_tmp"' EXIT
for asset in "$compose_asset" checksums.txt; do
  curl --fail --silent --show-error --location --retry 3 \
    "https://github.com/docker/compose/releases/download/$compose_version/$asset" \
    -o "$compose_tmp/$asset"
done
(
  cd "$compose_tmp"
  awk -v asset="$compose_asset" '$2 == asset || $2 == "*" asset { print; found=1 } END { if (!found) exit 1 }' \
    checksums.txt > selected.sha256
  sha256sum --check selected.sha256
)
install -d -m 0755 /usr/local/lib/docker/cli-plugins
install -m 0755 "$compose_tmp/$compose_asset" /usr/local/lib/docker/cli-plugins/docker-compose
systemctl enable --now docker
usermod -aG docker ec2-user
install -d -m 0750 -o ec2-user -g ec2-user /opt/de-dw-aws
install -d -m 0750 -o ec2-user -g ec2-user /opt/de-dw-aws/certs
sudo -u ec2-user python3.11 -m venv /opt/de-dw-aws/.venv
curl --fail --silent --show-error --location --retry 3 \
  https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
  -o /opt/de-dw-aws/certs/global-bundle.pem
chown ec2-user:ec2-user /opt/de-dw-aws/certs/global-bundle.pem
chmod 0640 /opt/de-dw-aws/certs/global-bundle.pem
# Docker queda preparado; no se arranca Airflow ni se carga código/datos.
# Sin credenciales de las bases o de AWS en user_data.
