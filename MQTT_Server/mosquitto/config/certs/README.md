# TLS Certificates for Mosquitto MQTTS (Port 8883)

Place production certificates in this directory:
- `ca.crt`: Certificate Authority public certificate
- `server.crt`: Server TLS certificate
- `server.key`: Server private key (chmod 600)

To generate self-signed testing certificates:
```bash
# 1. CA
openssl req -new -x509 -days 3650 -extensions v3_ca -keyout ca.key -out ca.crt -subj "/CN=DTV-Root-CA" -nodes

# 2. Server Key & CSR
openssl req -new -nodes -out server.csr -keyout server.key -subj "/CN=gateway.local"

# 3. Sign Server Certificate
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 365
chmod 600 server.key
```
