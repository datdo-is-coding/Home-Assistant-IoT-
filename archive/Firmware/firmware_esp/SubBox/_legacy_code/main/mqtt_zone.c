/*
 * MQTT Zone Gateway — Implementation
 * DTV Smart Home — T2 Zone Controller
 */

#include "mqtt_zone.h"
#include "zone_manager.h"
#include "espnow_master.h"
#include "t2_config.h"
#include "ir_controller.h"

#include <string.h>
#include <stdio.h>
#include "esp_log.h"
#include "mqtt_client.h"
#include "cJSON.h"

static const char *TAG = "MQTT_ZONE";

static esp_mqtt_client_handle_t s_client = NULL;
static bool s_connected = false;

/* ─── Forward Declarations ───────────────────────────────────────────── */

static void mqtt_event_handler(void *handler_args, esp_event_base_t base,
                               int32_t event_id, void *event_data);
static void handle_relay_set_topic(const char *topic, const char *data, int data_len);

/* ─── Public API ─────────────────────────────────────────────────────── */

bool mqtt_zone_is_connected(void)
{
    return s_connected;
}

esp_err_t mqtt_zone_init(const char *broker_uri, const char *user, const char *pass)
{
    ESP_LOGI(TAG, "Connecting to MQTT Broker at %s...", broker_uri);

    esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = broker_uri,
        .credentials.username = user,
        .credentials.authentication.password = pass,
        .network.reconnect_timeout_ms = 5000,
    };

    s_client = esp_mqtt_client_init(&mqtt_cfg);
    if (!s_client) {
        ESP_LOGE(TAG, "Failed to create MQTT client handle");
        return ESP_FAIL;
    }

    esp_mqtt_client_register_event(s_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
    return esp_mqtt_client_start(s_client);
}

void mqtt_zone_publish_node_status(const zone_node_entry_t *node)
{
    if (!s_connected || !node) return;

    char topic[128];
    snprintf(topic, sizeof(topic), "home/%s/%s/status",
             zone_manager_get_zone_name(), node->device_id);

    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "device_id", node->device_id);
    cJSON_AddStringToObject(root, "zone", zone_manager_get_zone_name());
    cJSON_AddStringToObject(root, "mac", "");
    char mac_str[18];
    snprintf(mac_str, sizeof(mac_str), "%02X:%02X:%02X:%02X:%02X:%02X",
             node->mac[0], node->mac[1], node->mac[2],
             node->mac[3], node->mac[4], node->mac[5]);
    cJSON_ReplaceItemInObject(root, "mac", cJSON_CreateString(mac_str));
    cJSON_AddBoolToObject(root, "online", node->is_online);
    cJSON_AddNumberToObject(root, "capabilities", node->capabilities);
    cJSON_AddNumberToObject(root, "rl1_state", node->rl1_state);
    cJSON_AddNumberToObject(root, "rl2_state", node->rl2_state);
    cJSON_AddNumberToObject(root, "uptime_s", node->uptime_s);
    cJSON_AddNumberToObject(root, "rssi", node->rssi);

    char *json_str = cJSON_PrintUnformatted(root);
    if (json_str) {
        esp_mqtt_client_publish(s_client, topic, json_str, 0, 1, 0);
        cJSON_free(json_str);
    }
    cJSON_Delete(root);
}

void mqtt_zone_publish_relay_state(const char *device_id, uint8_t channel, uint8_t state)
{
    if (!s_connected || !device_id) return;

    char topic[128];
    snprintf(topic, sizeof(topic), "home/%s/%s/relay/%d/state",
             zone_manager_get_zone_name(), device_id, channel);

    const char *payload = (state != 0) ? "ON" : "OFF";
    esp_mqtt_client_publish(s_client, topic, payload, 0, 1, 1 /* retain */);
}

void mqtt_zone_publish_telemetry(const char *device_id, const esp_now_packet_t *tele)
{
    if (!s_connected || !device_id || !tele) return;

    char topic[128];
    snprintf(topic, sizeof(topic), "home/%s/%s/power",
             zone_manager_get_zone_name(), device_id);

    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "device_id", device_id);
    cJSON_AddNumberToObject(root, "voltage", tele->voltage);
    cJSON_AddNumberToObject(root, "current", tele->current);
    cJSON_AddNumberToObject(root, "power", tele->power);
    cJSON_AddNumberToObject(root, "energy", tele->energy);
    cJSON_AddNumberToObject(root, "frequency", tele->frequency);
    cJSON_AddNumberToObject(root, "pf", tele->pf);
    cJSON_AddNumberToObject(root, "relay_state", tele->relay_state);

    char *json_str = cJSON_PrintUnformatted(root);
    if (json_str) {
        esp_mqtt_client_publish(s_client, topic, json_str, 0, 0, 0);
        cJSON_free(json_str);
    }
    cJSON_Delete(root);
}

void mqtt_zone_publish_zone_summary(void)
{
    if (!s_connected) return;

    char topic[128];
    snprintf(topic, sizeof(topic), "home/%s/summary", zone_manager_get_zone_name());

    int count = 0;
    zone_node_entry_t *nodes = zone_manager_get_all(&count);

    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "zone", zone_manager_get_zone_name());
    cJSON_AddNumberToObject(root, "node_count", count);

    cJSON *arr = cJSON_CreateArray();
    for (int i = 0; i < count; i++) {
        cJSON *item = cJSON_CreateObject();
        cJSON_AddStringToObject(item, "device_id", nodes[i].device_id);
        cJSON_AddBoolToObject(item, "online", nodes[i].is_online);
        cJSON_AddNumberToObject(item, "rl1", nodes[i].rl1_state);
        cJSON_AddNumberToObject(item, "rl2", nodes[i].rl2_state);
        cJSON_AddItemToArray(arr, item);
    }
    cJSON_AddItemToObject(root, "nodes", arr);

    char *json_str = cJSON_PrintUnformatted(root);
    if (json_str) {
        esp_mqtt_client_publish(s_client, topic, json_str, 0, 0, 0);
        cJSON_free(json_str);
    }
    cJSON_Delete(root);
}

/* ─── MQTT Event Handler ─────────────────────────────────────────────── */

static void mqtt_event_handler(void *handler_args, esp_event_base_t base,
                               int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;

    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED: {
        ESP_LOGI(TAG, "✅ MQTT Connected to Gateway Broker!");
        s_connected = true;

        /* Subscribe to relay commands for all nodes in this zone: home/<zone>/+/relay/+/set */
        char sub_topic[128];
        snprintf(sub_topic, sizeof(sub_topic), "home/%s/+/relay/+/set", zone_manager_get_zone_name());
        esp_mqtt_client_subscribe(s_client, sub_topic, 1);
        ESP_LOGI(TAG, "Subscribed to '%s'", sub_topic);

        /* Also subscribe to universal node topic: home/nodes/+/relay/+/set */
        esp_mqtt_client_subscribe(s_client, "home/nodes/+/relay/+/set", 1);

        /* Subscribe to IR commands: home/<zone>/ir/# and home/ir/# */
        char ir_topic[128];
        snprintf(ir_topic, sizeof(ir_topic), "home/%s/ir/#", zone_manager_get_zone_name());
        esp_mqtt_client_subscribe(s_client, ir_topic, 1);
        esp_mqtt_client_subscribe(s_client, "home/ir/#", 1);
        ESP_LOGI(TAG, "Subscribed to IR commands: '%s'", ir_topic);
        break;
    }

    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "⚠️ MQTT Disconnected from Gateway Broker");
        s_connected = false;
        break;

    case MQTT_EVENT_DATA: {
        char topic_buf[128] = {0};
        int tlen = event->topic_len < (int)sizeof(topic_buf) - 1 ? event->topic_len : (int)sizeof(topic_buf) - 1;
        memcpy(topic_buf, event->topic, tlen);

        char data_buf[512] = {0};
        int dlen = event->data_len < (int)sizeof(data_buf) - 1 ? event->data_len : (int)sizeof(data_buf) - 1;
        memcpy(data_buf, event->data, dlen);

        ESP_LOGI(TAG, "📩 MQTT RX: %s -> %s", topic_buf, data_buf);

        if (strstr(topic_buf, "/ir/") != NULL || strstr(topic_buf, "/ir") != NULL) {
            ESP_LOGI(TAG, "Executing IR Command from MQTT...");
            ir_handle_json_cmd(data_buf);
        } else {
            handle_relay_set_topic(topic_buf, data_buf, dlen);
        }
        break;
    }

    default:
        break;
    }
}

/* ─── Handle Incoming MQTT Relay Commands ────────────────────────────── */

static void handle_relay_set_topic(const char *topic, const char *data, int data_len)
{
    /* Supported formats:
     *   home/<zone>/<device_id>/relay/<channel>/set
     *   home/nodes/<device_id>/relay/<channel>/set
     */
    char dev_id[32] = {0};
    int channel = 0;

    char *relay_pos = strstr(topic, "/relay/");
    if (!relay_pos) return;

    /* Parse channel */
    if (sscanf(relay_pos, "/relay/%d/set", &channel) != 1 || channel < 1 || channel > 2) {
        return;
    }

    /* Extract device_id preceding /relay/ */
    const char *p = relay_pos - 1;
    while (p > topic && *p != '/') {
        p--;
    }
    if (*p == '/') {
        size_t id_len = (relay_pos - p - 1);
        if (id_len < sizeof(dev_id)) {
            memcpy(dev_id, p + 1, id_len);
            dev_id[id_len] = '\0';
        }
    }

    if (strlen(dev_id) == 0) return;

    /* Determine desired state: ON/1/true vs OFF/0/false */
    uint8_t state = 0;
    if (strcasecmp(data, "ON") == 0 || strcmp(data, "1") == 0 || strcasecmp(data, "true") == 0) {
        state = 1;
    }

    ESP_LOGI(TAG, "⚡ Routing Relay Cmd: Node '%s' CH%d -> %s", dev_id, channel, state ? "ON" : "OFF");

    /* Lookup node in zone table */
    zone_node_entry_t *node = zone_manager_find_by_id(dev_id);
    if (!node) {
        ESP_LOGW(TAG, "Node '%s' not found in zone '%s'", dev_id, zone_manager_get_zone_name());
        return;
    }

    /* Send ESP-NOW command to T1 node */
    espnow_master_send_relay_cmd(node->mac, (uint8_t)channel, state);
}
