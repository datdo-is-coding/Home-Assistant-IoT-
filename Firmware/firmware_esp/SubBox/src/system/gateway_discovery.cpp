#include "gateway_discovery.h"

#include <cstring>
#include <cerrno>
#include "esp_log.h"
#include "esp_timer.h"
#include "cJSON.h"
#include "lwip/sockets.h"
#include "lwip/netdb.h"
#include "lwip/inet.h"

static const char *TAG = "GW_DISCOVERY";

bool gateway_discover(char* out_ip, size_t max_ip_len, uint16_t* out_ws_port, uint16_t* out_mqtt_port, uint32_t timeout_ms) {
    if (!out_ip || max_ip_len == 0) {
        return false;
    }
    out_ip[0] = '\0';
    if (out_ws_port) *out_ws_port = 8765;
    if (out_mqtt_port) *out_mqtt_port = 8883;

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) {
        ESP_LOGE(TAG, "Failed to create UDP socket: errno %d", errno);
    } else {
        int broadcast = 1;
        setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &broadcast, sizeof(broadcast));

        int reuse = 1;
        setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

        struct sockaddr_in bind_addr;
        memset(&bind_addr, 0, sizeof(bind_addr));
        bind_addr.sin_family = AF_INET;
        bind_addr.sin_port = htons(5005);
        bind_addr.sin_addr.s_addr = htonl(INADDR_ANY);
        bind(sock, (struct sockaddr*)&bind_addr, sizeof(bind_addr));

        struct sockaddr_in dest_addr;
        memset(&dest_addr, 0, sizeof(dest_addr));
        dest_addr.sin_family = AF_INET;
        dest_addr.sin_port = htons(5005);
        dest_addr.sin_addr.s_addr = htonl(INADDR_BROADCAST);

        const char* probe_msg = "DISCOVER_GATEWAY";
        ssize_t sent = sendto(sock, probe_msg, strlen(probe_msg), 0, (struct sockaddr*)&dest_addr, sizeof(dest_addr));
        if (sent < 0) {
            ESP_LOGW(TAG, "UDP probe send failed: errno %d", errno);
        } else {
            ESP_LOGI(TAG, "Sent UDP discovery probe to 255.255.255.255:5005 (timeout %lu ms)", (unsigned long)timeout_ms);
        }

        int64_t deadline_us = esp_timer_get_time() + (int64_t)timeout_ms * 1000;
        while (true) {
            int64_t now_us = esp_timer_get_time();
            int64_t remaining_us = deadline_us - now_us;
            if (remaining_us <= 0) {
                break;
            }

            fd_set read_fds;
            FD_ZERO(&read_fds);
            FD_SET(sock, &read_fds);

            struct timeval tv;
            tv.tv_sec = (time_t)(remaining_us / 1000000);
            tv.tv_usec = (suseconds_t)(remaining_us % 1000000);

            int sel = select(sock + 1, &read_fds, NULL, NULL, &tv);
            if (sel <= 0) {
                break;
            }

            if (FD_ISSET(sock, &read_fds)) {
                char rx_buf[512];
                struct sockaddr_in src_addr;
                socklen_t addr_len = sizeof(src_addr);
                ssize_t len = recvfrom(sock, rx_buf, sizeof(rx_buf) - 1, 0, (struct sockaddr*)&src_addr, &addr_len);
                if (len <= 0) {
                    continue;
                }
                rx_buf[len] = '\0';
                cJSON* root = cJSON_Parse(rx_buf);
                if (!root) {
                    continue;
                }
                cJSON* srv = cJSON_GetObjectItem(root, "service");
                if (srv && cJSON_IsString(srv) && strcmp(srv->valuestring, "aetheria_gateway") == 0) {
                    cJSON* ip_item = cJSON_GetObjectItem(root, "ip");
                    const char* gw_ip = nullptr;
                    if (ip_item && cJSON_IsString(ip_item) && strlen(ip_item->valuestring) > 0) {
                        if (strncmp(ip_item->valuestring, "127.", 4) == 0 || strcmp(ip_item->valuestring, "0.0.0.0") == 0) {
                            gw_ip = inet_ntoa(src_addr.sin_addr);
                        } else {
                            gw_ip = ip_item->valuestring;
                        }
                    } else {
                        gw_ip = inet_ntoa(src_addr.sin_addr);
                    }

                    if (gw_ip && strlen(gw_ip) > 0) {
                        strncpy(out_ip, gw_ip, max_ip_len - 1);
                        out_ip[max_ip_len - 1] = '\0';

                        if (out_ws_port) {
                            cJSON* ws_item = cJSON_GetObjectItem(root, "ws_port");
                            if (ws_item && cJSON_IsNumber(ws_item)) {
                                *out_ws_port = (uint16_t)ws_item->valueint;
                            }
                        }
                        if (out_mqtt_port) {
                            cJSON* mqtt_tls_item = cJSON_GetObjectItem(root, "mqtt_tls_port");
                            cJSON* mqtt_item = cJSON_GetObjectItem(root, "mqtt_port");
                            if (mqtt_tls_item && cJSON_IsNumber(mqtt_tls_item) && mqtt_tls_item->valueint > 0) {
                                *out_mqtt_port = (uint16_t)mqtt_tls_item->valueint;
                            } else if (mqtt_item && cJSON_IsNumber(mqtt_item)) {
                                *out_mqtt_port = (uint16_t)mqtt_item->valueint;
                            }
                        }

                        ESP_LOGI(TAG, "Gateway found via UDP: %s (WS: %u, MQTT: %u)",
                                 out_ip, out_ws_port ? *out_ws_port : 0, out_mqtt_port ? *out_mqtt_port : 0);
                        cJSON_Delete(root);
                        close(sock);
                        return true;
                    }
                }
                cJSON_Delete(root);
            }
        }
        close(sock);
    }

    // Fallback: mDNS resolution for "gateway.local"
    ESP_LOGW(TAG, "UDP broadcast timeout, trying mDNS fallback (gateway.local)...");
    struct hostent *he = gethostbyname("gateway.local");
    if (he && he->h_addr_list && he->h_addr_list[0]) {
        struct in_addr **addr_list = (struct in_addr **)he->h_addr_list;
        const char* resolved_ip = inet_ntoa(*addr_list[0]);
        if (resolved_ip && strlen(resolved_ip) > 0) {
            strncpy(out_ip, resolved_ip, max_ip_len - 1);
            out_ip[max_ip_len - 1] = '\0';
            if (out_ws_port) *out_ws_port = 8765;
            if (out_mqtt_port) *out_mqtt_port = 8883;
            ESP_LOGI(TAG, "Gateway resolved via mDNS: %s", out_ip);
            return true;
        }
    }

    ESP_LOGE(TAG, "Gateway discovery failed (UDP timeout & mDNS resolution failed)");
    return false;
}
