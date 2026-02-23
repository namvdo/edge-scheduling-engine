#!/usr/bin/env bash
set -euo pipefail

# Generates a local CA + mTLS certs for:
#- scheduler-eu, scheduler-us (servers)
# - ran-eu, ran-us (clients)
# Output: cloud/inc9/certs/out/

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/certs/out"
mkdir -p "${OUT_DIR}"

CA_KEY="${OUT_DIR}/ca.key"
CA_CRT="${OUT_DIR}/ca.crt"

if [[ ! -f "${CA_KEY}" || ! -f "${CA_CRT}" ]]; then
  echo "[certs] creating CA"
  openssl genrsa -out "${CA_KEY}" 4096
  openssl req -x509 -new -nodes -key "${CA_KEY}" -sha256 -days 3650 \
    -subj "/C=FI/O=RAN-Scheduler/OU=Inc9/CN=ran-inc9-local-ca" \
    -out "${CA_CRT}"
else
  echo "[certs] CA already exists -> ${CA_CRT}"
fi

mk_cert() {
  local NAME="$1"        #e.g. scheduler-eu
  local KIND="$2"        #server|client
  local DNS_ALT="$3"     #e.g. scheduler-eu
  local KEY="${OUT_DIR}/${NAME}.key"
  local CSR="${OUT_DIR}/${NAME}.csr"
  local CRT="${OUT_DIR}/${NAME}.crt"
  local EXT="${OUT_DIR}/${NAME}.ext"

  echo "[certs] generating ${KIND} cert: ${NAME}"
  openssl genrsa -out "${KEY}" 2048

  openssl req -new -key "${KEY}" -out "${CSR}" \
    -subj "/C=FI/O=RAN-Scheduler/OU=Inc9/CN=${NAME}"

  cat > "${EXT}" <<EOF
basicConstraints=CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = $( [[ "${KIND}" == "server" ]] && echo "serverAuth" || echo "clientAuth" )
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${DNS_ALT}
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF

  openssl x509 -req -in "${CSR}" -CA "${CA_CRT}" -CAkey "${CA_KEY}" -CAcreateserial \
    -out "${CRT}" -days 825 -sha256 -extfile "${EXT}"

  rm -f "${CSR}" "${EXT}"
}

mk_cert "scheduler-eu" server "scheduler-eu"
mk_cert "scheduler-us" server "scheduler-us"
mk_cert "ran-eu" client "ran-eu"
mk_cert "ran-us" client "ran-us"

echo "[certs] done. Files in: ${OUT_DIR}"
ls -1 "${OUT_DIR}" | sed 's/^/  - /'
