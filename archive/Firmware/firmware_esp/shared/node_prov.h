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
    char node_id[PROV_NODE_ID_MAX];
    char room[PROV_ROOM_MAX];
    char rl1[PROV_DEV_MAX];
    char rl2[PROV_DEV_MAX];
    uint16_t cfg_version;
    bool provisioned;
    bool relay_state[2];
    uint16_t last_seq;
} node_prov_t;

extern node_prov_t g_prov;

bool prov_load(void);

esp_err_t prov_save_cfg(const char *node_id, const char *room,
                        const char *rl1, const char *rl2, uint16_t version);

void prov_set_relay(int ch  , bool on);

int prov_handle_relay_cmd(int ch, int s, int seq);

int prov_build_hello(char *buf, size_t bufsz, const char *mac_str,
                     const char *fw_ver, const char *ip_str, int rssi, uint32_t uptime_s);

int prov_build_ack(char *buf, size_t bufsz, int seq);

void prov_fullname(int ch, char *out, size_t outsz);

#ifdef __cplusplus
}
#endif
#endif
