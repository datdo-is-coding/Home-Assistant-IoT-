#pragma once
#include <stdbool.h>
#include "hc_protocol.h"

static inline bool hc_maintenance_valid(const hc_frame *f,uint32_t revision,uint64_t now) {
    if(!f || f->type!=HC_MAINTENANCE || f->payload_len!=9 || f->config_rev!=revision || f->payload[0]<1 || f->payload[0]>3)return false;
    uint64_t deadline=0;
    for(unsigned i=0;i<8;++i)deadline|=(uint64_t)f->payload[1+i]<<(8*i);
    return deadline>=now && deadline-now<=5000;
}
