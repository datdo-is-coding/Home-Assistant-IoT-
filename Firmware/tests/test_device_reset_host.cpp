#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
#include <map>
#include <string>
#include <chrono>
#include <thread>

#include "host_idf.h"
#include "device_reset.h"
#include "nvs_storage.h"
#include "relay_driver.h"
#include "security_config.h"
#include "nvs_manager.h"
#include "device_lifecycle.h"

// ============================================================================
// Host IDF Mock Implementation
// ============================================================================

struct NvsEntry {
    std::vector<uint8_t> data;
    bool is_string = false;
};

static std::map<std::string, std::map<std::string, NvsEntry>> s_nvs_storage;
static std::map<nvs_handle_t, std::string> s_nvs_handles;
static nvs_handle_t s_next_handle = 1;

void mock_nvs_clear_all() {
    s_nvs_storage.clear();
    s_nvs_handles.clear();
    s_next_handle = 1;
}

void mock_nvs_clear_namespace(const char* ns) {
    if (ns) s_nvs_storage[ns].clear();
}

esp_err_t nvs_flash_init() { return ESP_OK; }
esp_err_t nvs_flash_erase() { mock_nvs_clear_all(); return ESP_OK; }

esp_err_t nvs_open(const char* name, int, nvs_handle_t* handle) {
    if (!name || !handle) return ESP_ERR_INVALID_ARG;
    for (const auto& kv : s_nvs_handles) {
        if (kv.second == name) {
            *handle = kv.first;
            return ESP_OK;
        }
    }
    *handle = s_next_handle++;
    s_nvs_handles[*handle] = name;
    return ESP_OK;
}

esp_err_t nvs_get_blob(nvs_handle_t handle, const char* key, void* out, size_t* size) {
    if (!key || !size) return ESP_ERR_INVALID_ARG;
    auto h_it = s_nvs_handles.find(handle);
    if (h_it == s_nvs_handles.end()) return ESP_ERR_INVALID_ARG;
    const std::string& ns = h_it->second;
    auto ns_it = s_nvs_storage.find(ns);
    if (ns_it == s_nvs_storage.end()) return ESP_ERR_NOT_FOUND;
    auto k_it = ns_it->second.find(key);
    if (k_it == ns_it->second.end()) return ESP_ERR_NOT_FOUND;
    const auto& val = k_it->second.data;
    if (out == nullptr) {
        *size = val.size();
        return ESP_OK;
    }
    if (*size < val.size()) {
        *size = val.size();
        return ESP_ERR_INVALID_SIZE;
    }
    memcpy(out, val.data(), val.size());
    *size = val.size();
    return ESP_OK;
}

esp_err_t nvs_set_blob(nvs_handle_t handle, const char* key, const void* bytes, size_t size) {
    if (!key || !bytes) return ESP_ERR_INVALID_ARG;
    auto h_it = s_nvs_handles.find(handle);
    if (h_it == s_nvs_handles.end()) return ESP_ERR_INVALID_ARG;
    const std::string& ns = h_it->second;
    const uint8_t* p = static_cast<const uint8_t*>(bytes);
    s_nvs_storage[ns][key] = NvsEntry{std::vector<uint8_t>(p, p + size), false};
    return ESP_OK;
}

esp_err_t nvs_get_str(nvs_handle_t handle, const char* key, char* out, size_t* size) {
    if (!key || !size) return ESP_ERR_INVALID_ARG;
    auto h_it = s_nvs_handles.find(handle);
    if (h_it == s_nvs_handles.end()) return ESP_ERR_INVALID_ARG;
    const std::string& ns = h_it->second;
    auto ns_it = s_nvs_storage.find(ns);
    if (ns_it == s_nvs_storage.end()) return ESP_ERR_NOT_FOUND;
    auto k_it = ns_it->second.find(key);
    if (k_it == ns_it->second.end()) return ESP_ERR_NOT_FOUND;
    const auto& val = k_it->second.data;
    if (out == nullptr) {
        *size = val.size();
        return ESP_OK;
    }
    if (*size < val.size()) {
        *size = val.size();
        return ESP_ERR_INVALID_SIZE;
    }
    memcpy(out, val.data(), val.size());
    *size = val.size();
    return ESP_OK;
}

esp_err_t nvs_set_str(nvs_handle_t handle, const char* key, const char* str) {
    if (!key || !str) return ESP_ERR_INVALID_ARG;
    auto h_it = s_nvs_handles.find(handle);
    if (h_it == s_nvs_handles.end()) return ESP_ERR_INVALID_ARG;
    const std::string& ns = h_it->second;
    size_t len = strlen(str) + 1;
    const uint8_t* p = reinterpret_cast<const uint8_t*>(str);
    s_nvs_storage[ns][key] = NvsEntry{std::vector<uint8_t>(p, p + len), true};
    return ESP_OK;
}

esp_err_t nvs_get_u32(nvs_handle_t handle, const char* key, uint32_t* out) {
    if (!key || !out) return ESP_ERR_INVALID_ARG;
    size_t sz = sizeof(uint32_t);
    return nvs_get_blob(handle, key, out, &sz);
}

esp_err_t nvs_set_u32(nvs_handle_t handle, const char* key, uint32_t val) {
    return nvs_set_blob(handle, key, &val, sizeof(uint32_t));
}

esp_err_t nvs_get_u8(nvs_handle_t handle, const char* key, uint8_t* out) {
    if (!key || !out) return ESP_ERR_INVALID_ARG;
    size_t sz = sizeof(uint8_t);
    return nvs_get_blob(handle, key, out, &sz);
}

esp_err_t nvs_set_u8(nvs_handle_t handle, const char* key, uint8_t val) {
    return nvs_set_blob(handle, key, &val, sizeof(uint8_t));
}

esp_err_t nvs_erase_key(nvs_handle_t handle, const char* key) {
    if (!key) return ESP_ERR_INVALID_ARG;
    auto h_it = s_nvs_handles.find(handle);
    if (h_it == s_nvs_handles.end()) return ESP_ERR_INVALID_ARG;
    const std::string& ns = h_it->second;
    s_nvs_storage[ns].erase(key);
    return ESP_OK;
}

esp_err_t nvs_erase_all(nvs_handle_t handle) {
    auto h_it = s_nvs_handles.find(handle);
    if (h_it == s_nvs_handles.end()) return ESP_ERR_INVALID_ARG;
    const std::string& ns = h_it->second;
    s_nvs_storage[ns].clear();
    return ESP_OK;
}

esp_err_t nvs_commit(nvs_handle_t) { return ESP_OK; }
void nvs_close(nvs_handle_t) {}

// GPIO mock
static std::map<int, uint32_t> s_gpio_levels;
esp_err_t gpio_config(const gpio_config_t*) { return ESP_OK; }
esp_err_t gpio_set_level(gpio_num_t pin, uint32_t level) {
    s_gpio_levels[pin] = level;
    return ESP_OK;
}
int gpio_get_level(gpio_num_t pin) {
    auto it = s_gpio_levels.find(pin);
    if (it != s_gpio_levels.end()) return it->second;
    return 1; // default high (unpressed)
}

// Runtime hooks
static int s_mock_espnow_peers = 0;
extern "C" esp_err_t espnow_transport_clear_peers(void) {
    s_mock_espnow_peers = 0;
    return ESP_OK;
}

static bool s_mock_voice_stopped = false;
extern "C" void voice_capture_stop_streaming(void) {
    s_mock_voice_stopped = true;
}

static int s_mock_restart_count = 0;
extern "C" void esp_restart(void) {
    s_mock_restart_count++;
}

extern "C" bool safety_sensor_ready(uint8_t) {
    return true;
}

// ============================================================================
// Test 1: Calibration survives factory reset
// ============================================================================
void test_calibration_survives_factory_reset() {
    printf("[TEST 1] Starting calibration_survives_factory_reset...\n");
    mock_nvs_clear_all();
    assert(nvs_storage_init() == ESP_OK);

    // Save custom factory data
    nvs_handle_t h;
    assert(nvs_open("actionbox_v2", NVS_READWRITE, &h) == ESP_OK);
    NvsFactoryData fd{};
    fd.magic = NVS_FACTORY_DATA_MAGIC;
    fd.schema_version = 1;
    strncpy(fd.device_uid, "AB2_FAC_UID_1", sizeof(fd.device_uid) - 1);
    strncpy(fd.board_model, "actionbox_v2", sizeof(fd.board_model) - 1);
    fd.calibrations[0].current_factor = 1.050f;
    fd.calibrations[0].voltage_factor = 220.5f;
    fd.calibrations[0].power_factor = 0.15f;
    fd.calibrations[1].current_factor = 1.060f;
    fd.calibrations[1].voltage_factor = 221.0f;
    fd.calibrations[1].power_factor = 0.25f;
    fd.calibrations[2].current_factor = 1.070f;
    fd.calibrations[2].voltage_factor = 222.0f;
    fd.calibrations[2].power_factor = 0.35f;
    fd.crc32 = calculate_crc32(reinterpret_cast<const uint8_t*>(&fd), offsetof(NvsFactoryData, crc32));
    assert(nvs_set_blob(h, "factory_data", &fd, sizeof(NvsFactoryData)) == ESP_OK);

    // Save custom user config
    NvsUserConfig uc{};
    uc.magic = NVS_USER_CONFIG_MAGIC;
    uc.schema_version = 1;
    strncpy(uc.node_id, "node_custom_1", sizeof(uc.node_id) - 1);
    strncpy(uc.room_id, "room_custom_1", sizeof(uc.room_id) - 1);
    strncpy(uc.channel_names[0], "Living Light 1", sizeof(uc.channel_names[0]) - 1);
    strncpy(uc.channel_names[1], "Living Light 2", sizeof(uc.channel_names[1]) - 1);
    strncpy(uc.channel_names[2], "Air Conditioner", sizeof(uc.channel_names[2]) - 1);
    uc.startup_modes[0] = STARTUP_MODE_ALWAYS_ON;
    uc.startup_modes[1] = STARTUP_MODE_ALWAYS_OFF;
    uc.startup_modes[2] = STARTUP_MODE_RESTORE_LAST;
    uc.assigned_subbox_mac[0] = 0xAA;
    uc.assigned_subbox_mac[5] = 0xBB;
    uc.has_assigned_subbox = true;
    uc.crc32 = calculate_crc32(reinterpret_cast<const uint8_t*>(&uc), offsetof(NvsUserConfig, crc32));
    assert(nvs_set_blob(h, "user_config", &uc, sizeof(NvsUserConfig)) == ESP_OK);
    nvs_close(h);

    // Reload and verify custom user config is loaded
    ActionBoxPersistentConfig loaded{};
    assert(nvs_storage_load_config(&loaded) == ESP_OK);
    assert(strcmp(loaded.node_id, "node_custom_1") == 0);
    assert(loaded.has_assigned_subbox == true);
    assert(loaded.calibrations[2].current_factor == 1.070f);

    // Execute Factory Reset
    ActionBoxPersistentConfig reset_cfg{};
    assert(nvs_storage_factory_reset(&reset_cfg) == ESP_OK);

    // Verify user config is reset to factory defaults (node_id restored to factory UID, room to default, unassigned)
    assert(strcmp(reset_cfg.node_id, "AB2_FAC_UID_1") == 0);
    assert(strcmp(reset_cfg.room_id, "LIVING_ROOM") == 0);
    assert(reset_cfg.has_assigned_subbox == false);
    assert(reset_cfg.startup_modes[2] == STARTUP_MODE_ALWAYS_OFF);

    // CRITICAL: Verify factory calibration and factory UID survived 100%
    NvsFactoryData read_fd{};
    assert(nvs_storage_get_factory_data(&read_fd) == ESP_OK);
    assert(strcmp(read_fd.device_uid, "AB2_FAC_UID_1") == 0);
    assert(read_fd.calibrations[0].current_factor == 1.050f);
    assert(read_fd.calibrations[0].voltage_factor == 220.5f);
    assert(read_fd.calibrations[1].current_factor == 1.060f);
    assert(read_fd.calibrations[2].current_factor == 1.070f);
    assert(read_fd.calibrations[2].voltage_factor == 222.0f);
    assert(read_fd.calibrations[2].power_factor == 0.35f);
    assert(reset_cfg.calibrations[2].current_factor == 1.070f);
    assert(nvs_storage_get_cached_config()->calibrations[2].current_factor == 1.070f);

    printf("[TEST 1] PASS: Factory calibration survived factory reset byte-for-byte.\n");
}

// ============================================================================
// Test 2: Channel 3 and all relays OFF before reset & Command lock
// ============================================================================
void test_channel3_off_before_reset() {
    printf("[TEST 2] Starting channel3_off_before_reset...\n");
    assert(relay_driver_init() == ESP_OK);

    // Turn ON all 3 channels
    assert(relay_on(1) == ESP_OK);
    assert(relay_on(2) == ESP_OK);
    assert(relay_on(3) == ESP_OK);
    assert(relay_get_state(1) == RELAY_STATE_ON);
    assert(relay_get_state(2) == RELAY_STATE_ON);
    assert(relay_get_state(3) == RELAY_STATE_ON);

    // Verify lock state before reset
    assert(!is_reset_locked());

    // Prepare and execute reset
    uint32_t epoch = nvs_storage_get_owner_epoch();
    assert(prepare_reset(ResetKind::FACTORY_RESET, "op_reset_ch3_test", epoch) == ESP_OK);
    assert(execute_confirmed_reset(ResetKind::FACTORY_RESET, "op_reset_ch3_test") == ESP_OK);

    // Verify ALL relays, specifically Channel 3, are in RELAY_STATE_OFF
    assert(relay_get_state(1) == RELAY_STATE_OFF);
    assert(relay_get_state(2) == RELAY_STATE_OFF);
    assert(relay_get_state(3) == RELAY_STATE_OFF);

    // Verify command lock is active
    assert(is_reset_locked() == true);
    printf("[TEST 2] PASS: Channel 3 and all relays OFF before reset, reset locked.\n");
}

// ============================================================================
// Test 3: Power-cut resumption logic
// ============================================================================
void test_power_cut_resume() {
    printf("[TEST 3] Starting power_cut_resume...\n");

    // Scenario A: Power cut at step 1 (INTENT_RECORDED)
    {
        assert(relay_on(1) == ESP_OK);
        assert(relay_on(3) == ESP_OK);
        assert(relay_get_state(3) == RELAY_STATE_ON);

        ResetIntent intent{};
        intent.magic = RESET_INTENT_MAGIC;
        intent.state = static_cast<uint8_t>(ResetIntentState::INTENT_RECORDED);
        intent.kind = static_cast<uint8_t>(ResetKind::FACTORY_RESET);
        intent.step = 1;
        intent.owner_epoch = nvs_storage_get_owner_epoch();
        strncpy(intent.operation_id, "op_cut_step1", sizeof(intent.operation_id) - 1);
        intent.crc32 = calculate_crc32(reinterpret_cast<const uint8_t*>(&intent), offsetof(ResetIntent, crc32));
        assert(nvs_storage_write_reset_intent(&intent) == ESP_OK);

        // Simulate boot resumption
        bool resumed = resume_interrupted_reset();
        assert(resumed == true);
        assert(relay_get_state(1) == RELAY_STATE_OFF);
        assert(relay_get_state(3) == RELAY_STATE_OFF);

        // Verify intent was cleared
        ResetIntent check{};
        assert(nvs_storage_read_reset_intent(&check) != ESP_OK);
    }

    // Scenario B: Power cut at step 4 (RELAYS_OFF)
    {
        s_mock_espnow_peers = 3;
        ResetIntent intent{};
        intent.magic = RESET_INTENT_MAGIC;
        intent.state = static_cast<uint8_t>(ResetIntentState::RELAYS_OFF);
        intent.kind = static_cast<uint8_t>(ResetKind::NETWORK_RESET);
        intent.step = 4;
        intent.owner_epoch = nvs_storage_get_owner_epoch();
        strncpy(intent.operation_id, "op_cut_step4", sizeof(intent.operation_id) - 1);
        intent.crc32 = calculate_crc32(reinterpret_cast<const uint8_t*>(&intent), offsetof(ResetIntent, crc32));
        assert(nvs_storage_write_reset_intent(&intent) == ESP_OK);

        bool resumed = resume_interrupted_reset();
        assert(resumed == true);
        assert(s_mock_espnow_peers == 0);

        ResetIntent check{};
        assert(nvs_storage_read_reset_intent(&check) != ESP_OK);
    }

    // Scenario C: Clean boot
    {
        bool resumed = resume_interrupted_reset();
        assert(resumed == false);
    }

    printf("[TEST 3] PASS: Power-cut resumption recovered all states cleanly.\n");
}

// ============================================================================
// Test 4: Peer runtime cleared (ActionBox + SubBox)
// ============================================================================
void test_peer_runtime_cleared() {
    printf("[TEST 4] Starting peer_runtime_cleared...\n");

    // ActionBox ESP-NOW peer clearance
    s_mock_espnow_peers = 5;
    uint32_t epoch = nvs_storage_get_owner_epoch();
    assert(prepare_reset(ResetKind::NETWORK_RESET, "op_peer_clean", epoch) == ESP_OK);
    assert(execute_confirmed_reset(ResetKind::NETWORK_RESET, "op_peer_clean") == ESP_OK);
    assert(s_mock_espnow_peers == 0);

    // CONFIG must leave a bounded discovery window after the user releases it.
    SecurityConfig::factoryReset();
    gpio_set_level(1, 0);
    assert(SecurityConfig::isPairingAllowed());
    gpio_set_level(1, 1);
    assert(SecurityConfig::isPairingAllowed() && "CONFIG release must keep discovery open");

    // SubBox Peer & Credential clearance
    TrustedPeer p1{};
    p1.mac[0] = 0x12; p1.mac[5] = 0x34;
    memset(p1.lmk, 0xEE, 16);
    gpio_set_level(1, 0); // physical presence active
    SecurityConfig::openPairingWindow(60000);
    assert(SecurityConfig::savePeer(p1) == ESP_OK);
    gpio_set_level(1, 1); // release physical presence button
    assert(SecurityConfig::hasConfiguredPeers() == true);
    assert(SecurityConfig::isPeerTrusted(p1.mac) == true);

    // SubBox Network Reset opens 180s pairing window and preserves peers
    assert(NVSManager::networkReset() == ESP_OK);
    assert(SecurityConfig::isPairingAllowed() == true);
    assert(SecurityConfig::hasConfiguredPeers() == true);

    // SubBox Factory Reset wipes peers & credentials completely
    assert(NVSManager::factoryReset() == ESP_OK);
    assert(SecurityConfig::hasConfiguredPeers() == false);
    assert(SecurityConfig::isPeerTrusted(p1.mac) == false);

    printf("[TEST 4] PASS: Peer table and runtime cleared across ActionBox & SubBox.\n");
}

// ============================================================================
// Test 5: Owner epoch monotonicity across factory reset
// ============================================================================
void test_owner_epoch_monotonicity_across_factory_reset() {
    printf("[TEST 5] Starting owner_epoch_monotonicity_across_factory_reset...\n");

    // ActionBox Epoch Monotonicity
    uint32_t e1 = nvs_storage_get_owner_epoch();
    assert(prepare_reset(ResetKind::FACTORY_RESET, "epoch_reset_1", e1) == ESP_OK);
    assert(execute_confirmed_reset(ResetKind::FACTORY_RESET, "epoch_reset_1") == ESP_OK);
    uint32_t e2 = nvs_storage_get_owner_epoch();
    assert(e2 == e1 + 1);

    assert(prepare_reset(ResetKind::FACTORY_RESET, "epoch_reset_2", e2) == ESP_OK);
    assert(execute_confirmed_reset(ResetKind::FACTORY_RESET, "epoch_reset_2") == ESP_OK);
    uint32_t e3 = nvs_storage_get_owner_epoch();
    assert(e3 == e2 + 1);

    // Stale epoch commands must be rejected
    assert(prepare_reset(ResetKind::FACTORY_RESET, "stale_e1", e1) == ESP_ERR_INVALID_VERSION);
    assert(prepare_reset(ResetKind::FACTORY_RESET, "stale_e2", e2) == ESP_ERR_INVALID_VERSION);
    assert(prepare_reset(ResetKind::FACTORY_RESET, "valid_e3", e3) == ESP_OK);

    // SubBox Epoch Monotonicity
    uint32_t sb_e1 = SecurityConfig::getOwnerEpoch();
    assert(SecurityConfig::factoryReset() == ESP_OK);
    uint32_t sb_e2 = SecurityConfig::getOwnerEpoch();
    assert(sb_e2 == sb_e1 + 1);

    printf("[TEST 5] PASS: Monotonically increasing owner_epoch validated.\n");
}

// ============================================================================
// Test 6: Legacy blob migration without silent fallback
// ============================================================================
void test_nvs_migration_legacy_blob() {
    printf("[TEST 6] Starting nvs_migration_legacy_blob...\n");
    mock_nvs_clear_all();
    nvs_storage_deinit();

    // Populate legacy single config_blob in NVS
    nvs_handle_t h;
    assert(nvs_open("actionbox_v2", NVS_READWRITE, &h) == ESP_OK);

    ActionBoxPersistentConfig legacy{};
    legacy.config_version = 0xAB001001;
    strncpy(legacy.node_id, "mig_node_99", sizeof(legacy.node_id) - 1);
    strncpy(legacy.room_id, "mig_room_88", sizeof(legacy.room_id) - 1);
    strncpy(legacy.channel_names[0], "Migrated Ch1", sizeof(legacy.channel_names[0]) - 1);
    strncpy(legacy.channel_names[1], "Migrated Ch2", sizeof(legacy.channel_names[1]) - 1);
    strncpy(legacy.channel_names[2], "Migrated AC Ch3", sizeof(legacy.channel_names[2]) - 1);
    legacy.startup_modes[0] = STARTUP_MODE_ALWAYS_OFF;
    legacy.startup_modes[1] = STARTUP_MODE_ALWAYS_ON;
    legacy.startup_modes[2] = STARTUP_MODE_RESTORE_LAST;
    legacy.calibrations[0].current_factor = 1.111f;
    legacy.calibrations[1].current_factor = 2.222f;
    legacy.calibrations[2].current_factor = 3.333f;
    legacy.calibrations[2].voltage_factor = 230.5f;
    legacy.calibrations[2].power_factor = 1.25f;
    legacy.assigned_subbox_mac[0] = 0xDE;
    legacy.assigned_subbox_mac[5] = 0xAD;
    legacy.has_assigned_subbox = true;

    assert(nvs_set_blob(h, "config_blob", &legacy, sizeof(legacy)) == ESP_OK);
    nvs_close(h);

    // Initialize storage -> triggers automatic migration
    assert(nvs_storage_init() == ESP_OK);

    // 1. Verify user config migrated
    const ActionBoxPersistentConfig* cached = nvs_storage_get_cached_config();
    assert(strcmp(cached->node_id, "mig_node_99") == 0);
    assert(strcmp(cached->room_id, "mig_room_88") == 0);
    assert(strcmp(cached->channel_names[2], "Migrated AC Ch3") == 0);
    assert(cached->startup_modes[2] == STARTUP_MODE_RESTORE_LAST);
    assert(cached->has_assigned_subbox == true);
    assert(cached->assigned_subbox_mac[0] == 0xDE);

    // 2. Verify factory calibrations migrated WITHOUT silent fallback
    assert(cached->calibrations[2].current_factor == 3.333f);
    assert(cached->calibrations[2].voltage_factor == 230.5f);
    NvsFactoryData fd{};
    assert(nvs_storage_get_factory_data(&fd) == ESP_OK);
    assert(fd.calibrations[2].current_factor == 3.333f);
    assert(fd.calibrations[2].voltage_factor == 230.5f);

    // 3. Verify owner epoch initialized to 1
    assert(nvs_storage_get_owner_epoch() == 1);

    // 4. Verify legacy key config_blob was erased after migration commit
    assert(nvs_open("actionbox_v2", NVS_READONLY, &h) == ESP_OK);
    size_t sz = sizeof(legacy);
    assert(nvs_get_blob(h, "config_blob", &legacy, &sz) == ESP_ERR_NOT_FOUND);
    nvs_close(h);

    // 5. Subsequent load succeeds
    ActionBoxPersistentConfig reloaded{};
    assert(nvs_storage_load_config(&reloaded) == ESP_OK);
    assert(strcmp(reloaded.node_id, "mig_node_99") == 0);
    assert(reloaded.calibrations[2].current_factor == 3.333f);

    // 6. Corrupted legacy blob refusal check (Defect 1)
    mock_nvs_clear_all();
    nvs_storage_deinit();
    assert(nvs_open("actionbox_v2", NVS_READWRITE, &h) == ESP_OK);
    ActionBoxPersistentConfig corrupt{};
    corrupt.config_version = 0xBADF00D; // invalid version magic
    assert(nvs_set_blob(h, "config_blob", &corrupt, sizeof(corrupt)) == ESP_OK);
    nvs_close(h);
    // Must refuse fallback to defaults and return ESP_ERR_INVALID_VERSION
    assert(nvs_storage_init() == ESP_ERR_INVALID_VERSION);

    // Verify factory data was NOT overwritten with default values
    assert(nvs_open("actionbox_v2", NVS_READONLY, &h) == ESP_OK);
    NvsFactoryData unwritten_fd{};
    size_t fd_sz = sizeof(unwritten_fd);
    assert(nvs_get_blob(h, "factory_data", &unwritten_fd, &fd_sz) == ESP_ERR_NOT_FOUND);
    nvs_close(h);

    printf("[TEST 6] PASS: Legacy config_blob cleanly migrated into 4 NVS partitions & corrupted blob rejected.\n");
}

// ============================================================================
// Test 7: SubBox Factory Reset preserves factory UID
// ============================================================================
void test_subbox_factory_reset_preserves_uid() {
    printf("[TEST 7] Starting subbox_factory_reset_preserves_uid...\n");
    nvs_handle_t h;
    assert(nvs_open("subbox_cfg", NVS_READWRITE, &h) == ESP_OK);
    assert(nvs_set_str(h, "id", "SB_PERMANENT_UID_456") == ESP_OK);
    assert(nvs_set_str(h, "room", "Master Bedroom") == ESP_OK);
    assert(nvs_set_str(h, "ssid", "HomeWiFi") == ESP_OK);
    assert(nvs_set_str(h, "pass", "SecretPassword") == ESP_OK);
    nvs_close(h);

    // Perform SubBox Factory Reset
    assert(NVSManager::factoryReset() == ESP_OK);

    // Verify factory UID is preserved
    assert(nvs_open("subbox_cfg", NVS_READONLY, &h) == ESP_OK);
    char uid[32]{};
    size_t len = sizeof(uid);
    assert(nvs_get_str(h, "id", uid, &len) == ESP_OK);
    assert(strcmp(uid, "SB_PERMANENT_UID_456") == 0);

    // Verify user config was wiped
    char dummy[64]{};
    len = sizeof(dummy);
    assert(nvs_get_str(h, "room", dummy, &len) == ESP_ERR_NOT_FOUND);
    assert(nvs_get_str(h, "ssid", dummy, &len) == ESP_ERR_NOT_FOUND);
    nvs_close(h);

    printf("[TEST 7] PASS: SubBox factory reset preserved UID and erased user credentials.\n");
}

void test_registration_persistence_and_encrypted_peer_isolation() {
    SecurityConfig::factoryReset();
    RegisteredPeer peer{}; peer.mac[0]=2; peer.mac[5]=9;
    peer.claim.type=CLAIM_FRAME;peer.claim.version=3;peer.claim.session=42;peer.claim.revision=2;
    strcpy(peer.claim.node_id,"AB020000000009");strcpy(peer.claim.operation,"op_claim_test");
    strcpy(peer.claim.room,"livingroom");
    for(auto& name:peer.claim.channels) strcpy(name,"switch");
    assert(SecurityConfig::saveRegistration(peer)!=ESP_OK);
    SecurityConfig::networkReset();
    assert(SecurityConfig::saveRegistration(peer)==ESP_OK);
    RegisteredPeer restored{};
    assert(SecurityConfig::loadRegistration(0,restored));
    assert(memcmp(&peer,&restored,sizeof(peer))==0);
    assert(SecurityConfig::hasConfiguredPeers());
    TrustedPeer encrypted{}; encrypted.mac[0]=2;encrypted.mac[5]=10;encrypted.lmk[0]=99;
    assert(SecurityConfig::savePeer(encrypted)==ESP_OK);
    peer.mac[5]=10;
    assert(SecurityConfig::saveRegistration(peer)!=ESP_OK);
    assert(SecurityConfig::loadPeer(0,encrypted) && encrypted.lmk[0]==99);
    assert(SecurityConfig::clearPeers()==ESP_OK);
    assert(!SecurityConfig::loadRegistration(0,restored));
}

int main() {
    printf("============================================================\n");
    printf("   RUNNING ALL SAFE DEVICE RESET & NVS MIGRATION HOST TESTS  \n");
    printf("============================================================\n");

    test_registration_persistence_and_encrypted_peer_isolation();
    test_calibration_survives_factory_reset();
    test_channel3_off_before_reset();
    test_power_cut_resume();
    test_peer_runtime_cleared();
    test_owner_epoch_monotonicity_across_factory_reset();
    test_nvs_migration_legacy_blob();
    test_subbox_factory_reset_preserves_uid();

    printf("\n=== ALL DEVICE RESET HOST TESTS PASSED! ===\n");
    return 0;
}
