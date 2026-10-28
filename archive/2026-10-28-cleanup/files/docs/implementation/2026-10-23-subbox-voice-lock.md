# SubBox audio send/receive contention

Observed before change: Gateway saw START followed by abnormal WebSocket disconnect before STOP/ASR on three attempts. A later live serial trace recorded `Could not lock ws-client within 100 timeout` while uploading a new utterance and receiving an earlier reply. Other attempts completed, including the inventory query. These observations do not prove every disconnect has the same cause.

Root cause confirmed in code and host regression: start/feedAudio/stop held WsASR receive-state mutex while sending over WebSocket. The WebSocket receive callback holds its client lock and needs the same application mutex for transcript/result delivery. The host test compiled actual ws_asr.cpp and demonstrated receive-state access blocked during sends before the fix.

Change: serialize outgoing PCM/state resets with a separate send mutex; release receive-state mutex before network sends. Enable ESP WebSocket separate TX lock, so speaker playback in receive callbacks does not serialize outgoing audio. Downgrade repeated per-channel telemetry registration logs to DEBUG.

Validation: regression failed before, passed after; real AudioManager PCM relay host test passed. ESP-IDF SubBox build succeeded. App-only flash at 0x20000 verified data hash; Wi-Fi/registration/security NVS preserved. Pi observed SubBox speaker reconnect. Firmware SHA256: 2094588d074417bbc11333cf767cfd6c8b0a5cae62e2f20a4b9380db1c1bbecc.

Pending: three spoken inventory queries on hardware, including operation without serial monitor. Not a claim that Wi-Fi interruptions or every voice issue are fixed. Existing room/name/type ambiguity in device control remains a separate issue.
