/*
 * MQTT Relay Controller — Implementation
 * DTV Smart Home — ESP32-S3 Combined Node (Voice + Relay)
 *
 * Handles:
 *   1. MQTT connection to EMQX broker on Pi 4
 *   2. Node registration on boot
 *   3. Subscribe to relay commands from Gateway
 *   4. GPIO relay control (2 channels)
 *   5. Periodic status/heartbeat publishing
 */

#include "mqtt_relay.h"

#include <string.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_mac.h"
#include "driver/gpio.h"
#include "mqtt_client.h"
#include "cJSON.h"

static const char *TAG = "MQTT_RELAY";

/* ─── MQTT Configuration ─────────────────────────────────────────────── */

#define NODE_ID             "esp32s3_master"
#define TOPIC_REGISTER      "smarthome/register"
#define TOPIC_COMMAND        "smarthome/command/" NODE_ID
#define TOPIC_STATUS         "smarthome/status/" NODE_ID
#define TOPIC_TELEMETRY      "smarthome/telemetry/" NODE_ID

#define HEARTBEAT_INTERVAL_S  30

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
static void heartbeat_task(void *arg);
static void publish_registration(void);

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

    /* Initialize relays to OFF state */
    for (int i = 0; i < 2; i++) {
        int level = RELAY_ACTIVE_LOW ? 1 : 0;  /* OFF level */
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

    /* Initialize relay GPIOs */
    init_relay_gpios();

    /* Configure MQTT client */
    esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = broker_uri,
        .credentials.username = username,
        .credentials.authentication.password = password,
        .credentials.client_id = NODE_ID,
        .session.keepalive = 60,
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

    /* Start MQTT client (connects in background) */
    esp_err_t err = esp_mqtt_client_start(mqtt_client);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "MQTT client start failed: %s", esp_err_to_name(err));
        return err;
    }

    /* Create heartbeat task */
    xTaskCreate(heartbeat_task, "mqtt_heartbeat", 3072, NULL, 2, NULL);

    ESP_LOGI(TAG, "MQTT relay controller initialized. Waiting for broker connection...");
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

    int level;
    if (RELAY_ACTIVE_LOW) {
        level = state ? 0 : 1;  /* Active LOW: ON=LOW, OFF=HIGH */
    } else {
        level = state ? 1 : 0;  /* Active HIGH: ON=HIGH, OFF=LOW */
    }

    gpio_set_level(relay_gpio[idx], level);

    ESP_LOGI(TAG, "🔌 Relay CH%d → %s (GPIO%d = %d)",
             channel, state ? "ON" : "OFF", relay_gpio[idx], level);

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

    char status_json[256];
    snprintf(status_json, sizeof(status_json),
             "{\"online\":true,\"ch1\":%d,\"ch2\":%d,\"uptime_s\":%lu,\"node_id\":\"%s\"}",
             relay_state[0] ? 1 : 0,
             relay_state[1] ? 1 : 0,
             (unsigned long)uptime_s,
             NODE_ID);

    esp_mqtt_client_publish(mqtt_client, TOPIC_STATUS,
                           status_json, 0, 1, 0);
}

/* ─── MQTT Event Handler ─────────────────────────────────────────────── */

static void mqtt_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t event = event_data;

    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED:
        mqtt_connected = true;
        ESP_LOGI(TAG, "✅ MQTT connected to broker");

        /* Subscribe to command topic */
        esp_mqtt_client_subscribe(mqtt_client, TOPIC_COMMAND, 1);
        ESP_LOGI(TAG, "Subscribed to: %s", TOPIC_COMMAND);

        /* Publish registration */
        publish_registration();

        /* Publish initial status */
        mqtt_relay_publish_status();
        break;

    case MQTT_EVENT_DISCONNECTED:
        mqtt_connected = false;
        ESP_LOGW(TAG, "⚠️ MQTT disconnected from broker");
        break;

    case MQTT_EVENT_DATA:
        if (event->topic_len > 0 && event->data_len > 0) {
            /* Check if this is a command message */
            if (strncmp(event->topic, TOPIC_COMMAND, event->topic_len) == 0) {
                handle_command(event->data, event->data_len);
            }
        }
        break;

    case MQTT_EVENT_ERROR:
        ESP_LOGE(TAG, "❌ MQTT error occurred");
        if (event->error_handle->error_type == MQTT_ERROR_TYPE_TCP_TRANSPORT) {
            ESP_LOGE(TAG, "  TCP transport error: %d", event->error_handle->esp_tls_last_esp_err);
        }
        break;

    case MQTT_EVENT_SUBSCRIBED:
        ESP_LOGI(TAG, "MQTT topic subscribed successfully");
        break;

    default:
        break;
    }
}

/* ─── Command Handler ────────────────────────────────────────────────── */
/*
 * Expected JSON format:
 *   {"channel": "ch1", "action": "turn_on"}
 *   {"channel": "ch2", "action": "turn_off"}
 */

static void handle_command(const char *data, int len)
{
    char *json_str = malloc(len + 1);
    if (!json_str) return;
    memcpy(json_str, data, len);
    json_str[len] = '\0';

    ESP_LOGI(TAG, "📥 Received MQTT command: %s", json_str);

    cJSON *root = cJSON_Parse(json_str);
    if (!root) {
        ESP_LOGW(TAG, "Failed to parse command JSON");
        free(json_str);
        return;
    }

    const cJSON *channel_json = cJSON_GetObjectItem(root, "channel");
    const cJSON *action_json = cJSON_GetObjectItem(root, "action");

    if (!cJSON_IsString(channel_json) || !cJSON_IsString(action_json)) {
        ESP_LOGW(TAG, "Invalid command format — missing channel or action");
        cJSON_Delete(root);
        free(json_str);
        return;
    }

    const char *channel_str = channel_json->valuestring;
    const char *action_str = action_json->valuestring;

    /* Parse channel number */
    int channel = 0;
    if (strcmp(channel_str, "ch1") == 0) channel = 1;
    else if (strcmp(channel_str, "ch2") == 0) channel = 2;
    else {
        ESP_LOGW(TAG, "Unknown channel: %s", channel_str);
        cJSON_Delete(root);
        free(json_str);
        return;
    }

    /* Parse action */
    if (strcmp(action_str, "turn_on") == 0) {
        mqtt_relay_set(channel, true);
    } else if (strcmp(action_str, "turn_off") == 0) {
        mqtt_relay_set(channel, false);
    } else if (strcmp(action_str, "toggle") == 0) {
        mqtt_relay_set(channel, !mqtt_relay_get_state(channel));
    } else {
        ESP_LOGW(TAG, "Unknown action: %s", action_str);
    }

    cJSON_Delete(root);
    free(json_str);
}

/* ─── Registration ───────────────────────────────────────────────────── */

static void publish_registration(void)
{
    if (!mqtt_client || !mqtt_connected) return;

    /* Get ESP32-S3 MAC address */
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);

    char reg_json[512];
    snprintf(reg_json, sizeof(reg_json),
             "{"
             "\"node_id\":\"%s\","
             "\"mac\":\"%02X:%02X:%02X:%02X:%02X:%02X\","
             "\"type\":\"voice_relay_combined\","
             "\"area\":\"phong_ngu\","
             "\"description\":\"ESP32-S3 Master Voice + 2-CH Relay Phòng Ngủ\","
             "\"channels\":{"
               "\"ch1\":{\"device_type\":\"den\",\"description\":\"Đèn phòng ngủ\",\"gpio\":%d},"
               "\"ch2\":{\"device_type\":\"quat\",\"description\":\"Quạt phòng ngủ\",\"gpio\":%d}"
             "},"
             "\"capabilities\":[\"voice\",\"relay\",\"speaker\"]"
             "}",
             NODE_ID,
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5],
             RELAY_CH1_GPIO, RELAY_CH2_GPIO);

    esp_mqtt_client_publish(mqtt_client, TOPIC_REGISTER,
                           reg_json, 0, 1, 0);
    ESP_LOGI(TAG, "📡 Published node registration (phong_ngu: RL1=den, RL2=quat) to %s", TOPIC_REGISTER);
}

/* ─── Heartbeat Task ─────────────────────────────────────────────────── */

static void heartbeat_task(void *arg)
{
    ESP_LOGI(TAG, "MQTT heartbeat task started (%ds interval)", HEARTBEAT_INTERVAL_S);
    vTaskDelay(pdMS_TO_TICKS(5000));  /* Wait for initial connection */

    while (1) {
        if (mqtt_connected) {
            mqtt_relay_publish_status();
        }
        vTaskDelay(pdMS_TO_TICKS(HEARTBEAT_INTERVAL_S * 1000));
    }
}
