/*
 * Node Provision — Implementation (NVS "smhome")
 */
#include "node_prov.h"
#include <string.h>
#include <stdio.h>
#include "esp_log.h"
#include "esp_err.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "driver/gpio.h"

static const char *TAG = "PROV";
#define NVS_NS "smhome"

node_prov_t g_prov;

static const int RELAY_GPIO[2] = {4, 5};

static void apply_relay_gpio(int idx, bool on) {
    // Active-LOW: ON → GPIO LOW (0), OFF → HIGH (1)
    gpio_set_level((gpio_num_t)RELAY_GPIO[idx], on ? 0 : 1);
}

bool prov_load(void) {
    memset(&g_prov, 0, sizeof(g_prov));
    nvs_handle_t h;
    if (nvs_open(NVS_NS, NVS_READONLY, &h) != ESP_OK) {
        ESP_LOGI(TAG, "No provision yet (fresh node) — will announce as pending");
        return false;
    }
    size_t l;
    l = sizeof(g_prov.node_id);  if (nvs_get_str(h, "node_id", g_prov.node_id, &l) != ESP_OK) g_prov.node_id[0] = 0;
    l = sizeof(g_prov.room);     if (nvs_get_str(h, "room",    g_prov.room,    &l) != ESP_OK) g_prov.room[0] = 0;
    l = sizeof(g_prov.rl1);      if (nvs_get_str(h, "rl1",     g_prov.rl1,     &l) != ESP_OK) g_prov.rl1[0] = 0;
    l = sizeof(g_prov.rl2);      if (nvs_get_str(h, "rl2",     g_prov.rl2,     &l) != ESP_OK) g_prov.rl2[0] = 0;
    uint16_t v = 0;
    if (nvs_get_u16(h, "cfg_v", &v) == ESP_OK) g_prov.cfg_version = v;
    uint8_t ls = 0;
    if (nvs_get_u8(h, "last_seq", &ls) == ESP_OK) g_prov.last_seq = ls;
    nvs_close(h);

    g_prov.provisioned = (g_prov.node_id[0] != '\0' && g_prov.cfg_version > 0);
    ESP_LOGI(TAG, "Loaded: id='%s' room='%s' rl1='%s' rl2='%s' v=%u %s",
             g_prov.node_id, g_prov.room, g_prov.rl1, g_prov.rl2,
             g_prov.cfg_version, g_prov.provisioned ? "(provisioned)" : "(PENDING)");
    return g_prov.provisioned;
}

esp_err_t prov_save_cfg(const char *node_id, const char *room,
                        const char *rl1, const char *rl2, uint16_t version) {
    nvs_handle_t h;
    esp_err_t err = nvs_open(NVS_NS, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    if (node_id) nvs_set_str(h, "node_id", node_id);
    if (room)    nvs_set_str(h, "room",    room);
    nvs_set_str(h, "rl1", rl1 ? rl1 : "");
    nvs_set_str(h, "rl2", rl2 ? rl2 : "");
    nvs_set_u16(h, "cfg_v", version);
    err = nvs_commit(h);
    nvs_close(h);
    if (err == ESP_OK) {
        strlcpy(g_prov.node_id, node_id ? node_id : "", sizeof(g_prov.node_id));
        strlcpy(g_prov.room,    room ? room : "",       sizeof(g_prov.room));
        strlcpy(g_prov.rl1,     rl1 ? rl1 : "",          sizeof(g_prov.rl1));
        strlcpy(g_prov.rl2,     rl2 ? rl2 : "",          sizeof(g_prov.rl2));
        g_prov.cfg_version = version;
        g_prov.provisioned = true;
        ESP_LOGI(TAG, "Saved provision: id=%s room=%s rl1=%s rl2=%s v=%u (reboot to apply)",
                 node_id, room, g_prov.rl1, g_prov.rl2, version);
    }
    return err;
}

void prov_set_relay(int ch, bool on) {
    if (ch < 1 || ch > 2) return;
    g_prov.relay_state[ch-1] = on;
}

int prov_handle_relay_cmd(int ch, int s, int seq) {
    if (ch < 1 || ch > 2) return -1;
    // seq==0 là bản legacy không có seq → luôn thực thi
    if (seq != 0) {
        // seq 16-bit wrap-safe: coi là cũ nếu cách > 32768 vòng
        int16_t diff = (int16_t)(seq - g_prov.last_seq);
        if (diff <= 0) {
            ESP_LOGW(TAG, "Dropped duplicate/old seq=%d last=%u", seq, g_prov.last_seq);
            return 1;
        }
        g_prov.last_seq = (uint16_t)seq;
    }
    bool on = (s != 0);
    apply_relay_gpio(ch-1, on);
    g_prov.relay_state[ch-1] = on;
    char fn[64]; prov_fullname(ch, fn, sizeof(fn));
    ESP_LOGI(TAG, "Relay %s (%s) → %s seq=%d", fn, ch==1?"RL1":"RL2", on?"ON":"OFF", seq);
    return 0;
}

int prov_build_hello(char *buf, size_t bufsz, const char *mac_str,
                     const char *fw_ver, const char *ip_str, int rssi, uint32_t uptime_s) {
    int n;
    int rl0 = g_prov.relay_state[0] ? 1 : 0;
    int rl1 = g_prov.relay_state[1] ? 1 : 0;
    if (!g_prov.provisioned) {
        n = snprintf(buf, bufsz,
            "{\"t\":\"hello\",\"mac\":\"%s\",\"fw\":\"%s\",\"ip\":\"%s\",\"rssi\":%d,\"rl\":[%d,%d],\"cfg\":null,\"up\":%u}",
            mac_str?mac_str:"", fw_ver?fw_ver:"1.0.0", ip_str?ip_str:"", rssi, rl0, rl1, (unsigned)uptime_s);
    } else {
        n = snprintf(buf, bufsz,
            "{\"t\":\"hello\",\"id\":\"%s\",\"rl\":[%d,%d],\"cfg\":%u,\"rssi\":%d,\"up\":%u}",
            g_prov.node_id, rl0, rl1, g_prov.cfg_version, rssi, (unsigned)uptime_s);
    }
    return n;
}

int prov_build_ack(char *buf, size_t bufsz, int seq) {
    if (!g_prov.provisioned) return 0;
    return snprintf(buf, bufsz,
        "{\"t\":\"ack\",\"id\":\"%s\",\"rl\":[%d,%d],\"seq\":%d}",
        g_prov.node_id,
        g_prov.relay_state[0]?1:0, g_prov.relay_state[1]?1:0, seq);
}

void prov_fullname(int ch, char *out, size_t outsz) {
    const char *dev = (ch==1 ? g_prov.rl1 : g_prov.rl2);
    if (!g_prov.provisioned || !dev[0])
        snprintf(out, outsz, "unknown-ch%d", ch);
    else
        snprintf(out, outsz, "%s-%s", g_prov.node_id, dev);
}
