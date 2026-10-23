#!/usr/bin/env bash
set -e

CERTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$CERTS_DIR"

if [ -f "ca.crt" ] && [ -f "server.crt" ] && [ -f "server.key" ]; then
    echo "Certificates already exist in $CERTS_DIR"
    chmod 644 ca.crt server.crt server.key
    exit 0
fi

echo "Generating self-signed TLS certificates for Mosquitto..."

# 1. Generate CA key and certificate
openssl req -new -x509 -days 3650 -extensions v3_ca \
    -keyout ca.key -out ca.crt \
    -subj "/CN=DTV-Root-CA" -nodes

# 2. Generate Server key and CSR
openssl req -new -nodes \
    -out server.csr -keyout server.key \
    -subj "/CN=gateway.local"

# 3. Sign Server certificate with CA
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out server.crt -days 365

chmod 644 ca.crt server.crt server.key

echo "Certificates generated successfully in $CERTS_DIR."
