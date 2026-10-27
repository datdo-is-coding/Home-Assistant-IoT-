#include "hc_ota_manifest.h"
#include <string.h>

static uint16_t get16(const uint8_t *p) {return (uint16_t)p[0]|((uint16_t)p[1]<<8);}
static uint32_t get32(const uint8_t *p) {return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static uint64_t get64(const uint8_t *p) {return (uint64_t)get32(p)|((uint64_t)get32(p+4)<<32);}
static bool nonzero(const uint8_t *p,size_t size) {
    for(size_t i=0;i<size;++i)if(p[i])return true;
    return false;
}
static bool text16(const uint8_t *p) {
    bool ended=false;
    if(!p[0])return false;
    for(size_t i=0;i<16;++i) {
        uint8_t c=p[i];
        if(!c){ended=true;continue;}
        if(ended || !((c>='A' && c<='Z') || (c>='a' && c<='z') ||
                     (c>='0' && c<='9') || c=='_' || c=='.' || c=='-'))return false;
    }
    return ended;
}
bool hc_ota_manifest_parse(const uint8_t *m,size_t length,const hc_ota_policy *p,
                           hc_ota_verify_fn verify,void *ctx,hc_ota_target *out) {
    if(!m || !p || !verify || !out)return false;
    hc_ota_target t={0};size_t header;
    if(length==HC_OTA_V2_TARGET_SIZE) {
        if(m[0]!=2 || m[1]!=p->role || (m[1]!=HC_OTA_ROLE_SUBBOX && m[1]!=HC_OTA_ROLE_ACTIONBOX) ||
           m[2]!=HC_OTA_ARTIFACT_FIRMWARE || m[3]!=0 || !p->has_compatibility ||
           !nonzero(m+4,32) || memcmp(m+4,p->compatibility,32)!=0 || !text16(m+36) ||
           !get16(m+88) || get16(m+88)>p->agent_version ||
           !get16(m+90) || get16(m+90)>p->bootloader_api ||
           !get16(m+92) || get16(m+92)>get16(m+94) ||
           p->protocol_version<get16(m+92) || p->protocol_version>get16(m+94) ||
           !get64(m+96) || get64(m+96)<=p->confirmed_counter ||
           get32(m+104)<p->security_epoch || get32(m+108)!=p->key_id)return false;
        t.schema=2;memcpy(t.version,m+36,16);t.size=get32(m+52);memcpy(t.sha256,m+56,32);
        t.release_counter=get64(m+96);t.security_epoch=get32(m+104);t.key_id=get32(m+108);
        header=HC_OTA_V2_HEADER_SIZE;
    } else if(length==HC_OTA_V1_TARGET_SIZE) {
        if(p->confirmed_counter || p->security_epoch || !text16(m) || !text16(m+16) ||
           !memchr(p->model,0,16) || strcmp((const char*)m,p->model)!=0)return false;
        t.schema=1;memcpy(t.version,m+16,16);t.size=get32(m+32);memcpy(t.sha256,m+36,32);
        header=HC_OTA_V1_HEADER_SIZE;
    } else return false;
    if(!t.size || t.size>HC_OTA_MAX_IMAGE_SIZE || t.size>p->max_size || !nonzero(t.sha256,32) ||
       !verify(ctx,m,header,m+header))return false;
    *out=t;return true;
}
