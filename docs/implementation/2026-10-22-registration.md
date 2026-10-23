# Complete registration on the deployed protocol-3 stack

Keep ActionBox V2 → SubBox → authenticated TLS MQTT → Gateway → Android.
Physical setup on both boards expires after 180 seconds. A heartbeat is discovery,
not ownership. Advertise a canonical MAC-derived ID and setup session. Only the
SubBox that heard the device may dispatch its claim. Persist the ActionBox user
configuration before its ACK; persist the SubBox enrollment before forwarding
success. Repeated identical requests recover a lost ACK without actuating relays.
Do not alter calibration, secure hc_core peers, or reset existing boards.

Scope: firmware discovery/claim/persistence/restart, Gateway candidate routing,
strict correlated ACK and failed dispatch, Android error/retry guidance. Existing
protocol-3 radio is unencrypted: keep it separate from encrypted peers; do not
claim commercial radio authentication. Secure hc_core provisioning remains intact.

Verification: failing host/API regressions, firmware build, Gateway and app tests,
then hardware commissioning/reboot when boards and physical interaction are
available. Never report success from MQTT enqueue or discovery alone.
