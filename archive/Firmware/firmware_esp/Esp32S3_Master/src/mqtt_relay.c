/*
 * MQTT Relay Controller — Implementation
 * DTV Smart Home — ESP32-S3 Combined Node (Voice + Relay)
 *
 * Handles:
 *   1. Dynamic Node Identity (Unique MAC, NVS-persisted room & channel names)
 *   2. Zero-collision Provisioning Flow (Pairing from WebUI)
 *   3. Compact v2 Protocol (protocol_spec.md) + Legacy MQTT backward compatibility
 *   4. Safe relay GPIO control (Active-LOW, Optocoupler PC817)
 *   5. Periodic heartbeat / telemetry echo
 */

#include "mqtt_relay.h"
#include "audio_feedback.h"
#include "ota_updater.h"
#include "device_identity.h"

#include <string.h>
#include <stdio.h>
#include <ctype.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_mac.h"
#include "esp_system.h"
#include "driver/gpio.h"
#include "mqtt_client.h"
#include "cJSON.h"
#include "nvs_flash.h"
#include "nvs.h"

static const char *TAG = "MQTT_RELAY";

#define HEARTBEAT_INTERVAL_S  30
#define NVS_NAMESPACE         "dtv_cfg"

/* ─── Dynamic Identity Struct ────────────────────────────────────────── */

typedef struct {
    bool is_provisioned;
    char node_id[64];       /* e.g. "livingroom-node01" or temp "esp32s3_BD69D4" */
    char room[32];          /* e.g. "livingroom" */
    char rl1_name[20];      /* e.g. "light" */
    char rl2_name[20];      /* e.g. "fan" */
    uint32_t cfg_version;
    uint8_t mac[6];
    char mac_str[18];       /* "30:ED:A0:BD:69:D4" */
    char mac_lower[18];     /* "30:ed:a0:bd:69:d4" */
    char mac_clean[13];     /* "30EDA0BD69D4" */
} node_config_t;

static node_config_t s_node;

/* ─── State ──────────────────────────────────────────────────────────── */

static esp_mqtt_client_handle_t mqtt_client = NULL;
static volatile bool mqtt_connected = false;
static volatile bool relay_state[2] = {false, false};  /* ch1, ch2 */
static const int relay_gpio[2] = {RELAY_CH1_GPIO, RELAY_CH2_GPIO};
static uint32_t boot_time_ms = 0;

/* ─── Forward Declarations ───────────────────────────────────────────── */

static void mqtt_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data);
static void handle_command(const char *data, int len);
static void handle_ota_command(const char *payload);
static void heartbeat_task(void *arg);
static void publish_registration(void);
static void load_nvs_config(void);

/* ─── NVS Configuration Helpers ──────────────────────────────────────── */

static void load_nvs_config(void)
{
    device_identity_init();
    const hardware_identity_t *hw = device_identity_get_hardware();
    const user_identity_t *usr = device_identity_get_user();

    memcpy(s_node.mac, hw->mac_raw, 6);
    strncpy(s_node.mac_str, hw->mac_str, sizeof(s_node.mac_str) - 1);
    snprintf(s_node.mac_lower, sizeof(s_node.mac_lower), "%02x:%02x:%02x:%02x:%02x:%02x",
             hw->mac_raw[0], hw->mac_raw[1], hw->mac_raw[2],
             hw->mac_raw[3], hw->mac_raw[4], hw->mac_raw[5]);
    snprintf(s_node.mac_clean, sizeof(s_node.mac_clean), "%02X%02X%02X%02X%02X%02X",
             hw->mac_raw[0], hw->mac_raw[1], hw->mac_raw[2],
             hw->mac_raw[3], hw->mac_raw[4], hw->mac_raw[5]);

    /* Primary key is hardware device_id (e.g. node_7f3a91c2) */
    strncpy(s_node.node_id, hw->device_id, sizeof(s_node.node_id) - 1);
    strncpy(s_node.room, usr->room, sizeof(s_node.room) - 1);
    strncpy(s_node.rl1_name, usr->rl1_name, sizeof(s_node.rl1_name) - 1);
    strncpy(s_node.rl2_name, usr->rl2_name, sizeof(s_node.rl2_name) - 1);
    s_node.cfg_version = usr->cfg_version;
    s_node.is_provisioned = usr->is_provisioned;

    if (s_node.is_provisioned) {
        ESP_LOGI(TAG, "📋 Node IDENTITY [PROVISIONED / READY]: ID='%s', Name='%s', Room='%s', RL1='%s', RL2='%s', v=%lu",
                 s_node.node_id, usr->name, s_node.room, s_node.rl1_name, s_node.rl2_name,
                 (unsigned long)s_node.cfg_version);
    } else {
        ESP_LOGW(TAG, "📢 Node IDENTITY [FACTORY_NEW]: DeviceID='%s', Serial='%s', MAC=%s — Waiting for Gateway Claiming!",
                 hw->device_id, hw->serial, s_node.mac_str);
    }
}

esp_err_t mqtt_relay_save_config(const char *node_id, const char *room,
                                const char *rl1, const char *rl2,
                                uint32_t version)
{
    if (!node_id || strlen(node_id) == 0) return ESP_ERR_INVALID_ARG;

    nvs_handle_t h;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;

    nvs_set_u8(h, "prov", 1);
    nvs_set_str(h, "node_id", node_id);
    if (room) nvs_set_str(h, "room", room);
    if (rl1) nvs_set_str(h, "rl1", rl1);
    if (rl2) nvs_set_str(h, "rl2", rl2);
    nvs_set_u32(h, "cfg_ver", version);

    err = nvs_commit(h);
    nvs_close(h);

    if (err == ESP_OK) {
        strncpy(s_node.node_id, node_id, sizeof(s_node.node_id) - 1);
        if (room) strncpy(s_node.room, room, sizeof(s_node.room) - 1);
        if (rl1) strncpy(s_node.rl1_name, rl1, sizeof(s_node.rl1_name) - 1);
        if (rl2) strncpy(s_node.rl2_name, rl2, sizeof(s_node.rl2_name) - 1);
        s_node.cfg_version = version;
        s_node.is_provisioned = true;
        ESP_LOGI(TAG, "💾 Saved provision config to NVS: ID='%s', Room='%s', RL1='%s', RL2='%s', v=%lu",
                 s_node.node_id, s_node.room, s_node.rl1_name, s_node.rl2_name, (unsigned long)version);
    }
    return err;
}

void mqtt_relay_factory_reset(void)
{
    nvs_handle_t h;
    if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h) == ESP_OK) {
        nvs_erase_all(h);
        nvs_commit(h);
        nvs_close(h);
    }
    ESP_LOGW(TAG, "⚠️ FACTORY RESET: NVS erased. Soft restarting into unprovisioned state...");
    vTaskDelay(pdMS_TO_TICKS(500));
    esp_restart();
}

bool mqtt_relay_is_provisioned(void)
{
    return s_node.is_provisioned;
}

void mqtt_relay_set_provisioned(bool prov)
{
    s_node.is_provisioned = prov;
    nvs_handle_t h;
    if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h) == ESP_OK) {
        nvs_set_u8(h, "prov", prov ? 1 : 0);
        nvs_commit(h);
        nvs_close(h);
    }
}

const char *mqtt_relay_get_node_id(void)
{
    return s_node.node_id;
}

const char *mqtt_relay_get_room(void)
{
    return s_node.room;
}

const char *mqtt_relay_get_mac_str(void)
{
    return s_node.mac_str;
}

uint32_t mqtt_relay_get_cfg_version(void)
{
    return s_node.cfg_version;
}

/* ─── Parse and Apply Provision JSON from Gateway ────────────────────── */

bool mqtt_relay_handle_cfg_json(const char *json_str)
{
    if (!json_str) return false;

    cJSON *root = cJSON_Parse(json_str);
    if (!root) return false;

    /* Check if this is a remote factory reset command */
    const cJSON *act_item = cJSON_GetObjectItem(root, "action");
    if (!act_item) act_item = cJSON_GetObjectItem(root, "cmd");
    if (cJSON_IsString(act_item) && (strcmp(act_item->valuestring, "factory_reset") == 0 ||
                                     strcmp(act_item->valuestring, "reset") == 0)) {
        ESP_LOGW(TAG, "⚠️ Received remote factory_reset command via cfg topic!");
        cJSON_Delete(root);
        mqtt_relay_factory_reset();
        return true;
    }

    const cJSON *id_item = cJSON_GetObjectItem(root, "id");
    if (!id_item) id_item = cJSON_GetObjectItem(root, "node_id");
    if (!id_item) id_item = cJSON_GetObjectItem(root, "device_id");

    /* Support user identity attributes */
    const cJSON *name_item = cJSON_GetObjectItem(root, "name");
    const cJSON *room_item = cJSON_GetObjectItem(root, "room");
    const cJSON *loc_item  = cJSON_GetObjectItem(root, "location");
    const cJSON *desc_item = cJSON_GetObjectItem(root, "description");
    const cJSON *rl1_item  = cJSON_GetObjectItem(root, "rl1");
    const cJSON *rl2_item  = cJSON_GetObjectItem(root, "rl2");
    const cJSON *v_item    = cJSON_GetObjectItem(root, "v");
    if (!v_item) v_item = cJSON_GetObjectItem(root, "cfg_version");

    user_identity_t u;
    memset(&u, 0, sizeof(u));
    const user_identity_t *cur = device_identity_get_user();
    if (cur) {
        memcpy(&u, cur, sizeof(u));
    }

    if (cJSON_IsString(name_item) && strlen(name_item->valuestring) > 0)
        strncpy(u.name, name_item->valuestring, sizeof(u.name) - 1);
    if (cJSON_IsString(room_item) && strlen(room_item->valuestring) > 0)
        strncpy(u.room, room_item->valuestring, sizeof(u.room) - 1);
    if (cJSON_IsString(loc_item) && strlen(loc_item->valuestring) > 0)
        strncpy(u.location, loc_item->valuestring, sizeof(u.location) - 1);
    if (cJSON_IsString(desc_item) && strlen(desc_item->valuestring) > 0)
        strncpy(u.description, desc_item->valuestring, sizeof(u.description) - 1);
    if (cJSON_IsString(rl1_item) && strlen(rl1_item->valuestring) > 0)
        strncpy(u.rl1_name, rl1_item->valuestring, sizeof(u.rl1_name) - 1);
    if (cJSON_IsString(rl2_item) && strlen(rl2_item->valuestring) > 0)
        strncpy(u.rl2_name, rl2_item->valuestring, sizeof(u.rl2_name) - 1);
    if (cJSON_IsNumber(v_item))
        u.cfg_version = (uint32_t)v_item->valueint;
    else
        u.cfg_version = u.cfg_version + 1;

    u.is_provisioned = true;

    /* Idempotency check: nếu cấu hình và phiên bản đã hoàn toàn giống cấu hình hiện tại, không reboot */
    if (cur && cur->is_provisioned && cur->cfg_version == u.cfg_version &&
        strcmp(cur->name, u.name) == 0 &&
        strcmp(cur->room, u.room) == 0 &&
        strcmp(cur->location, u.location) == 0 &&
        strcmp(cur->rl1_name, u.rl1_name) == 0 &&
        strcmp(cur->rl2_name, u.rl2_name) == 0) {
        ESP_LOGI(TAG, "⚡ [CFG IDEMPOTENT] Config already up-to-date (v=%lu, Name='%s'), skipping reboot!",
                 (unsigned long)u.cfg_version, u.name);
        cJSON_Delete(root);
        return true;
    }

    ESP_LOGI(TAG, "🎉 Received Commercial Provision Cfg: Name='%s', Room='%s', Loc='%s', v=%lu",
             u.name, u.room, u.location, (unsigned long)u.cfg_version);

    device_identity_save_user_config(&u);
    load_nvs_config();

    /* Send instant ACK to smarthome/hello so Gateway WebUI immediately updates */
    if (mqtt_client && mqtt_connected) {
        publish_registration();
    }

    audio_feedback_play(AUDIO_FB_SUCCESS);
    cJSON_Delete(root);

    /* Soft restart in 1 second so all subsystems cleanly adopt the new node identity */
    ESP_LOGI(TAG, "🔄 Rebooting in 1s to apply new node identity across all tasks...");
    vTaskDelay(pdMS_TO_TICKS(1000));
    esp_restart();
    return true;
}

/* ─── Device OS Twin: Desired / Reported Config (Spec Section 4) ───── */

void mqtt_relay_publish_reported_config(uint32_t version)
{
    if (!mqtt_client || !mqtt_connected) return;

    const hardware_identity_t *hw = device_identity_get_hardware();
    const user_identity_t *usr = device_identity_get_user();

    cJSON *root = cJSON_CreateObject();
    if (!root) return;

    uint32_t rep_v = version ? version : usr->cfg_version;
    cJSON_AddStringToObject(root, "device_id", hw->device_id);
    cJSON_AddNumberToObject(root, "version", rep_v);
    cJSON_AddNumberToObject(root, "cfg_version", rep_v);
    cJSON_AddStringToObject(root, "name", usr->name);
    cJSON_AddStringToObject(root, "room", usr->room);
    cJSON_AddStringToObject(root, "location", usr->location);
    cJSON_AddStringToObject(root, "description", usr->description);
    cJSON_AddStringToObject(root, "rl1", usr->rl1_name);
    cJSON_AddStringToObject(root, "rl2", usr->rl2_name);
    cJSON_AddStringToObject(root, "status", "APPLIED");
    cJSON_AddNumberToObject(root, "free_heap", (uint32_t)esp_get_free_heap_size());

    char *json_str = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);

    if (json_str) {
        char topic[96];
        snprintf(topic, sizeof(topic), "home/devices/%s/config/reported", hw->device_id);
        esp_mqtt_client_publish(mqtt_client, topic, json_str, 0, 1, 1);
        ESP_LOGI(TAG, "📤 [Reported Twin] Published to %s: v=%lu", topic, (unsigned long)rep_v);
        free(json_str);
    }
}

bool mqtt_relay_handle_desired_config(const char *json_str)
{
    cJSON *root = cJSON_Parse(json_str);
    if (!root) {
        ESP_LOGW(TAG, "Failed to parse desired config JSON: %s", json_str);
        return false;
    }

    user_identity_t u;
    memset(&u, 0, sizeof(u));
    const user_identity_t *cur = device_identity_get_user();
    memcpy(&u, cur, sizeof(u));

    const cJSON *ver = cJSON_GetObjectItem(root, "version");
    if (!ver) ver = cJSON_GetObjectItem(root, "v");
    if (cJSON_IsNumber(ver)) {
        u.cfg_version = (uint32_t)ver->valueint;
    } else {
        u.cfg_version += 1;
    }

    const cJSON *name = cJSON_GetObjectItem(root, "name");
    if (cJSON_IsString(name) && name->valuestring && strlen(name->valuestring) > 0) {
        strncpy(u.name, name->valuestring, sizeof(u.name) - 1);
    }

    const cJSON *room = cJSON_GetObjectItem(root, "room");
    if (cJSON_IsString(room) && room->valuestring && strlen(room->valuestring) > 0) {
        strncpy(u.room, room->valuestring, sizeof(u.room) - 1);
    }

    const cJSON *loc = cJSON_GetObjectItem(root, "location");
    if (cJSON_IsString(loc) && loc->valuestring) {
        strncpy(u.location, loc->valuestring, sizeof(u.location) - 1);
    }

    const cJSON *desc = cJSON_GetObjectItem(root, "description");
    if (cJSON_IsString(desc) && desc->valuestring) {
        strncpy(u.description, desc->valuestring, sizeof(u.description) - 1);
    }

    const cJSON *rl1 = cJSON_GetObjectItem(root, "rl1");
    if (cJSON_IsString(rl1) && rl1->valuestring) {
        strncpy(u.rl1_name, rl1->valuestring, sizeof(u.rl1_name) - 1);
    }

    const cJSON *rl2 = cJSON_GetObjectItem(root, "rl2");
    if (cJSON_IsString(rl2) && rl2->valuestring) {
        strncpy(u.rl2_name, rl2->valuestring, sizeof(u.rl2_name) - 1);
    }

    /* Idempotency check: if config version and settings are already up-to-date, skip saving */
    if (cur && cur->is_provisioned && cur->cfg_version == u.cfg_version &&
        strcmp(cur->name, u.name) == 0 &&
        strcmp(cur->room, u.room) == 0 &&
        strcmp(cur->location, u.location) == 0 &&
        strcmp(cur->rl1_name, u.rl1_name) == 0 &&
        strcmp(cur->rl2_name, u.rl2_name) == 0) {
        ESP_LOGI(TAG, "⚡ [Desired Twin IDEMPOTENT] Config v=%lu already active, skipping re-apply",
                 (unsigned long)u.cfg_version);
        cJSON_Delete(root);
        return true;
    }

    u.is_provisioned = true;

    ESP_LOGI(TAG, "✨ [Desired Twin Applied]: Name='%s', Room='%s', RL1='%s', RL2='%s', v=%lu",
             u.name, u.room, u.rl1_name, u.rl2_name, (unsigned long)u.cfg_version);

    device_identity_save_user_config(&u);
    load_nvs_config();

    /* Immediately echo reported twin state */
    mqtt_relay_publish_reported_config(u.cfg_version);

    /* Desired twin sync is a background operation — do not play intrusive audio chimes */
    cJSON_Delete(root);
    return true;
}

/* ─── GPIO Relay Control ─────────────────────────────────────────────── */

static void init_relay_gpios(void)
{
    gpio_config_t io_conf = {
        .intr_type = GPIO_INTR_DISABLE,
        .mode = GPIO_MODE_OUTPUT,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pin_bit_mask = (1ULL << RELAY_CH1_GPIO) | (1ULL << RELAY_CH2_GPIO),
    };
    gpio_config(&io_conf);

    /* Initialize relays to OFF state (Active-LOW: 1=OFF, 0=ON) */
    for (int i = 0; i < 2; i++) {
        int level = RELAY_ACTIVE_LOW ? 1 : 0;
        gpio_set_level(relay_gpio[i], level);
        relay_state[i] = false;
    }

    ESP_LOGI(TAG, "Relay GPIOs initialized: CH1=GPIO%d, CH2=GPIO%d (active %s)",
             RELAY_CH1_GPIO, RELAY_CH2_GPIO,
             RELAY_ACTIVE_LOW ? "LOW" : "HIGH");
}

/* ─── Public API ─────────────────────────────────────────────────────── */

esp_err_t mqtt_relay_init(const char *broker_uri, const char *username, const char *password)
{
    ESP_LOGI(TAG, "Initializing MQTT relay controller → %s", broker_uri);

    boot_time_ms = (uint32_t)(esp_timer_get_time() / 1000);

    /* Load NVS node configuration & MAC address */
    load_nvs_config();

    /* Initialize relay GPIOs */
    init_relay_gpios();

    /* Generate unique MQTT client ID with chip MAC so multiple nodes never clash */
    static char unique_client_id[64];
    snprintf(unique_client_id, sizeof(unique_client_id), "esp32s3_%02X%02X%02X",
             s_node.mac[3], s_node.mac[4], s_node.mac[5]);
    ESP_LOGI(TAG, "Unique MQTT Client ID: %s", unique_client_id);

    /* Configure LWT (Last Will and Testament) topic on industrial status path */
    static char s_lwt_topic[96];
    snprintf(s_lwt_topic, sizeof(s_lwt_topic), "home/devices/%s/status", s_node.node_id);

    /* Configure MQTT client */
    esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = broker_uri,
        .credentials.username = username,
        .credentials.authentication.password = password,
        .credentials.client_id = unique_client_id,
        .session.keepalive = 60,
        .session.last_will.topic = s_lwt_topic,
        .session.last_will.msg = "offline",
        .session.last_will.msg_len = 7,
        .session.last_will.qos = 1,
        .session.last_will.retain = 1,
        .network.reconnect_timeout_ms = 5000,
        .buffer.size = 2048,
    };

    mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
    if (!mqtt_client) {
        ESP_LOGE(TAG, "Failed to create MQTT client!");
        return ESP_FAIL;
    }

    /* Register event handler */
    esp_mqtt_client_register_event(mqtt_client, ESP_EVENT_ANY_ID,
                                   mqtt_event_handler, NULL);

    ESP_LOGI(TAG, "MQTT relay controller initialized (ready for network IP)...");
    return ESP_OK;
}

static bool mqtt_started = false;

esp_err_t mqtt_relay_start(void)
{
    if (!mqtt_client) return ESP_FAIL;
    if (mqtt_started) return ESP_OK;

    ESP_LOGI(TAG, "🔄 Starting MQTT connection to broker...");
    esp_err_t err = esp_mqtt_client_start(mqtt_client);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "MQTT client start failed: %s", esp_err_to_name(err));
        return err;
    }
    mqtt_started = true;

    /* Create heartbeat task */
    xTaskCreate(heartbeat_task, "mqtt_heartbeat", 3072, NULL, 2, NULL);
    return ESP_OK;
}

void mqtt_relay_set(int channel, bool state)
{
    if (channel < 1 || channel > 2) {
        ESP_LOGW(TAG, "Invalid relay channel: %d (must be 1 or 2)", channel);
        return;
    }

    int idx = channel - 1;
    relay_state[idx] = state;

    int level = RELAY_ACTIVE_LOW ? (state ? 0 : 1) : (state ? 1 : 0);
    gpio_set_level(relay_gpio[idx], level);

    ESP_LOGI(TAG, "🔌 Relay CH%d (%s) → %s (GPIO%d = %d)",
             channel, (channel == 1 ? s_node.rl1_name : s_node.rl2_name),
             state ? "ON" : "OFF", relay_gpio[idx], level);

    /* Publish updated status to MQTT */
    if (mqtt_connected) {
        mqtt_relay_publish_status();
    }
}

bool mqtt_relay_get_state(int channel)
{
    if (channel < 1 || channel > 2) return false;
    return relay_state[channel - 1];
}

void mqtt_relay_publish_status(void)
{
    if (!mqtt_client || !mqtt_connected) return;

    uint32_t uptime_s = (uint32_t)((esp_timer_get_time() / 1000 - boot_time_ms) / 1000);

    /* Compact v2 status payload */
    char status_json[256];
    snprintf(status_json, sizeof(status_json),
             "{\"t\":\"ack\",\"id\":\"%s\",\"online\":true,\"ch1\":%d,\"ch2\":%d,\"rl\":[%d,%d],\"uptime_s\":%lu}",
             s_node.node_id,
             relay_state[0] ? 1 : 0, relay_state[1] ? 1 : 0,
             relay_state[0] ? 1 : 0, relay_state[1] ? 1 : 0,
             (unsigned long)uptime_s);

    char topic[96];
    snprintf(topic, sizeof(topic), "smarthome/status/%s", s_node.node_id);
    esp_mqtt_client_publish(mqtt_client, topic, status_json, 0, 1, 0);

    /* Spec v1.0 Industrial Status Topic (home/devices/{device_id}/status) */
    char dev_status_topic[96];
    snprintf(dev_status_topic, sizeof(dev_status_topic), "home/devices/%s/status", s_node.node_id);
    char dev_status_json[192];
    snprintf(dev_status_json, sizeof(dev_status_json),
             "{\"device_id\":\"%s\",\"state\":\"online\",\"uptime_s\":%lu,\"free_heap\":%lu}",
             s_node.node_id, (unsigned long)uptime_s, (unsigned long)esp_get_free_heap_size());
    esp_mqtt_client_publish(mqtt_client, dev_status_topic, dev_status_json, 0, 1, 1);

    /* Spec v1.0 Industrial Telemetry Topic (home/devices/{device_id}/telemetry) */
    char tele_topic[96];
    snprintf(tele_topic, sizeof(tele_topic), "home/devices/%s/telemetry", s_node.node_id);
    char tele_json[256];
    snprintf(tele_json, sizeof(tele_json),
             "{\"device_id\":\"%s\",\"voltage\":220.0,\"current\":0.0,\"power\":0.0,\"energy\":0.0,\"free_heap\":%lu,\"wifi_rssi\":-55,\"uptime_s\":%lu}",
             s_node.node_id, (unsigned long)esp_get_free_heap_size(), (unsigned long)uptime_s);
    esp_mqtt_client_publish(mqtt_client, tele_topic, tele_json, 0, 0, 0);
}

/* ─── MQTT Event Handler ─────────────────────────────────────────────── */

static void mqtt_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t event = event_data;

    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED:
        mqtt_connected = true;
        ESP_LOGI(TAG, "✅ MQTT connected to broker as '%s'", s_node.node_id);

        audio_feedback_stop_disconnect_loop();
        audio_feedback_play(AUDIO_FB_TING);

        /* Subscribe to provisioning topics matching this device's MAC */
        char topic_buf[96];

        /* 1. Provision topic by MAC (Upper & Lower) */
        snprintf(topic_buf, sizeof(topic_buf), "smarthome/cfg/%s", s_node.mac_str);
        esp_mqtt_client_subscribe(mqtt_client, topic_buf, 1);
        snprintf(topic_buf, sizeof(topic_buf), "smarthome/cfg/%s", s_node.mac_lower);
        esp_mqtt_client_subscribe(mqtt_client, topic_buf, 1);
        snprintf(topic_buf, sizeof(topic_buf), "smarthome/cfg/%s", s_node.mac_clean);
        esp_mqtt_client_subscribe(mqtt_client, topic_buf, 1);

        /* 2. Provision topic by Node ID and MAC (for factory unprovisioned nodes) */
        snprintf(topic_buf, sizeof(topic_buf), "smarthome/cfg/%s", s_node.node_id);
        esp_mqtt_client_subscribe(mqtt_client, topic_buf, 1);

        snprintf(topic_buf, sizeof(topic_buf), "smarthome/cfg/%s", s_node.mac_str);
        esp_mqtt_client_subscribe(mqtt_client, topic_buf, 1);

        /* 3. Command topics (Compact & Legacy) */
        snprintf(topic_buf, sizeof(topic_buf), "smarthome/cmd/%s", s_node.node_id);
        esp_mqtt_client_subscribe(mqtt_client, topic_buf, 1);
        snprintf(topic_buf, sizeof(topic_buf), "smarthome/command/%s", s_node.node_id);
        esp_mqtt_client_subscribe(mqtt_client, topic_buf, 1);

        /* 4. Global broadcast config / reset */
        esp_mqtt_client_subscribe(mqtt_client, "smarthome/cfg/all", 1);

        /* 5. OTA firmware trigger topics */
        snprintf(topic_buf, sizeof(topic_buf), "smarthome/ota/%s", s_node.node_id);
        esp_mqtt_client_subscribe(mqtt_client, topic_buf, 1);
        esp_mqtt_client_subscribe(mqtt_client, "smarthome/ota/all", 1);

        /* 6. Spec v1.0 Industrial Device OS Topics (home/devices/...) */
        char ind_buf[96];
        snprintf(ind_buf, sizeof(ind_buf), "home/devices/%s/config/desired", s_node.node_id);
        esp_mqtt_client_subscribe(mqtt_client, ind_buf, 1);

        snprintf(ind_buf, sizeof(ind_buf), "home/devices/%s/relay/+/set", s_node.node_id);
        esp_mqtt_client_subscribe(mqtt_client, ind_buf, 1);

        ESP_LOGI(TAG, "Subscribed to cmd/cfg/ota topics for Node '%s' (MAC: %s)", s_node.node_id, s_node.mac_str);

        /* Publish online status (retained, QoS 1) on home/devices/{device_id}/status */
        char st_top[96];
        snprintf(st_top, sizeof(st_top), "home/devices/%s/status", s_node.node_id);
        esp_mqtt_client_publish(mqtt_client, st_top, "online", 6, 1, 1);

        /* If unprovisioned / FACTORY_NEW, publish announcement to home/discovery/unclaimed */
        if (!s_node.is_provisioned) {
            cJSON *ucl = cJSON_CreateObject();
            if (ucl) {
                const hardware_identity_t *hw = device_identity_get_hardware();
                cJSON_AddStringToObject(ucl, "device_id", hw->device_id);
                cJSON_AddStringToObject(ucl, "hardware", hw->hardware);
                cJSON_AddStringToObject(ucl, "serial", hw->serial);
                cJSON_AddStringToObject(ucl, "mac", hw->mac_str);
                cJSON_AddStringToObject(ucl, "state", "FACTORY_NEW");
                char *ucl_str = cJSON_PrintUnformatted(ucl);
                cJSON_Delete(ucl);
                if (ucl_str) {
                    esp_mqtt_client_publish(mqtt_client, "home/discovery/unclaimed", ucl_str, 0, 1, 0);
                    free(ucl_str);
                    ESP_LOGI(TAG, "🆕 Announced Unclaimed Device on home/discovery/unclaimed");
                }
            }
        }

        /* Echo Reported Configuration Twin immediately upon connection */
        mqtt_relay_publish_reported_config(0);

        /* Publish registration & initial status */
        publish_registration();
        mqtt_relay_publish_status();
        break;

    case MQTT_EVENT_DISCONNECTED:
        mqtt_connected = false;
        ESP_LOGW(TAG, "⚠️ MQTT disconnected from broker (will reconnect automatically)");
        break;

    case MQTT_EVENT_DATA:
        if (event->topic_len > 0 && event->data_len > 0) {
            char topic[128];
            int tlen = event->topic_len < (sizeof(topic) - 1) ? event->topic_len : (sizeof(topic) - 1);
            memcpy(topic, event->topic, tlen);
            topic[tlen] = '\0';

            char *payload = malloc(event->data_len + 1);
            if (!payload) break;
            memcpy(payload, event->data, event->data_len);
            payload[event->data_len] = '\0';

            ESP_LOGI(TAG, "📥 MQTT RX [%s]: %s", topic, payload);

            /* Check if this is a desired twin config */
            if (strstr(topic, "/config/desired") != NULL) {
                mqtt_relay_handle_desired_config(payload);
            }
            /* Check if this is a provision configuration (legacy) */
            else if (strncmp(topic, "smarthome/cfg/", 14) == 0 ||
                     strncmp(topic, "smarthome/config/", 17) == 0) {
                mqtt_relay_handle_cfg_json(payload);
            }
            /* Check if this is a relay 1 set command */
            else if (strstr(topic, "/relay/1/set") != NULL) {
                int st = (strstr(payload, "\"state\": 1") || strstr(payload, "\"state\":1") || strcmp(payload, "1") == 0) ? 1 : 0;
                mqtt_relay_set(1, st);
                char rep_top[96];
                snprintf(rep_top, sizeof(rep_top), "home/devices/%s/relay/1/state", s_node.node_id);
                char rep_pay[32];
                snprintf(rep_pay, sizeof(rep_pay), "{\"channel\":1,\"state\":%d}", st);
                esp_mqtt_client_publish(mqtt_client, rep_top, rep_pay, 0, 1, 0);
            }
            /* Check if this is a relay 2 set command */
            else if (strstr(topic, "/relay/2/set") != NULL) {
                int st = (strstr(payload, "\"state\": 1") || strstr(payload, "\"state\":1") || strcmp(payload, "1") == 0) ? 1 : 0;
                mqtt_relay_set(2, st);
                char rep_top[96];
                snprintf(rep_top, sizeof(rep_top), "home/devices/%s/relay/2/state", s_node.node_id);
                char rep_pay[32];
                snprintf(rep_pay, sizeof(rep_pay), "{\"channel\":2,\"state\":%d}", st);
                esp_mqtt_client_publish(mqtt_client, rep_top, rep_pay, 0, 1, 0);
            }
            /* Check if this is a command message */
            else if (strncmp(topic, "smarthome/cmd/", 14) == 0 ||
                     strncmp(topic, "smarthome/command/", 18) == 0) {
                handle_command(event->data, event->data_len);
            }
            /* Check if this is an OTA firmware trigger */
            else if (strncmp(topic, "smarthome/ota/", 14) == 0) {
                handle_ota_command(payload);
            }

            free(payload);
        }
        break;

    case MQTT_EVENT_ERROR:
        ESP_LOGE(TAG, "❌ MQTT error occurred");
        break;

    default:
        break;
    }
}

/* ─── Command Handler ────────────────────────────────────────────────── */

static void handle_command(const char *data, int len)
{
    char *json_str = malloc(len + 1);
    if (!json_str) return;
    memcpy(json_str, data, len);
    json_str[len] = '\0';

    cJSON *root = cJSON_Parse(json_str);
    if (!root) {
        free(json_str);
        return;
    }

    int channel = 0;
    bool new_state = false;
    bool is_toggle = false;
    int seq = 0;

    /* ── 1. Compact Protocol (protocol_spec.md): {"t":"rl","ch":1,"s":1,"seq":n} ── */
    const cJSON *t_item = cJSON_GetObjectItem(root, "t");
    const cJSON *action_item = cJSON_GetObjectItem(root, "action");

    if (cJSON_IsString(t_item) && strcmp(t_item->valuestring, "rl") == 0) {
        const cJSON *ch_item = cJSON_GetObjectItem(root, "ch");
        const cJSON *s_item = cJSON_GetObjectItem(root, "s");
        const cJSON *seq_item = cJSON_GetObjectItem(root, "seq");

        if (cJSON_IsNumber(ch_item)) channel = ch_item->valueint;
        if (cJSON_IsNumber(s_item)) new_state = (s_item->valueint == 1);
        if (cJSON_IsNumber(seq_item)) seq = seq_item->valueint;
    }
    /* ── 2. Legacy Protocol: {"channel":"ch1","action":"turn_on"} ── */
    else {
        const cJSON *ch_item = cJSON_GetObjectItem(root, "channel");
        if (cJSON_IsString(ch_item)) {
            if (strcmp(ch_item->valuestring, "ch1") == 0) channel = 1;
            else if (strcmp(ch_item->valuestring, "ch2") == 0) channel = 2;
        }

        if (cJSON_IsString(action_item)) {
            const char *act = action_item->valuestring;
            if (strcmp(act, "turn_on") == 0 || strcmp(act, "on") == 0) new_state = true;
            else if (strcmp(act, "turn_off") == 0 || strcmp(act, "off") == 0) new_state = false;
            else if (strcmp(act, "toggle") == 0) is_toggle = true;
            else if (strcmp(act, "factory_reset") == 0 || strcmp(act, "reset_provision") == 0) {
                cJSON_Delete(root);
                free(json_str);
                mqtt_relay_factory_reset();
                return;
            }
        }
    }

    /* Check for direct reset command {"t":"reset"} */
    if (cJSON_IsString(t_item) && strcmp(t_item->valuestring, "reset") == 0) {
        cJSON_Delete(root);
        free(json_str);
        mqtt_relay_factory_reset();
        return;
    }

    if (channel >= 1 && channel <= 2) {
        if (is_toggle) {
            new_state = !mqtt_relay_get_state(channel);
        }
        mqtt_relay_set(channel, new_state);

        /* Reply with compact ACK */
        if (mqtt_client && mqtt_connected) {
            char ack_json[192];
            snprintf(ack_json, sizeof(ack_json),
                     "{\"t\":\"ack\",\"id\":\"%s\",\"rl\":[%d,%d],\"seq\":%d}",
                     s_node.node_id,
                     relay_state[0] ? 1 : 0, relay_state[1] ? 1 : 0,
                     seq);
            char status_topic[96];
            snprintf(status_topic, sizeof(status_topic), "smarthome/status/%s", s_node.node_id);
            esp_mqtt_client_publish(mqtt_client, status_topic, ack_json, 0, 1, 0);
        }
    } else {
        ESP_LOGW(TAG, "Unrecognized command format: %s", json_str);
    }

    cJSON_Delete(root);
    free(json_str);
}

/* ─── OTA Command Handler & Progress Publisher ────────────────────────── */

static void handle_ota_command(const char *payload)
{
    cJSON *root = cJSON_Parse(payload);
    if (!root) return;

    const cJSON *url = cJSON_GetObjectItem(root, "url");
    const cJSON *size = cJSON_GetObjectItem(root, "size");
    const cJSON *md5 = cJSON_GetObjectItem(root, "md5");

    if (cJSON_IsString(url) && url->valuestring && strlen(url->valuestring) > 7) {
        size_t expected_size = cJSON_IsNumber(size) ? size->valueint : 0;
        const char *expected_md5 = cJSON_IsString(md5) ? md5->valuestring : NULL;
        ESP_LOGI(TAG, "🚀 [MQTT OTA] Trigger received: URL='%s', size=%zu, md5=%s",
                 url->valuestring, expected_size, expected_md5 ? expected_md5 : "none");
        ota_updater_start_http_pull(url->valuestring, expected_size, expected_md5);
    } else {
        ESP_LOGW(TAG, "Invalid OTA payload (missing 'url'): %s", payload);
    }

    cJSON_Delete(root);
}

void mqtt_relay_publish_ota_progress(int percent, const char *status, const char *message)
{
    if (!mqtt_client || !mqtt_connected) return;

    char topic[96];
    snprintf(topic, sizeof(topic), "smarthome/ota_progress/%s", s_node.node_id);

    char payload[256];
    snprintf(payload, sizeof(payload),
             "{\"node_id\":\"%s\",\"progress\":%d,\"status\":\"%s\",\"message\":\"%s\"}",
             s_node.node_id, percent, status ? status : "downloading",
             message ? message : "");

    esp_mqtt_client_publish(mqtt_client, topic, payload, 0, 1, 0);
}

/* ─── Registration & Discovery Beacon ────────────────────────────────── */

static void publish_registration(void)
{
    if (!mqtt_client || !mqtt_connected) return;

    const hardware_identity_t *hw = device_identity_get_hardware();
    const user_identity_t *usr = device_identity_get_user();
    device_lifecycle_state_t state = device_identity_get_state();

    cJSON *root = cJSON_CreateObject();
    if (!root) return;

    cJSON_AddStringToObject(root, "t", "hello");
    cJSON_AddStringToObject(root, "id", hw->device_id);
    cJSON_AddStringToObject(root, "mac", hw->mac_str);
    cJSON_AddStringToObject(root, "hardware", hw->hardware);
    cJSON_AddStringToObject(root, "serial", hw->serial);
    cJSON_AddStringToObject(root, "state", device_identity_state_str(state));
    cJSON_AddNumberToObject(root, "cfg", usr->cfg_version);

    cJSON *rl = cJSON_CreateArray();
    cJSON_AddItemToArray(rl, cJSON_CreateNumber(relay_state[0] ? 1 : 0));
    cJSON_AddItemToArray(rl, cJSON_CreateNumber(relay_state[1] ? 1 : 0));
    cJSON_AddItemToObject(root, "rl", rl);

    cJSON *user = cJSON_CreateObject();
    cJSON_AddStringToObject(user, "name", usr->name);
    cJSON_AddStringToObject(user, "room", usr->room);
    cJSON_AddStringToObject(user, "location", usr->location);
    cJSON_AddStringToObject(user, "description", usr->description);
    cJSON_AddStringToObject(user, "rl1", usr->rl1_name);
    cJSON_AddStringToObject(user, "rl2", usr->rl2_name);
    cJSON_AddItemToObject(root, "user_identity", user);

    char *json_str = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);

    if (json_str) {
        esp_mqtt_client_publish(mqtt_client, "smarthome/hello", json_str, 0, 1, 0);
        char disc_topic[64];
        snprintf(disc_topic, sizeof(disc_topic), "smarthome/discovery/%s", hw->device_id);
        esp_mqtt_client_publish(mqtt_client, disc_topic, json_str, 0, 1, 0);
        free(json_str);
        ESP_LOGI(TAG, "📡 Published Commercial Hello Beacon: ID='%s', State=%s, Serial=%s",
                 hw->device_id, device_identity_state_str(state), hw->serial);
    }
}

/* ─── Heartbeat Task ─────────────────────────────────────────────────── */

static void heartbeat_task(void *arg)
{
    ESP_LOGI(TAG, "MQTT heartbeat task started (%ds interval)", HEARTBEAT_INTERVAL_S);
    vTaskDelay(pdMS_TO_TICKS(5000));

    while (1) {
        if (mqtt_connected) {
            publish_registration();
            mqtt_relay_publish_status();
        }
        vTaskDelay(pdMS_TO_TICKS(HEARTBEAT_INTERVAL_S * 1000));
    }
}
