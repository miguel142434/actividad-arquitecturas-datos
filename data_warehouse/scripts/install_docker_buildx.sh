#!/usr/bin/env bash
# Preparación de la EC2: solo plugin CLI; no inicia contenedores ni cargas.
set -euo pipefail

[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || {
  printf 'Este instalador corresponde a la EC2 Linux x86_64 del proyecto.\n' >&2
  exit 1
}
command -v docker >/dev/null
buildx_version=v0.29.1
buildx_asset="buildx-${buildx_version}.linux-amd64"
# SHA-256 del checksums.txt oficial de la release, consultado el 25-10-2026.
buildx_sha256=7d2d7d6d4680aa349614965aaa33ccec43f1a9a21e908a5ce4cb6adfa5ad5141
buildx_directory="${DOCKER_CONFIG:-$HOME/.docker}/cli-plugins"
buildx_temporary=$(mktemp -d)
trap 'rm -rf "$buildx_temporary"' EXIT
curl --fail --silent --show-error --location --retry 3 \
  "https://github.com/docker/buildx/releases/download/${buildx_version}/${buildx_asset}" \
  -o "$buildx_temporary/$buildx_asset"
(
  cd "$buildx_temporary"
  printf '%s  %s\n' "$buildx_sha256" "$buildx_asset" | sha256sum --check -
)
install -d -m 0755 "$buildx_directory"
install -m 0755 "$buildx_temporary/$buildx_asset" "$buildx_directory/docker-buildx"
docker buildx version
