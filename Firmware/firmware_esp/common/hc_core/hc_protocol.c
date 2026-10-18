#include "hc_protocol.h"
#include <string.h>

static void put(uint8_t *p, uint64_t v, unsigned n) {
    for (unsigned i=0; i<n; ++i) { p[i]=(uint8_t)v; v >>= 8; }
}
static uint64_t get(const uint8_t *p, unsigned n) {
    uint64_t v=0;
    for (unsigned i=0; i<n; ++i) v |= (uint64_t)p[i] << (i*8);
    return v;
}
int hc_encode(const hc_frame *f, uint8_t *out, size_t capacity, hc_mac_fn mac, void *ctx) {
    if (!f || !out || !mac || f->type<HC_HELLO || f->type>HC_CHANNEL_PROBE ||
        (f->flags & ~3u) || f->payload_len>HC_MAX_PAYLOAD || !f->message_id ||
        !f->boot_id || !f->sequence) return HC_INVALID;
    size_t length=HC_HEADER_SIZE+f->payload_len;
    if (capacity<length+HC_TAG_SIZE) return HC_CAPACITY;
    out[0]='H'; out[1]='C'; out[2]=HC_VERSION; out[3]=f->type;
    out[4]=f->flags; out[5]=f->payload_len;
    put(out+6,f->message_id,8); put(out+14,f->source,4); put(out+18,f->destination,4);
    put(out+22,f->boot_id,8); put(out+30,f->sequence,4); put(out+34,f->config_rev,4);
    memcpy(out+HC_HEADER_SIZE,f->payload,f->payload_len);
    if (mac(ctx,out,length,out+length)!=0) return HC_AUTH;
    return (int)(length+HC_TAG_SIZE);
}
int hc_validate(const uint8_t *d, size_t len, hc_mac_fn mac, void *ctx) {
    if (!d || !mac || len<HC_HEADER_SIZE+HC_TAG_SIZE || len>HC_MAX_FRAME ||
        d[0]!='H' || d[1]!='C' || d[2]!=HC_VERSION || d[3]<HC_HELLO ||
        d[3]>HC_CHANNEL_PROBE || (d[4]&~3u) || d[5]>HC_MAX_PAYLOAD ||
        len!=HC_HEADER_SIZE+HC_TAG_SIZE+d[5] || !get(d+6,8) ||
        !get(d+22,8) || !get(d+30,4)) return HC_INVALID;
    uint8_t tag[HC_TAG_SIZE], diff=0;
    if (mac(ctx,d,len-HC_TAG_SIZE,tag)!=0) return HC_AUTH;
    for (unsigned i=0;i<HC_TAG_SIZE;++i) diff |= tag[i]^d[len-HC_TAG_SIZE+i];
    return diff ? HC_AUTH : HC_OK;
}
int hc_decode(const uint8_t *d, size_t len, hc_frame *f, hc_mac_fn mac, void *ctx) {
    if (!f) return HC_INVALID;
    int result=hc_validate(d,len,mac,ctx);
    if (result!=HC_OK) return result;
    memset(f,0,sizeof(*f));
    f->type=d[3]; f->flags=d[4]; f->payload_len=d[5];
    f->message_id=get(d+6,8); f->source=(uint32_t)get(d+14,4);
    f->destination=(uint32_t)get(d+18,4); f->boot_id=get(d+22,8);
    f->sequence=(uint32_t)get(d+30,4); f->config_rev=(uint32_t)get(d+34,4);
    memcpy(f->payload,d+HC_HEADER_SIZE,f->payload_len);
    return HC_OK;
}
int hc_roundtrip(const uint8_t *d, size_t len, uint8_t out[HC_MAX_FRAME], hc_mac_fn mac, void *ctx) {
    hc_frame f;
    int result=hc_decode(d,len,&f,mac,ctx);
    return result==HC_OK ? hc_encode(&f,out,HC_MAX_FRAME,mac,ctx) : result;
}
void hc_factory_id(const uint8_t mac[6], char out[16]) {
    static const char hex[]="0123456789ABCDEF";
    memcpy(out,"HC-",3);
    for (unsigned i=0;i<6;++i) { out[3+2*i]=hex[mac[i]>>4]; out[4+2*i]=hex[mac[i]&15]; }
    out[15]=0;
}
void hc_replay_admit(hc_replay *s, uint64_t boot) {
    if (boot && s->boot!=boot) { s->boot=boot; s->high=0; s->mask=0; }
}
hc_replay_result hc_replay_check(hc_replay *s, uint64_t boot, uint32_t seq) {
    if (!boot || boot!=s->boot) return HC_SESSION_REQUIRED;
    if (!seq) return HC_STALE;
    if (seq>s->high) {
        uint32_t delta=seq-s->high;
        s->mask=(delta>=32 ? 0 : s->mask<<delta)|1u;
        s->high=seq; return HC_NEW;
    }
    uint32_t delta=s->high-seq;
    if (delta>=32) return HC_STALE;
    uint32_t bit=1u<<delta;
    if (s->mask&bit) return HC_DUPLICATE;
    s->mask|=bit; return HC_NEW;
}
int hc_command_admit(uint64_t generations[3],uint8_t channel,uint8_t state,uint64_t generation,uint64_t deadline,uint64_t now) {
    if(!generations || channel<1 || channel>3 || state>1 || !generation ||
       generation<=generations[channel-1] || deadline<=now || deadline-now>30000) return 0;
    generations[channel-1]=generation;
    return 1;
}
