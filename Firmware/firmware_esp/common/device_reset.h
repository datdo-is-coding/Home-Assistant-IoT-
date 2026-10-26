#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"

#ifdef __cplusplus
enum class ResetKind : uint8_t {
    NONE = 0,
    REBOOT = 1,
    NETWORK_RESET = 2,
    FACTORY_RESET = 3
};

enum class ResetIntentState : uint8_t {
    NONE = 0,
    INTENT_RECORDED = 1,
    RELAYS_OFF = 2
};

constexpr ResetKind RESET_KIND_NONE = ResetKind::NONE;
constexpr ResetKind RESET_KIND_REBOOT = ResetKind::REBOOT;
constexpr ResetKind RESET_KIND_NETWORK_RESET = ResetKind::NETWORK_RESET;
constexpr ResetKind RESET_KIND_FACTORY_RESET = ResetKind::FACTORY_RESET;

constexpr ResetIntentState RESET_INTENT_STATE_NONE = ResetIntentState::NONE;
constexpr ResetIntentState RESET_INTENT_STATE_RECORDED = ResetIntentState::INTENT_RECORDED;
constexpr ResetIntentState RESET_INTENT_STATE_RELAYS_OFF = ResetIntentState::RELAYS_OFF;

extern "C" {
#else
typedef enum {
    RESET_KIND_NONE           = 0,
    RESET_KIND_REBOOT         = 1,
    RESET_KIND_NETWORK_RESET  = 2,
    RESET_KIND_FACTORY_RESET  = 3
} ResetKind;

typedef enum {
    RESET_INTENT_STATE_NONE            = 0,
    RESET_INTENT_STATE_RECORDED        = 1,
    RESET_INTENT_STATE_RELAYS_OFF      = 2
} ResetIntentState;
#endif

#define RESET_INTENT_MAGIC 0x17E40001

typedef struct {
    uint32_t magic;
    uint8_t  state;           // ResetIntentState (NONE, RECORDED, RELAYS_OFF)
    uint8_t  kind;            // ResetKind (REBOOT, NETWORK_RESET, FACTORY_RESET)
    uint8_t  step;
    uint8_t  reserved;
    uint32_t owner_epoch;
    char     operation_id[64];
    uint32_t crc32;
} ResetIntent;

/**
 * @brief Prepare a device reset. Validates kind, operation_id and owner_epoch.
 * Rejects operations with stale/old owner_epoch.
 */
esp_err_t prepare_reset(ResetKind kind, const char* operation_id, uint32_t owner_epoch);

/**
 * @brief Execute a confirmed reset through strict 7-step safe procedure:
 * 1. Write reset_intent (state = INTENT_RECORDED) to NVS.
 * 2. Lock accepting control commands, stop audio streaming.
 * 3. Turn ALL relays OFF (channel 1..N).
 * 4. Update reset_intent (state = RELAYS_OFF) in NVS.
 * 5. Selective flash state erase & peer RAM cleanup:
 *    - Reboot: Keep NVS, generate new boot_id.
 *    - Network Reset: Clear peer link/SubBox pairing, keep calibration and room/channel config.
 *    - Factory Reset: Clear user config and peer list, PRESERVE factory data (calibrations, UID),
 *      and increment owner_epoch and reset_generation.
 * 6. Clear reset_intent from NVS.
 * 7. Delay 100ms and restart device.
 */
esp_err_t execute_confirmed_reset(ResetKind kind, const char* operation_id);
// Network callers must deliver the durable result before restarting.
esp_err_t complete_confirmed_reset(ResetKind kind, const char* operation_id);

/**
 * @brief Resume interrupted reset after power cut.
 * Checks reset_intent in NVS. If an incomplete reset is found, forces all relays OFF,
 * completes the reset steps according to intent kind, and clears the intent.
 * @return true if an interrupted reset was recovered and completed, false otherwise.
 */
bool resume_interrupted_reset(void);

/**
 * @brief Check if system controls are locked due to ongoing reset.
 */
bool is_reset_locked(void);

/**
 * @brief Cancel armed reset.
 */
void cancel_armed_reset(void);

#ifdef __cplusplus
}
#endif
