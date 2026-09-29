/**
 * @file wifi_provisioning.cpp
 * @brief SubBox SoftAP Captive Portal Wi-Fi Provisioning Engine
 */

#include "wifi_provisioning.h"
#include "storage/nvs_manager.h"
#include "nlu/entity/entity_types.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_mac.h"
#include "esp_http_server.h"
#include "cJSON.h"
#include "lwip/sockets.h"
#include "lwip/netdb.h"

static const char *TAG = "WIFI_PROV";

static httpd_handle_t s_http_server = NULL;
static TaskHandle_t s_dns_task_handle = NULL;
static volatile bool s_is_active = false;
static int s_dns_socket = -1;

/* ─── Captive Portal Web UI ───────────────────────────────────────────── */
static const char PORTAL_HTML[] = 
"<!DOCTYPE html>"
"<html lang='vi'>"
"<head>"
"<meta charset='UTF-8'>"
"<meta name='viewport' content='width=device-width,initial-scale=1'>"
"<title>AETHERIA SubBox Cấu Hình</title>"
"<style>"
":root{--bg:#0b0f19;--card:#141c2e;--accent:#3b82f6;--text:#f8fafc;--text-dim:#94a3b8;--border:#1e293b;}"
"*{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}"
"body{background:var(--bg);color:var(--text);display:flex;justify-content:center;align-items:center;min-height:100vh;padding:16px;}"
".box{background:var(--card);width:100%;max-width:420px;border-radius:16px;border:1px solid var(--border);padding:24px;box-shadow:0 20px 25px -5px rgba(0,0,0,0.5);}"
".logo{display:flex;align-items:center;gap:12px;margin-bottom:20px;}"
".icon{width:40px;height:40px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;}"
"h1{font-size:18px;font-weight:700;letter-spacing:-0.5px;}"
"p.sub{font-size:13px;color:var(--text-dim);margin-top:2px;}"
".field{margin-bottom:16px;}"
"label{display:block;font-size:12px;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;}"
"input,select{width:100%;padding:12px 14px;background:#0f172a;border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:14px;outline:none;transition:border-color 0.2s;}"
"input:focus,select:focus{border-color:var(--accent);}"
".btn{width:100%;padding:14px;background:linear-gradient(135deg,#3b82f6,#2563eb);color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;margin-top:10px;transition:opacity 0.2s;}"
".btn:active{opacity:0.8;}"
".btn-scan{background:#1e293b;color:var(--text);padding:8px 12px;font-size:12px;border:none;border-radius:6px;cursor:pointer;margin-top:6px;width:100%;}"
"#status{margin-top:14px;font-size:13px;text-align:center;display:none;padding:10px;border-radius:8px;}"
".success{background:rgba(34,197,94,0.1);color:#4ade80;border:1px solid rgba(34,197,94,0.2);}"
".loading{background:rgba(59,130,246,0.1);color:#60a5fa;border:1px solid rgba(59,130,246,0.2);}"
"</style>"
"</head>"
"<body>"
"<div class='box'>"
"<div class='logo'>"
"<div class='icon'>🎙️</div>"
"<div>"
"<h1>AETHERIA SubBox</h1>"
"<p class='sub'>Thiết lập kết nối ban đầu</p>"
"</div>"
"</div>"
"<form id='f'>"
"<div class='field'>"
"<label>Mạng Wi-Fi (2.4GHz)</label>"
"<select id='ssid' name='ssid' required>"
"<option value=''>Đang quét Wi-Fi xung quanh...</option>"
"</select>"
"<button type='button' class='btn-scan' onclick='scanWifi()'>🔄 Quét lại mạng Wi-Fi</button>"
"</div>"
"<div class='field'>"
"<label>Mật khẩu Wi-Fi</label>"
"<input type='password' id='pass' name='pass' placeholder='Nhập mật khẩu...'>"
"</div>"
"<div class='field'>"
"<label>Vị trí phòng của SubBox</label>"
"<select id='room' name='room'>"
"<option value='Phòng ngủ|0' selected>Phòng ngủ (Bedroom)</option>"
"<option value='Phòng khách|1'>Phòng khách (Living Room)</option>"
"<option value='Phòng bếp|2'>Phòng bếp (Kitchen)</option>"
"<option value='Phòng làm việc|3'>Phòng làm việc (Workroom)</option>"
"<option value='Ban công|4'>Ban công (Balcony)</option>"
"</select>"
"</div>"
"<div class='field'>"
"<label>IP Gateway Pi 4 (Mặc định)</label>"
"<input type='text' id='gateway' name='gateway' value='192.168.11.29'>"
"</div>"
"<button type='submit' class='btn' id='sbtn'>Lưu Cấu Hình & Kết Nối</button>"
"<div id='status'></div>"
"</form>"
"</div>"
"<script>"
"function scanWifi(){"
"fetch('/scan').then(r=>r.json()).then(list=>{"
"let sel=document.getElementById('ssid');"
"sel.innerHTML='<option value=\"\">-- Chọn Wi-Fi nhà bạn --</option>';"
"if(!list||list.length===0){sel.innerHTML='<option value=\"\">Không tìm thấy mạng</option>';return;}"
"list.forEach(w=>{"
"let opt=document.createElement('option');"
"opt.value=w.ssid;"
"opt.innerText=w.ssid + ' (' + w.rssi + ' dBm)'; "
"sel.appendChild(opt);"
"});"
"}).catch(()=>{document.getElementById('ssid').innerHTML='<option value=\"\">Lỗi quét Wi-Fi</option>';});"
"}"
"window.onload=scanWifi;"
"document.getElementById('f').onsubmit=function(e){"
"e.preventDefault();"
"let sbtn=document.getElementById('sbtn');"
"let st=document.getElementById('status');"
"sbtn.disabled=true;"
"st.className='loading';"
"st.innerText='Đang lưu cấu hình và kết nối lại...';"
"st.style.display='block';"
"let data={"
"ssid:document.getElementById('ssid').value,"
"pass:document.getElementById('pass').value,"
"room:document.getElementById('room').value,"
"gateway:document.getElementById('gateway').value"
"};"
"fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})"
".then(r=>r.json()).then(res=>{"
"if(res.success){"
"st.className='success';"
"st.innerText='✅ Cấu hình thành công! SubBox đang khởi động lại...';"
"}else{"
"st.innerText='Lỗi: ' + res.error;"
"sbtn.disabled=false;"
"}"
"}).catch(()=>{st.innerText='Đã gửi cấu hình! Đang khởi động...';});"
"};"
"</script>"
"</body>"
"</html>";

/* ─── Captive Portal HTTP Handlers ───────────────────────────────────── */
static esp_err_t portal_root_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    httpd_resp_set_hdr(req, "Cache-Control", "no-cache, no-store, must-revalidate");
    httpd_resp_send(req, PORTAL_HTML, HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

static esp_err_t portal_redirect_handler(httpd_req_t *req) {
    httpd_resp_set_status(req, "302 Found");
    httpd_resp_set_hdr(req, "Location", "http://192.168.4.1/");
    httpd_resp_send(req, NULL, 0);
    return ESP_OK;
}

static esp_err_t portal_scan_handler(httpd_req_t *req) {
    wifi_scan_config_t scan_cfg = {};
    scan_cfg.show_hidden = false;
    esp_wifi_scan_start(&scan_cfg, true);

    uint16_t ap_count = 0;
    esp_wifi_scan_get_ap_num(&ap_count);
    if (ap_count > 20) ap_count = 20;

    wifi_ap_record_t *ap_records = (wifi_ap_record_t *)malloc(sizeof(wifi_ap_record_t) * (ap_count > 0 ? ap_count : 1));
    cJSON *arr = cJSON_CreateArray();

    if (ap_records && ap_count > 0) {
        esp_wifi_scan_get_ap_records(&ap_count, ap_records);
        for (int i = 0; i < ap_count; i++) {
            if (strlen((char *)ap_records[i].ssid) > 0) {
                cJSON *item = cJSON_CreateObject();
                cJSON_AddStringToObject(item, "ssid", (char *)ap_records[i].ssid);
                cJSON_AddNumberToObject(item, "rssi", ap_records[i].rssi);
                cJSON_AddItemToArray(arr, item);
            }
        }
        free(ap_records);
    }

    char *json_str = cJSON_PrintUnformatted(arr);
    cJSON_Delete(arr);

    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_send(req, json_str ? json_str : "[]", HTTPD_RESP_USE_STRLEN);
    if (json_str) free(json_str);
    return ESP_OK;
}

static void restart_task(void *pvParameters) {
    vTaskDelay(pdMS_TO_TICKS(1500));
    ESP_LOGI(TAG, "Rebooting system after provisioning save...");
    esp_restart();
}

static esp_err_t portal_save_handler(httpd_req_t *req) {
    char buf[512] = {0};
    int ret = httpd_req_recv(req, buf, sizeof(buf) - 1);
    if (ret <= 0) {
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }

    cJSON *root = cJSON_Parse(buf);
    if (!root) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid JSON");
        return ESP_FAIL;
    }

    const char *ssid = cJSON_GetStringValue(cJSON_GetObjectItem(root, "ssid"));
    const char *pass = cJSON_GetStringValue(cJSON_GetObjectItem(root, "pass"));
    const char *room_raw = cJSON_GetStringValue(cJSON_GetObjectItem(root, "room"));
    const char *gateway = cJSON_GetStringValue(cJSON_GetObjectItem(root, "gateway"));

    if (!ssid || strlen(ssid) == 0) {
        cJSON_Delete(root);
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "SSID required");
        return ESP_FAIL;
    }

    SubBoxPersistentConfig cfg;
    NVSManager::loadConfig(cfg);

    strncpy(cfg.wifi_ssid, ssid, sizeof(cfg.wifi_ssid) - 1);
    if (pass) {
        strncpy(cfg.wifi_pass, pass, sizeof(cfg.wifi_pass) - 1);
    } else {
        cfg.wifi_pass[0] = '\0';
    }

    if (room_raw) {
        char rname[32] = {0};
        int rtype = 0;
        if (sscanf(room_raw, "%31[^|]|%d", rname, &rtype) == 2) {
            strncpy(cfg.room_name, rname, sizeof(cfg.room_name) - 1);
            cfg.room_type = (RoomType)rtype;
        }
    }

    if (gateway && strlen(gateway) > 0) {
        snprintf(cfg.mqtt_broker_uri, sizeof(cfg.mqtt_broker_uri), "mqtt://%s:1883", gateway);
    }

    esp_err_t save_err = NVSManager::saveConfig(cfg);
    cJSON_Delete(root);

    cJSON *resp = cJSON_CreateObject();
    cJSON_AddBoolToObject(resp, "success", save_err == ESP_OK);
    char *resp_str = cJSON_PrintUnformatted(resp);
    cJSON_Delete(resp);

    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, resp_str, HTTPD_RESP_USE_STRLEN);
    free(resp_str);

    if (save_err == ESP_OK) {
        xTaskCreate(restart_task, "restart_task", 2048, NULL, 5, NULL);
    }

    return ESP_OK;
}

/* ─── Captive DNS Server Task (UDP Port 53) ───────────────────────────── */
static void dns_server_task(void *pvParameters) {
    struct sockaddr_in serv_addr;
    memset(&serv_addr, 0, sizeof(serv_addr));
    serv_addr.sin_family = AF_INET;
    serv_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    serv_addr.sin_port = htons(53);

    s_dns_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (s_dns_socket < 0) {
        ESP_LOGE(TAG, "Failed to create DNS socket");
        vTaskDelete(NULL);
        return;
    }

    if (bind(s_dns_socket, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) < 0) {
        ESP_LOGE(TAG, "Failed to bind DNS socket");
        close(s_dns_socket);
        s_dns_socket = -1;
        vTaskDelete(NULL);
        return;
    }

    ESP_LOGI(TAG, "Captive DNS Server running on UDP:53 (Redirecting all queries to 192.168.4.1)");

    uint8_t buffer[256];
    struct sockaddr_in client_addr;
    socklen_t client_len = sizeof(client_addr);

    while (s_is_active) {
        int len = recvfrom(s_dns_socket, buffer, sizeof(buffer), 0,
                           (struct sockaddr *)&client_addr, &client_len);
        if (len < 12) continue;

        /* Minimal DNS Response: set Flags = 0x8180 (Standard response, no error) */
        buffer[2] = 0x81;
        buffer[3] = 0x80;
        /* Set Questions = 1, Answers = 1, Authority = 0, Additional = 0 */
        buffer[6] = 0x00; buffer[7] = 0x01; // Answer count = 1
        buffer[8] = 0x00; buffer[9] = 0x00;
        buffer[10] = 0x00; buffer[11] = 0x00;

        /* Skip question section */
        int idx = 12;
        while (idx < len && buffer[idx] != 0) {
            idx += buffer[idx] + 1;
        }
        idx += 5; // null byte + QTYPE (2 bytes) + QCLASS (2 bytes)

        if (idx + 16 < (int)sizeof(buffer)) {
            /* Answer Section: Pointer to QNAME (0xc00c), Type A (0x0001), Class IN (0x0001), TTL=60s, Len=4 */
            buffer[idx++] = 0xc0; buffer[idx++] = 0x0c;
            buffer[idx++] = 0x00; buffer[idx++] = 0x01; // Type A
            buffer[idx++] = 0x00; buffer[idx++] = 0x01; // Class IN
            buffer[idx++] = 0x00; buffer[idx++] = 0x00; buffer[idx++] = 0x00; buffer[idx++] = 0x3c; // TTL 60s
            buffer[idx++] = 0x00; buffer[idx++] = 0x04; // Data length = 4 bytes
            /* IP: 192.168.4.1 */
            buffer[idx++] = 192;
            buffer[idx++] = 168;
            buffer[idx++] = 4;
            buffer[idx++] = 1;

            sendto(s_dns_socket, buffer, idx, 0, (struct sockaddr *)&client_addr, client_len);
        }
    }

    if (s_dns_socket >= 0) {
        close(s_dns_socket);
        s_dns_socket = -1;
    }
    vTaskDelete(NULL);
}

/* ─── Public API ──────────────────────────────────────────────────────── */
esp_err_t wifi_provisioning_start(void) {
    if (s_is_active) return ESP_OK;

    ESP_LOGW(TAG, "===============================================================");
    ESP_LOGW(TAG, "  🌐 STARTING SUBBOX SOFTAP CAPTIVE PORTAL PROVISIONING");
    ESP_LOGW(TAG, "===============================================================");

    /* 1. Get MAC address to append to SSID */
    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    char ap_ssid[32];
    snprintf(ap_ssid, sizeof(ap_ssid), "SubBox-Setup-%02X%02X", mac[4], mac[5]);

    /* 2. Configure Wi-Fi in AP+STA mode */
    esp_netif_t *ap_netif = esp_netif_create_default_wifi_ap();
    if (!ap_netif) {
        ESP_LOGW(TAG, "AP netif may already exist");
    }

    wifi_config_t ap_config = {};
    strncpy((char *)ap_config.ap.ssid, ap_ssid, sizeof(ap_config.ap.ssid) - 1);
    ap_config.ap.ssid_len = strlen(ap_ssid);
    ap_config.ap.channel = 1;
    ap_config.ap.max_connection = 4;
    ap_config.ap.authmode = WIFI_AUTH_OPEN; /* Open network for hassle-free mobile setup */

    esp_wifi_set_mode(WIFI_MODE_APSTA);
    esp_wifi_set_config(WIFI_IF_AP, &ap_config);
    esp_wifi_start();

    ESP_LOGI(TAG, "SoftAP active! Connect to Wi-Fi SSID: '%s' (Open, IP: 192.168.4.1)", ap_ssid);

    s_is_active = true;

    /* 3. Start DNS redirect server task */
    xTaskCreate(dns_server_task, "dns_task", 3072, NULL, 5, &s_dns_task_handle);

    /* 4. Start HTTP Web Server */
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.max_uri_handlers = 12;
    config.stack_size = 8192;

    if (httpd_start(&s_http_server, &config) == ESP_OK) {
        httpd_uri_t root_uri = {
            .uri = "/",
            .method = HTTP_GET,
            .handler = portal_root_handler,
            .user_ctx = NULL
        };
        httpd_register_uri_handler(s_http_server, &root_uri);

        httpd_uri_t scan_uri = {
            .uri = "/scan",
            .method = HTTP_GET,
            .handler = portal_scan_handler,
            .user_ctx = NULL
        };
        httpd_register_uri_handler(s_http_server, &scan_uri);

        httpd_uri_t save_uri = {
            .uri = "/save",
            .method = HTTP_POST,
            .handler = portal_save_handler,
            .user_ctx = NULL
        };
        httpd_register_uri_handler(s_http_server, &save_uri);

        /* Captive portal probes redirection */
        const char *probes[] = {
            "/generate_204",
            "/gen_204",
            "/hotspot-detect.html",
            "/canonical.html",
            "/connecttest.txt",
            "/ncsi.txt",
            NULL
        };
        for (int i = 0; probes[i] != NULL; i++) {
            httpd_uri_t probe_uri = {
                .uri = probes[i],
                .method = HTTP_GET,
                .handler = portal_redirect_handler,
                .user_ctx = NULL
            };
            httpd_register_uri_handler(s_http_server, &probe_uri);
        }

        ESP_LOGI(TAG, "Captive Portal Web Server running at http://192.168.4.1");
    }

    return ESP_OK;
}

void wifi_provisioning_stop(void) {
    if (!s_is_active) return;
    s_is_active = false;

    if (s_http_server) {
        httpd_stop(s_http_server);
        s_http_server = NULL;
    }
    if (s_dns_socket >= 0) {
        close(s_dns_socket);
        s_dns_socket = -1;
    }
    ESP_LOGI(TAG, "Wi-Fi Provisioning stopped.");
}

bool wifi_provisioning_is_active(void) {
    return s_is_active;
}
