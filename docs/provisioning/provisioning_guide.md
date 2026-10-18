# Home Competition Provisioning & Identity Guide

Updated 2026-10-15 to match the implemented commissioning flow. Host tests and
builds pass; physical Android/SoftAP/ESP-NOW commissioning remains **UNVERIFIED**.

## 1. Factory prerequisites

Factory ID is `HC-{12_UPPERCASE_HEX_BASE_MAC}`. Routing uses the **STA MAC**,
which the Box reports separately. A MAC address is not authentication.

Before commissioning, an authorized manufacturing/USB process must install the
following per-device values in the `hc_factory` NVS namespace:

| Key | NVS type | Value |
|---|---|---|
| `secret` | blob | Unique 32-byte factory secret |
| `setup` | string | Unique setup code; use 12–64 ASCII characters to fit both Gateway and firmware |
| `ap_pass` | string | Unique WPA2 SoftAP password; use 12–63 ASCII characters |
| `kind` | u8 | 1 for SubBox, 2 for ActionBox |

Import the same identity into the Gateway using a private JSON file containing
`factory_id`, `product_type` (`SUB_BOX` or `ACTION_BOX`), `model`,
`factory_secret` (64 hex digits), and `setup_code`:

```bash
# From Gateway/, after initializing the data directory:
python -m gateway.core_v1 --data /path/to/hc-data import-factory /private/factory.json
```

The app does not manufacture these credentials. No default/shared key is supplied.
NVS encryption and flash protection require a separately verified production
provisioning process; compiling this firmware does not prove either is enabled.
Do not erase an existing NVS partition to add a credential or automatically burn eFuses.

SubBox additionally requires USB-installed `subbox_sec` values `ca_pem`,
`mqtt_user` and `mqtt_pass`, with a broker ACL for its assigned node ID. The
existing USB `SEC` console command requires physical presence. The broker URI
comes from the authenticated enrollment; an old USB `mqtt_uri` no longer overrides
it. Voice WebSocket trust/configuration remains a separate existing USB setup.

## 2. Physical window and Android transport

1. Hold BOOT for **3 seconds**, then release. The Box opens a **120-second**
   commissioning window. AP names are `siciot_sub_XXXXXX` or `siciot_act_XXXXXX`.
   Holding BOOT for 10 seconds resets Core enrollment; avoid doing that accidentally.
2. On Android, connect manually in Wi-Fi settings using the Box's private AP password.
3. Enter its Factory ID and setup code in the Core management flow. The native
   bridge uses Espressif Security1 with proof of possession for `hc-info`,
   `hc-config` and `hc-status` at `192.168.4.1`; no plaintext configuration fallback exists.
4. `hc-info` returns the Base MAC, STA MAC, product kind and a fresh 32-byte
   physical-window challenge. The app verifies identity and kind before continuing.

The current native commissioning bridge supports **Android only**. Gateway
management on other supported app platforms does not imply local commissioning
support. Gateway access may require switching back to the home network between
steps; complete delivery before the claim and physical window expire.

## 3. SubBox enrollment

1. Select the home and room. Provide home Wi-Fi credentials, an `mqtts://` broker
   URI, and the OTA verification public key when OTA is required.
2. While connected to Gateway, the app calls `/api/v1/nodes/claim` followed by
   `/api/v1/provisioning/prepare`. Claims require Owner/Installer authorization
   and a matching setup code, and expire after 120 seconds.
3. Gateway creates a factory-authenticated **547-byte** envelope binding the
   challenge, claim nonce, identity, logical node, room, configuration revision,
   network credentials and key material. Only one envelope is issued per claim.
4. Reconnect to the Box AP and deliver the envelope through encrypted `hc-config`.
   `STORED` means NVS persistence was acknowledged; it is **not** registration success.
5. Box reboots, joins Wi-Fi and MQTT TLS, and authenticates its fresh session to
   Gateway. Its authenticated `HCA1` receipt confirms stored enrollment and the
   Gateway handshake. Gateway validates the receipt before registering the node.
6. Gateway sends `PAIR_ACCEPT`. Box persists committed status and performs a new
   operating-session handshake. Check `/api/v1/provisioning/{claim_id}` and then
   the live snapshot; `REGISTERED` and `ONLINE` are separate conditions.

Wi-Fi storage holds up to 32 SSID bytes and 64 key bytes plus terminators. ESP-IDF
STA fields receive the complete bounded values. See the [Espressif Wi-Fi API](https://docs.espressif.com/projects/esp-idf/en/v6.0/esp32/api-reference/network/esp_wifi.html).
Physical maximum-length association still requires HIL verification.

## 4. ActionBox enrollment

1. Choose a registered SubBox in the same room. Enter its STA MAC and current
   radio channel. Read the ActionBox identity through its own physical AP window.
2. Gateway prepares an envelope without router credentials and a separate
   **110-byte** authenticated peer grant for the SubBox. The grant contains the
   ActionBox STA MAC and a unique LMK. Gateway retries pending grants via MQTT.
3. Deliver the envelope to ActionBox. After reboot, SubBox and ActionBox exchange
   authenticated peer hello packets using the configured encrypted peer.
4. ActionBox supplies an operating-key-authenticated `HCA1` receipt; SubBox supplies
   its independently authenticated `HCR1` receipt. Gateway accepts either order
   but creates the assignment and three channels only after **both** are verified.
5. Gateway confirms commitment. Channels are `HC-{BASE_MAC}:CH1`, `CH2`, `CH3`
   and initially unbound. Bind electrical Device IDs through the app separately.

No more than four active ActionBoxes are admitted per SubBox. A forged receipt,
expired claim or failed proof cannot register the Box. Receipt retries may return
the existing assignment; they must not create a second one.

## 5. Recovery and test boundary

A timeout after sending configuration has an uncertain outcome: query Gateway
before retrying. A committed Box requires the explicit physical reset flow before
replacement enrollment; a room transfer also requires an authorized Gateway
assignment. Preserve Factory ID and Device ID when testing transfers.

If commissioning expires, start a fresh claim and physical window. The current
status endpoint can still show `PAIRING` after its timestamp expires until a later
claim updates it; inspect `expires`, not only the status string. Test interrupted
room transfer/recovery separately before field use.

Run the scenarios in [the HIL plan](../testing/test_plan_and_report.md). Nothing in
the automated report proves radio pairing, physical relay operation or recovery
after power loss.
