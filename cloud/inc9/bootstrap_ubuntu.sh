#!/usr/bin/env bash
set -euo pipefail

# Inc9 cloud bootstrap helper for Ubuntu/Debian VMs.
#
# Usage (on a fresh VM):
#   git clone <repo>
#   cd <repo>/cloud/inc9
#   REGION=eu bash bootstrap_ubuntu.sh
#
# This installs Docker + Compose plugin + OpenSSL (if missing),
# generates mTLS certs, and starts the single-region stack.

REGION="${REGION:-eu}"

have() { command -v "$1" >/dev/null 2>&1; }

if ! have docker; then
  echo "[bootstrap] installing docker..."
  sudo apt-get update
  sudo apt-get install -y docker.io
  sudo systemctl enable --now docker
fi

#docker compose plugin
if ! docker compose version >/dev/null 2>&1; then
  echo "[bootstrap] installing docker compose plugin..."
  sudo apt-get update
  sudo apt-get install -y docker-compose-plugin
fi

if ! have openssl; then
  echo "[bootstrap] installing openssl..."
  sudo apt-get update
  sudo apt-get install -y openssl
fi

echo "[bootstrap] generating certs"
bash certs/generate_certs.sh

mkdir -p out

echo "[bootstrap] starting single-region stack (REGION=${REGION})"
REGION="${REGION}" docker compose -f docker-compose.single-region.yml up -d --build

echo "[bootstrap] done"
docker compose -f docker-compose.single-region.yml ps
