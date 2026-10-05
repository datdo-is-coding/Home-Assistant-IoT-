/*
 * Node Provision store — NVS wrapper cho compact protocol (protocol_spec.md).
 *
 * ESP32 lưu lại thông tin Gateway gán (node_id, room, rl1_name, rl2_name, cfg_version)
 * vào NVS namespace "smhome". Mỗi lần hello/status đều echo rl1_name/rl2_name qua tên
 * đầy đủ để Gateway verify không bị lệch cấu hình (cfg_version).
 *
 * Dùng chung cho mọi node (voice S3 + relay WROOM thuần):
 *   prov_load()   → đọc lúc boot, trả true nếu đã provision
 *   prov_save()   → ghi khi nhận {"t":"cfg",...}
 *   prov_hello()  → build JSON hello (~110B đã provision / nhẹ hơn khi chưa)
 *   prov_ack()    → build JSON ack {"t":"ack","id":...,"rl":[a,b],"seq":n}
 *
 * Relay mapping: RL1=GPIO4, RL2=GPIO5 (Active-LOW, PC817).
 * Tên thiết bị (rl1_name/rl2_name): "light" | "fan" | "pump" | "curtain" | "" (trống).
 * Fullname suy ra: {node_id}-{dev}, ví dụ livingroom-node01-light.
 */
#ifndef NODE_PROV_H
#define NODE_PROV_H

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define PROV_NODE_ID_MAX   40
#define PROV_ROOM_MAX      24
#define PROV_DEV_MAX       16

typedef struct {
    char node_id[PROV_NODE_ID_MAX];   // "livingroom-node01" ("" = chưa provision)
    char room[PROV_ROOM_MAX];         // "livingroom"
    char rl1[PROV_DEV_MAX];           // "light" — ESP32 PHẢI nhớ để echo lại
    char rl2[PROV_DEV_MAX];           // "fan"
    uint16_t cfg_version;             // v do gateway cấp
    bool provisioned;                 // cfg_version>0 && node_id[0]
    bool relay_state[2];              // trạng thái thực tế GPIO RL1, RL2
    uint16_t last_seq;                // seq cuối đã thực thi (chống lặp MQTT retain)
} node_prov_t;

extern node_prov_t g_prov;

/** Đọc NVS lúc boot. */
bool prov_load(void);

/** Ghi cấu hình từ gói {"t":"cfg","id":..,"room":..,"rl1":..,"rl2":..,"v":n}. */
esp_err_t prov_save_cfg(const char *node_id, const char *room,
                        const char *rl1, const char *rl2, uint16_t version);

/** Cập nhật relay_state RAM (gọi sau mỗi lần kéo GPIO). Không ghi NVS mỗi lần để bền flash. */
void prov_set_relay(int ch /*1|2*/, bool on);

/**
 * Xử lý lệnh relay compact {"t":"rl","ch":1|2,"s":0|1,"seq":n}.
 * Trả về: 0=đã thực thi, 1=seq trùng/cũ (bỏ qua), -1=sai ch.
 * Hàm này TỰ kéo GPIO (Active-LOW) và cập nhật relay_state.
 */
int prov_handle_relay_cmd(int ch, int s, int seq);

/** Build JSON hello vào buf (trả về độ dài). Chưa provision → kèm mac/fw, không có id. */
int prov_build_hello(char *buf, size_t bufsz, const char *mac_str,
                     const char *fw_ver, const char *ip_str, int rssi, uint32_t uptime_s);

/** Build JSON ack {"t":"ack","id":..,"rl":[a,b],"seq":n}. */
int prov_build_ack(char *buf, size_t bufsz, int seq);

/** Fullname của 1 kênh: "{node_id}-{dev}" (dùng cho log). */
void prov_fullname(int ch, char *out, size_t outsz);

#ifdef __cplusplus
}
#endif
#endif /* NODE_PROV_H */
