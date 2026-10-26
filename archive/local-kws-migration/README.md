# Archive — local KWS migration (2026-10-25)

This directory preserves files removed from the active SubBox/ActionBox_V2 builds when
Vietnamese KWS recognition moved to SubBox. Paths below are the original repository
paths. The archived copies are not compiled and must not be used as a second source of
truth while `common/kws` and `SubBox/src/audio/kws` are active.

## Archived files

| Original path | Reason archived | Replacement / active owner |
| --- | --- | --- |
| `Firmware/firmware_esp/ActionBox_V2/src/audio/kws/kws_config.h` | ActionBox_V2 no longer runs the KWS model, MFCC, or sentence command path. It only detects `Hi ESP` with WakeNet and streams PCM. | `Firmware/firmware_esp/common/kws/kws_config.h` (shared model/MFCC configuration) |
| `Firmware/firmware_esp/ActionBox_V2/src/audio/kws/kws_engine.cpp` | ActionBox-side KWS inference was removed; inference now runs in the SubBox audio-manager task. | `Firmware/firmware_esp/SubBox/src/audio/kws/local_kws.cpp` |
| `Firmware/firmware_esp/ActionBox_V2/src/audio/kws/kws_engine.h` | Removed with the ActionBox KWS engine. | `Firmware/firmware_esp/SubBox/src/audio/kws/local_kws.h` |
| `Firmware/firmware_esp/ActionBox_V2/src/audio/kws/kws_mfcc.cpp` | MFCC moved to the shared firmware component so ActionBox_V2 and SubBox do not build duplicate implementations. | `Firmware/firmware_esp/common/kws/kws_mfcc.cpp` |
| `Firmware/firmware_esp/ActionBox_V2/src/audio/kws/kws_mfcc.h` | Moved with the shared MFCC implementation. | `Firmware/firmware_esp/common/kws/kws_mfcc.h` |
| `Firmware/firmware_esp/ActionBox_V2/src/audio/kws/kws_model_quantized.h` | Shared INT8 model weights moved out of ActionBox_V2. | `Firmware/firmware_esp/common/kws/kws_model_quantized.h` |
| `Firmware/firmware_esp/SubBox/src/network/espnow_receiver.cpp` | Obsolete duplicate receiver. The active `EspNowAudioTransport` owns ESP-NOW receive, ACK correlation, peer registration, and the receive queue. Keeping a second receiver risked split ownership of packets. | `Firmware/firmware_esp/SubBox/src/audio/audio_transport/espnow_audio_transport.cpp` |
| `Firmware/firmware_esp/SubBox/src/network/espnow_receiver.h` | Header for the obsolete receiver above. No active source includes it. | Same as above |

## Verification performed

- `rg "audio/kws|espnow_receiver"` over active SubBox and ActionBox_V2 sources and CMake
  files shows only the intended `SubBox/src/audio/kws` adapter and shared `common/kws`
  paths. No active file includes `network/espnow_receiver.h`.
- `Firmware/tests/test_kws_parity.py` asserts that
  `ActionBox_V2/src/audio/kws` does not exist and that ActionBox_V2 sources do not
  reference `kws_engine` or `kws_run_inference_quantized`.
- SubBox and ActionBox_V2 ESP-IDF 6.0.2 builds pass with the archived files absent.

## Not archived

- `Firmware/firmware_esp/ActionBox` (the older, non-V2 tree) still contains
  `MSG_TYPE_KEYWORD_EVENT` and `ActionBoxKeywordEventPacket`. That tree is not part of
  the active ActionBox_V2/SubBox build and was left untouched to avoid deleting
  unrelated legacy work. It is not an active KWS path.
- The model, MFCC, and KWS configuration remain functional code in `common/kws`; they
  are shared, not obsolete, so they are not archived.
- `SubBox/src/audio/asr/ws_asr.*` remains active for downstream TTS playback. The
  WebSocket microphone/ASR methods are retained but are not used by the local-KWS
  voice path.

## Restoring a file

Do not copy an archived file back on its own. Restoring the old ActionBox KWS engine
would reintroduce duplicate inference and the old execution path. If a file is needed
for reference or a deliberate rollback, restore it to the original path and update the
CMake/build and tests in the same change. Back up NVS and relay state before flashing a
rollback build.
