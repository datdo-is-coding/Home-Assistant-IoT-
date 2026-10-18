# Home Competition Core V1 Deployment Guide

## 1. System Requirements

- **Gateway Hardware:** Raspberry Pi 4 Model B (4GB RAM minimum).
- **Operating System:** Ubuntu Server 24.04 LTS (CLI / 64-bit arm64).
- **Dependencies:** Python 3.12+, Mosquitto MQTT Broker 2.x, SQLite 3.40+.

---

## 2. Gateway Service Installation

### 2.1. Clone Repository & Setup Virtualenv
```bash
sudo mkdir -p /opt/home-competition /var/lib/home-competition /etc/home-competition
sudo useradd -r -s /bin/false homecompetition
sudo chown -R homecompetition:homecompetition /var/lib/home-competition

cd /opt/home-competition
sudo cp -r /path/to/Home-Assistant-IoT-/* .
python3 -m venv .venv
./.venv/bin/pip install -r Gateway/requirements-core.txt
```

### 2.2. Service Configuration
Copy configuration files:
```bash
sudo cp deployment/systemd/home-competition-core.service /etc/systemd/system/
sudo cp deployment/config_examples/core.env.example /etc/home-competition/core.env
sudo chmod 600 /etc/home-competition/core.env
sudo chown -R homecompetition:homecompetition /etc/home-competition
```

Edit `/etc/home-competition/core.env` with unique secure passwords and certificate paths.

Initialize the database and owner account **once**, before starting the service:

```bash
cd /opt/home-competition/Gateway
sudo -u homecompetition /opt/home-competition/.venv/bin/python \
  -m gateway.core_v1 --data /var/lib/home-competition init \
  --name Owner --home 'Home Competition'
```

The CLI writes the bearer token to the private file
`/var/lib/home-competition/owner-token.txt`. Transfer it securely to the app;
do not paste it into logs or URLs. `init` refuses to overwrite existing identity
or ownership. Import per-device factory identities before commissioning; see the
[provisioning guide](../provisioning/provisioning_guide.md).

The supplied service binds **127.0.0.1:8081**. For app access, configure an HTTPS
reverse proxy that forwards `Authorization` and WebSocket upgrades, or explicitly
configure a non-loopback `serve --host` listener with `HC_TLS_CERT` and
`HC_TLS_KEY`. Setting `HC_PUBLIC_ORIGIN` alone does not expose the listener or
enable TLS. Configure the MQTT broker and referenced certificates before activation.

### 2.3. Systemd Service Activation
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now home-competition-core.service
sudo systemctl status home-competition-core.service
```

---

## 3. Mosquitto MQTT Configuration

1. Copy Mosquitto configuration:
   ```bash
   sudo cp deployment/config_examples/mosquitto-hc.conf /etc/mosquitto/conf.d/
   sudo cp deployment/config_examples/hc-acl.example /etc/mosquitto/hc-acl
   ```
2. Generate TLS certificates for Gateway and SubBox mutual authentication.
3. Restart Mosquitto:
   ```bash
   sudo systemctl restart mosquitto
   ```

---

## 4. Firmware Build and Flash Instructions

### 4.1. Prerequisites
Ensure ESP-IDF v6.0.2 is loaded:
```bash
source /path/to/esp-idf/export.sh
```

### 4.2. SubBox
```bash
cd Firmware/firmware_esp/SubBox
idf.py set-target esp32s3
idf.py build
idf.py -p /dev/ttyACM0 flash
```

### 4.3. ActionBox_V2
```bash
cd Firmware/firmware_esp/ActionBox_V2
idf.py set-target esp32s3
idf.py build
idf.py -p /dev/ttyACM0 flash
```

---

## 5. Flutter App Execution

```bash
cd App/dtv_energy_flutter
flutter pub get
flutter run -d <device_id>
```

Secure local Box commissioning currently requires Android. A fresh host build
and test report is available at [test_plan_and_report.md](../testing/test_plan_and_report.md);
physical provisioning and OTA acceptance still require its HIL scenarios.
