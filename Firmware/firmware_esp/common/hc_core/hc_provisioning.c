#include "hc_provisioning.h"
#include "hc_protocol.h"
#include "nvs.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_system.h"
#include "esp_log.h"
#include "driver/gpio.h"
#include "esp_netif.h"
#include "protocomm.h"
#include "protocomm_httpd.h"
#include "protocomm_security1.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "psa/crypto.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

static protocomm_t *server;
static uint8_t factory_secret[32], challenge[32];
static char setup[65];
static protocomm_security1_params_t security_params;
static bool is_subbox, parent_verified;
static int64_t deadline;
static SemaphoreHandle_t config_lock;
static uint32_t window_generation;

static uint32_t u32(const uint8_t *p) { return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24); }
static uint64_t u64(const uint8_t *p) { return (uint64_t)u32(p)|((uint64_t)u32(p+4)<<32); }
static void p32(uint8_t *p,uint32_t v) { for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(v>>(8*i)); }
static bool equal(const uint8_t *a,const uint8_t *b,size_t n) { uint8_t d=0; for(size_t i=0;i<n;++i)d|=a[i]^b[i]; return d==0; }
static bool nonzero(const uint8_t *p,size_t n) { uint8_t d=0;for(size_t i=0;i<n;++i)d|=p[i];return d!=0; }
static bool text_valid(const uint8_t *p,size_t n) { return memchr(p,0,n)!=NULL; }
static esp_err_t mac(const uint8_t *key,size_t key_len,const uint8_t *data,size_t len,uint8_t digest[32]) {
    psa_key_attributes_t attr=PSA_KEY_ATTRIBUTES_INIT;
    psa_set_key_type(&attr,PSA_KEY_TYPE_HMAC); psa_set_key_bits(&attr,key_len*8);
    psa_set_key_usage_flags(&attr,PSA_KEY_USAGE_SIGN_MESSAGE);
    psa_set_key_algorithm(&attr,PSA_ALG_HMAC(PSA_ALG_SHA_256));
    mbedtls_svc_key_id_t handle=0;size_t length=0;
    psa_status_t result=psa_crypto_init();
    if(result==PSA_SUCCESS)result=psa_import_key(&attr,key,key_len,&handle);
    if(result==PSA_SUCCESS)result=psa_mac_compute(handle,PSA_ALG_HMAC(PSA_ALG_SHA_256),data,len,digest,32,&length);
    if(handle)psa_destroy_key(handle);
    psa_reset_key_attributes(&attr);
    return result==PSA_SUCCESS && length==32?ESP_OK:ESP_FAIL;
}
static esp_err_t authenticate(const uint8_t *key,size_t key_len,const uint8_t *packet,size_t body,size_t tag) {
    uint8_t digest[32];esp_err_t err=mac(key,key_len,packet,body,digest);
    if(err==ESP_OK && !equal(digest,packet+body,tag))err=ESP_ERR_INVALID_CRC;
    memset(digest,0,32);return err;
}
static esp_err_t lock_config(void) {
    if(!config_lock)config_lock=xSemaphoreCreateMutex();
    if(!config_lock)return ESP_ERR_NO_MEM;
    return xSemaphoreTake(config_lock,pdMS_TO_TICKS(2000))==pdTRUE?ESP_OK:ESP_ERR_TIMEOUT;
}
static esp_err_t save(const hc_provisioned_config *c) {
    nvs_handle_t h;esp_err_t err=nvs_open("hc_core",NVS_READWRITE,&h);
    if(err!=ESP_OK)return err;
    err=nvs_set_blob(h,"enrollment",c,sizeof(*c));
    if(err==ESP_OK)err=nvs_commit(h);
    nvs_close(h);return err;
}
esp_err_t hc_provisioning_load(hc_provisioned_config *out) {
    if(!out)return ESP_ERR_INVALID_ARG;
    nvs_handle_t h;esp_err_t err=nvs_open("hc_core",NVS_READONLY,&h);
    if(err!=ESP_OK)return err;
    size_t size=sizeof(*out);err=nvs_get_blob(h,"enrollment",out,&size);nvs_close(h);
    if(err!=ESP_OK)return err;
    if(size!=sizeof(*out)||out->schema!=1||!out->node_id||!out->revision||out->peer_count>4||out->channel<1||out->channel>13)return ESP_ERR_INVALID_VERSION;
    if(!out->subbox && (!out->parent_id||out->peer_count!=1||out->peers[0].node_id!=out->parent_id))return ESP_ERR_INVALID_ARG;
    uint8_t base[6];char actual[16];err=esp_efuse_mac_get_default(base);
    if(err!=ESP_OK)return err;
    hc_factory_id(base,actual);
    return memcmp(actual,out->factory_id,sizeof(actual))==0?ESP_OK:ESP_ERR_INVALID_MAC;
}
esp_err_t hc_provisioning_speaker_token(char out[65]) {
    if(!out)return ESP_ERR_INVALID_ARG;
    out[0]=0;
    hc_provisioned_config c={0};
    esp_err_t err=hc_provisioning_load(&c);
    uint8_t digest[32]={0};
    if(err==ESP_OK && (!c.subbox||!c.committed||!nonzero(c.key,sizeof(c.key))))err=ESP_ERR_INVALID_STATE;
    static const uint8_t domain[]="HC-SPEAKER-V1";
    if(err==ESP_OK)err=mac(c.key,sizeof(c.key),domain,sizeof(domain),digest);
    memset(&c,0,sizeof(c));
    if(err==ESP_OK){
        static const char hex[]="0123456789abcdef";
        for(unsigned i=0;i<32;++i){out[2*i]=hex[digest[i]>>4];out[2*i+1]=hex[digest[i]&15];}
        out[64]=0;
    }
    memset(digest,0,sizeof(digest));
    return err;
}
static esp_err_t sync_subbox_credentials(const hc_provisioned_config *c) {
    if (!c || !c->subbox) return ESP_OK;
    char ws_uri[128] = {0};
    const char *p = c->mqtt_uri;
    const char *proto_end = strstr(p, "://");
    const char *host_start = proto_end ? proto_end + 3 : p;
    char host[64] = {0};
    size_t hi = 0;
    while (host_start[hi] && host_start[hi] != ':' && host_start[hi] != '/' && hi < sizeof(host) - 1) {
        host[hi] = host_start[hi];
        hi++;
    }
    host[hi] = '\0';
    if (hi > 0) {
        snprintf(ws_uri, sizeof(ws_uri), "ws://%s:8765/ws/audio", host);
    }

    nvs_handle_t h;
    if (nvs_open("subbox_cfg", NVS_READWRITE, &h) == ESP_OK) {
        char id_str[32] = {0};
        snprintf(id_str, sizeof(id_str), "%lu", (unsigned long)c->node_id);
        nvs_set_str(h, "id", id_str);
        if (c->room_id[0]) nvs_set_str(h, "room", c->room_id);
        nvs_set_str(h, "ssid", c->wifi_ssid);
        nvs_set_str(h, "pass", c->wifi_password);
        nvs_set_str(h, "broker", c->mqtt_uri);
        if (ws_uri[0]) nvs_set_str(h, "wsuri", ws_uri);
        nvs_commit(h);
        nvs_close(h);
    }

    if (nvs_open("subbox_sec", NVS_READWRITE, &h) == ESP_OK) {
        nvs_set_str(h, "mqtt_uri", c->mqtt_uri);
        if (ws_uri[0]) nvs_set_str(h, "ws_uri", ws_uri);
        nvs_set_str(h, "wifi_ssid", c->wifi_ssid);
        nvs_set_str(h, "wifi_pass", c->wifi_password);
        nvs_commit(h);
        nvs_close(h);
    }
    return ESP_OK;
}

static bool extract_json_str(const char *json, const char *key, char *out, size_t out_sz) {
    char pattern[64];
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    const char *k = strstr(json, pattern);
    if (!k) return false;
    const char *colon = strchr(k + strlen(pattern), ':');
    if (!colon) return false;
    const char *q1 = strchr(colon, '\"');
    if (!q1) return false;
    const char *q2 = strchr(q1 + 1, '\"');
    if (!q2) return false;
    size_t val_len = (size_t)(q2 - (q1 + 1));
    if (val_len >= out_sz) val_len = out_sz - 1;
    memcpy(out, q1 + 1, val_len);
    out[val_len] = '\0';
    return true;
}

static bool extract_json_int(const char *json, const char *key, int *out) {
    char pattern[64];
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    const char *k = strstr(json, pattern);
    if (!k) return false;
    const char *colon = strchr(k + strlen(pattern), ':');
    if (!colon) return false;
    const char *p = colon + 1;
    while (*p == ' ' || *p == '\t') p++;
    if (*p >= '0' && *p <= '9') {
        *out = atoi(p);
        return true;
    }
    return false;
}

bool hc_provisioning_active(void) { return server && esp_timer_get_time()<deadline; }
esp_err_t hc_provisioning_apply(const uint8_t *p,size_t length) {
    if(!hc_provisioning_active())return ESP_ERR_INVALID_STATE;

    if (p && length > 2 && p[0] == '{') {
        char json_buf[512] = {0};
        size_t cp_len = length < sizeof(json_buf) - 1 ? length : sizeof(json_buf) - 1;
        memcpy(json_buf, p, cp_len);
        json_buf[cp_len] = '\0';

        char j_ssid[33] = {0}, j_pass[65] = {0}, j_host[64] = {0}, j_pop[65] = {0}, j_room[32] = {0};
        int j_port = 8883;

        extract_json_str(json_buf, "ssid", j_ssid, sizeof(j_ssid));
        extract_json_str(json_buf, "password", j_pass, sizeof(j_pass));
        if (!j_pass[0]) extract_json_str(json_buf, "pass", j_pass, sizeof(j_pass));
        extract_json_str(json_buf, "gateway_host", j_host, sizeof(j_host));
        if (!j_host[0]) extract_json_str(json_buf, "gateway", j_host, sizeof(j_host));
        extract_json_str(json_buf, "pop", j_pop, sizeof(j_pop));
        extract_json_str(json_buf, "room_name", j_room, sizeof(j_room));
        if (!j_room[0]) extract_json_str(json_buf, "room", j_room, sizeof(j_room));
        extract_json_int(json_buf, "gateway_port", &j_port);

        if (!j_ssid[0]) return ESP_ERR_INVALID_ARG;
        if (j_pop[0] && setup[0] && strcmp(j_pop, setup) != 0) return ESP_ERR_INVALID_STATE;

        esp_err_t err = lock_config();
        if (err != ESP_OK) return err;
        hc_provisioned_config c = {0};
        hc_provisioning_load(&c);
        c.schema = 1;
        c.subbox = is_subbox ? 1 : 0;
        if (c.channel < 1 || c.channel > 13) c.channel = 1;
        if (c.revision == 0) c.revision = 1;

        uint8_t base[6];
        if (esp_efuse_mac_get_default(base) == ESP_OK) {
            hc_factory_id(base, c.factory_id);
            if (c.node_id == 0) {
                c.node_id = ((uint32_t)base[2] << 24) | ((uint32_t)base[3] << 16) |
                            ((uint32_t)base[4] << 8)  | (uint32_t)base[5];
            }
        }

        strncpy(c.wifi_ssid, j_ssid, sizeof(c.wifi_ssid) - 1);
        strncpy(c.wifi_password, j_pass, sizeof(c.wifi_password) - 1);
        if (j_host[0]) {
            snprintf(c.mqtt_uri, sizeof(c.mqtt_uri), "mqtts://%s:%d", j_host, j_port);
        }
        if (j_room[0]) {
            strncpy(c.room_id, j_room, sizeof(c.room_id) - 1);
        }

        c.committed = 1;
        err = save(&c);
        if (err == ESP_OK && is_subbox) {
            sync_subbox_credentials(&c);
        }
        memset(&c, 0, sizeof(c));
        xSemaphoreGive(config_lock);
        return err;
    }

    if(!p||length!=HC_ENROLLMENT_SIZE||memcmp(p,"HCP1",4)||p[4]!=(is_subbox?1:2)||p[5]<1||p[5]>13||p[6]||p[7])return ESP_ERR_INVALID_ARG;
    esp_err_t err=authenticate(factory_secret,32,p,515,32);if(err!=ESP_OK)return err;
    uint8_t base[6];err=esp_efuse_mac_get_default(base);if(err!=ESP_OK)return err;
    if(!equal(base,p+20,6)||!equal(challenge,p+32,32)||!nonzero(p+64,32)||!u32(p+8)||!u32(p+16))return ESP_ERR_INVALID_ARG;
    if(!text_valid(p+96,32)||!text_valid(p+128,32)||!text_valid(p+192,32)||!text_valid(p+224,33)||!text_valid(p+257,65)||!text_valid(p+322,128))return ESP_ERR_INVALID_ARG;
    if(!is_subbox && (!u32(p+12)||(p[26]&1)||!nonzero(p+26,6)||p[224]||p[257]||p[322]))return ESP_ERR_INVALID_ARG;
    if(is_subbox && (u32(p+12)||!p[224]||memcmp(p+322,"mqtts://",8)))return ESP_ERR_INVALID_ARG;
    if(nonzero(p+450,65)&&p[450]!=4)return ESP_ERR_INVALID_ARG;
    err=lock_config();if(err!=ESP_OK)return err;
    hc_provisioned_config existing={0};err=hc_provisioning_load(&existing);

    if(err==ESP_OK && existing.committed){xSemaphoreGive(config_lock);return ESP_ERR_INVALID_STATE;}
    hc_provisioned_config c={0};c.schema=1;c.node_id=u32(p+8);c.parent_id=u32(p+12);c.revision=u32(p+16);c.channel=p[5];c.subbox=is_subbox;
    hc_factory_id(base,c.factory_id);memcpy(c.model,p+192,32);memcpy(c.claim_id,p+96,32);memcpy(c.room_id,p+128,32);
    memcpy(c.claim_nonce,p+64,32);memcpy(c.pmk,p+160,16);memcpy(c.wifi_ssid,p+224,33);memcpy(c.wifi_password,p+257,65);memcpy(c.mqtt_uri,p+322,128);memcpy(c.ota_pubkey,p+450,65);

    const char domain[]="HC-OPERATING-V1";
    uint8_t material[sizeof(domain)+32];memcpy(material,domain,sizeof(domain));memcpy(material+sizeof(domain),p+64,32);
    err=mac(factory_secret,32,material,sizeof(material),c.key);memset(material,0,sizeof(material));
    if(!is_subbox){c.peer_count=1;c.peers[0].node_id=c.parent_id;memcpy(c.peers[0].mac,p+26,6);memcpy(c.peers[0].lmk,p+176,16);memcpy(c.peers[0].nonce,p+64,32);}
    if(err==ESP_OK)err=save(&c);
    if(err==ESP_OK && is_subbox)sync_subbox_credentials(&c);
    if(err==ESP_OK){parent_verified=false;memset(challenge,0,32);}
    memset(&c,0,sizeof(c));xSemaphoreGive(config_lock);return err;
}
esp_err_t hc_provisioning_install_peer(const uint8_t *p,size_t length) {
    if(!p||length!=HC_PEER_GRANT_SIZE||memcmp(p,"HCG1",4))return ESP_ERR_INVALID_ARG;
    esp_err_t err=lock_config();if(err!=ESP_OK)return err;
    hc_provisioned_config c={0};err=hc_provisioning_load(&c);
    if(err==ESP_OK && (!c.subbox||!c.committed||u32(p+8)!=c.node_id||u32(p+12)!=c.revision||!u32(p+4)||(p[48]&1)||!nonzero(p+48,6)))err=ESP_ERR_INVALID_ARG;
    if(err==ESP_OK)err=authenticate(c.key,32,p,78,32);
    unsigned slot=0;bool duplicate=false;
    if(err==ESP_OK){
        for(slot=0;slot<c.peer_count;++slot)if(c.peers[slot].node_id==u32(p+4))break;
        duplicate=slot<c.peer_count&&equal(c.peers[slot].nonce,p+16,32)&&equal(c.peers[slot].mac,p+48,6)&&equal(c.peers[slot].lmk,p+54,16);
        if(!duplicate && (u64(p+70)<=c.peer_generation||slot>=4))err=ESP_ERR_INVALID_STATE;
    }
    if(err==ESP_OK && !duplicate){
        if(slot==c.peer_count)c.peer_count++;
        c.peers[slot].node_id=u32(p+4);memcpy(c.peers[slot].nonce,p+16,32);memcpy(c.peers[slot].mac,p+48,6);memcpy(c.peers[slot].lmk,p+54,16);c.peer_generation=u64(p+70);err=save(&c);
    }
    memset(&c,0,sizeof(c));xSemaphoreGive(config_lock);return err;
}
static esp_err_t pair_packet(const hc_provisioned_config *c,const uint8_t lmk[16],bool response,uint32_t child,const uint8_t nonce[32],uint8_t out[60]) {
    memcpy(out,response?"HCS1":"HCQ1",4);memcpy(out+4,nonce,32);p32(out+36,child);p32(out+40,c->subbox?c->node_id:c->parent_id);
    uint8_t digest[32];esp_err_t err=mac(lmk,16,out,44,digest);if(err==ESP_OK)memcpy(out+44,digest,16);memset(digest,0,32);return err;
}
esp_err_t hc_provisioning_pair_hello(uint8_t out[HC_PAIR_HELLO_SIZE]) {
    hc_provisioned_config c;esp_err_t err=hc_provisioning_load(&c);if(err!=ESP_OK)return err;
    if(c.subbox||c.committed)return ESP_ERR_INVALID_STATE;
    err=pair_packet(&c,c.peers[0].lmk,false,c.node_id,c.claim_nonce,out);memset(&c,0,sizeof(c));return err;
}
esp_err_t hc_provisioning_pair_receive(const uint8_t radio_mac[6],const uint8_t *p,size_t length,uint8_t reply[HC_PAIR_HELLO_SIZE]) {
    if(!radio_mac||!p||!reply||length!=60)return ESP_ERR_INVALID_ARG;
    hc_provisioned_config c;esp_err_t err=hc_provisioning_load(&c);if(err!=ESP_OK)return err;
    if(c.subbox){
        if(memcmp(p,"HCQ1",4)||u32(p+40)!=c.node_id){err=ESP_ERR_INVALID_ARG;goto done;}
        err=ESP_ERR_NOT_FOUND;
        for(unsigned i=0;i<c.peer_count;++i)if(c.peers[i].node_id==u32(p+36)&&equal(c.peers[i].mac,radio_mac,6)&&equal(c.peers[i].nonce,p+4,32)){
            err=authenticate(c.peers[i].lmk,16,p,44,16);
            if(err==ESP_OK)err=pair_packet(&c,c.peers[i].lmk,true,c.peers[i].node_id,p+4,reply);
            break;
        }
    }else{
        if(memcmp(p,"HCS1",4)||u32(p+36)!=c.node_id||u32(p+40)!=c.parent_id||!equal(c.peers[0].mac,radio_mac,6)||!equal(c.claim_nonce,p+4,32)){err=ESP_ERR_INVALID_ARG;goto done;}
        err=authenticate(c.peers[0].lmk,16,p,44,16);if(err==ESP_OK){parent_verified=true;memset(reply,0,60);}
    }
 done:memset(&c,0,sizeof(c));return err;
}
esp_err_t hc_provisioning_peer_receipt(const uint8_t radio_mac[6],const uint8_t *p,size_t length,uint8_t receipt[HC_PEER_RECEIPT_SIZE]) {
    uint8_t response[HC_PAIR_HELLO_SIZE];
    esp_err_t err=hc_provisioning_pair_receive(radio_mac,p,length,response);
    if(err!=ESP_OK||memcmp(p,"HCQ1",4))return ESP_ERR_INVALID_ARG;
    hc_provisioned_config c;err=hc_provisioning_load(&c);
    if(err==ESP_OK && c.subbox && c.committed){
        memcpy(receipt,"HCR1",4);memcpy(receipt+4,p+4,32);p32(receipt+36,u32(p+36));p32(receipt+40,c.node_id);memcpy(receipt+44,radio_mac,6);
        err=mac(c.key,32,receipt,50,receipt+50);
    }else err=ESP_ERR_INVALID_STATE;
    memset(&c,0,sizeof(c));return err;
}
esp_err_t hc_provisioning_receipt(bool gateway_authenticated,uint8_t out[HC_ENROLLMENT_RECEIPT_SIZE]) {
    hc_provisioned_config c;esp_err_t err=hc_provisioning_load(&c);if(err!=ESP_OK)return err;
    if((c.subbox&&!gateway_authenticated)||(!c.subbox&&!parent_verified)){memset(&c,0,sizeof(c));return ESP_ERR_INVALID_STATE;}
    memcpy(out,"HCA1",4);memcpy(out+4,c.claim_nonce,32);p32(out+36,c.node_id);p32(out+40,c.parent_id);out[44]=c.subbox?0:3;out[45]=3;
    err=mac(c.key,32,out,46,out+46);memset(&c,0,sizeof(c));return err;
}
esp_err_t hc_provisioning_commit(void) {
    esp_err_t err=lock_config();if(err!=ESP_OK)return err;
    hc_provisioned_config c;err=hc_provisioning_load(&c);
    if(err==ESP_OK){c.committed=1;err=save(&c);}memset(&c,0,sizeof(c));xSemaphoreGive(config_lock);return err;
}
esp_err_t hc_provisioning_revision(uint32_t revision) {
    esp_err_t err=lock_config();if(err!=ESP_OK)return err;
    hc_provisioned_config c;err=hc_provisioning_load(&c);
    if(err==ESP_OK && revision<c.revision)err=ESP_ERR_INVALID_ARG;
    if(err==ESP_OK){c.revision=revision;err=save(&c);}
    memset(&c,0,sizeof(c));xSemaphoreGive(config_lock);return err;
}
esp_err_t hc_provisioning_reset(void) {
    esp_err_t err=lock_config();if(err!=ESP_OK)return err;
    nvs_handle_t h;err=nvs_open("hc_core",NVS_READWRITE,&h);
    if(err==ESP_OK){err=nvs_erase_all(h);if(err==ESP_OK)err=nvs_commit(h);nvs_close(h);}
    xSemaphoreGive(config_lock);return err;
}
static void restart_task(void *arg) { (void)arg;vTaskDelay(pdMS_TO_TICKS(2000));esp_restart(); }
static esp_err_t response(const void *data,size_t len,uint8_t **out,ssize_t *outlen) {
    *out=(uint8_t*)malloc(len);if(!*out)return ESP_ERR_NO_MEM;memcpy(*out,data,len);*outlen=(ssize_t)len;return ESP_OK;
}
static esp_err_t info_endpoint(uint32_t session,const uint8_t *in,ssize_t inlen,uint8_t **out,ssize_t *outlen,void *ctx) {
    (void)session;(void)in;(void)inlen;(void)ctx;
    if(!hc_provisioning_active())return ESP_ERR_INVALID_STATE;
    uint8_t data[49]={0};memcpy(data,"HCI1",4);data[4]=is_subbox?1:2;
    esp_err_t err=esp_efuse_mac_get_default(data+5);if(err!=ESP_OK)return err;
    err=esp_wifi_get_mac(WIFI_IF_STA,data+11);if(err!=ESP_OK)return err;
    memcpy(data+17,challenge,32);return response(data,sizeof(data),out,outlen);
}
static esp_err_t config_endpoint(uint32_t session,const uint8_t *in,ssize_t inlen,uint8_t **out,ssize_t *outlen,void *ctx) {
    (void)session;(void)ctx;
    if(inlen<0)return ESP_ERR_INVALID_ARG;
    esp_err_t err=hc_provisioning_apply(in,(size_t)inlen);if(err!=ESP_OK)return err;
    if(xTaskCreate(restart_task,"hc_apply",2048,NULL,3,NULL)!=pdPASS)return ESP_ERR_NO_MEM;
    return response("STORED",6,out,outlen);
}
static esp_err_t status_endpoint(uint32_t session,const uint8_t *in,ssize_t inlen,uint8_t **out,ssize_t *outlen,void *ctx) {
    (void)session;(void)in;(void)inlen;(void)ctx;
    if(!hc_provisioning_active())return ESP_ERR_INVALID_STATE;
    hc_provisioned_config c = {0};
    if (hc_provisioning_load(&c) == ESP_OK && c.committed) {
        return response("{\"status\":\"PROVISIONED\"}",24,out,outlen);
    }
    uint8_t receipt[78];esp_err_t err=hc_provisioning_receipt(false,receipt);if(err!=ESP_OK)return response("PENDING",7,out,outlen);
    return response(receipt,sizeof(receipt),out,outlen);
}
void hc_provisioning_stop(void) {
    if(server){protocomm_httpd_stop(server);protocomm_delete(server);server=NULL;esp_wifi_set_mode(WIFI_MODE_STA);}
    memset(factory_secret,0,sizeof(factory_secret));memset(setup,0,sizeof(setup));memset(challenge,0,32);deadline=0;
}
static void expiry_task(void *arg) {
    uint32_t generation=(uint32_t)(uintptr_t)arg;
    while(server&&window_generation==generation&&esp_timer_get_time()<deadline)vTaskDelay(pdMS_TO_TICKS(250));
    if(server&&window_generation==generation)hc_provisioning_stop();
    vTaskDelete(NULL);
}
esp_err_t hc_provisioning_start(bool subbox) {
    if(server)return ESP_ERR_INVALID_STATE;
    nvs_handle_t h;esp_err_t err=nvs_open("hc_factory",NVS_READONLY,&h);
    if(err!=ESP_OK)return err;
    char password[65]={0};size_t keylen=32,poplen=sizeof(setup),passlen=sizeof(password);uint8_t kind=0;
    err=nvs_get_blob(h,"secret",factory_secret,&keylen);
    if(err==ESP_OK)err=nvs_get_str(h,"setup",setup,&poplen);
    if(err==ESP_OK)err=nvs_get_str(h,"ap_pass",password,&passlen);
    if(err==ESP_OK)err=nvs_get_u8(h,"kind",&kind);
    nvs_close(h);
    if(err!=ESP_OK)return err;
    if(keylen!=32||poplen<9||passlen<13||kind!=(subbox?1:2))return ESP_ERR_INVALID_ARG;
    uint8_t base[6];err=esp_efuse_mac_get_default(base);if(err!=ESP_OK)return err;
    wifi_config_t ap={0};snprintf((char *)ap.ap.ssid,sizeof(ap.ap.ssid),"siciot_%s_%02X%02X%02X",subbox?"sub":"act",base[3],base[4],base[5]);
    ap.ap.ssid_len=(uint8_t)strlen((char *)ap.ap.ssid);memcpy(ap.ap.password,password,strlen(password));memset(password,0,sizeof(password));
    ap.ap.channel=1;ap.ap.authmode=WIFI_AUTH_WPA2_PSK;ap.ap.max_connection=1;ap.ap.pmf_cfg.capable=true;
    if(!esp_netif_get_handle_from_ifkey("WIFI_AP_DEF")&&!esp_netif_create_default_wifi_ap())return ESP_ERR_NO_MEM;
    err=esp_wifi_set_mode(WIFI_MODE_APSTA);
    if(err==ESP_OK)err=esp_wifi_set_config(WIFI_IF_AP,&ap);
    memset(&ap,0,sizeof(ap));if(err!=ESP_OK)return err;
    server=protocomm_new();if(!server)return ESP_ERR_NO_MEM;
    esp_log_level_set("security1", ESP_LOG_WARN);
    protocomm_httpd_config_t cfg = {0};
    const protocomm_http_server_config_t defaults = PROTOCOMM_HTTPD_DEFAULT_CONFIG();
    cfg.data.config = defaults;
    cfg.data.config.stack_size = 6144;
    err=protocomm_httpd_start(server,&cfg);
    security_params.data=(const uint8_t *)setup;security_params.len=strlen(setup);
    if(err==ESP_OK)err=protocomm_set_security(server,"prov-session",&protocomm_security1,&security_params);
    if(err==ESP_OK)err=protocomm_add_endpoint(server,"hc-info",info_endpoint,NULL);
    if(err==ESP_OK)err=protocomm_add_endpoint(server,"hc-config",config_endpoint,NULL);
    if(err==ESP_OK)err=protocomm_add_endpoint(server,"hc-status",status_endpoint,NULL);
    if(err!=ESP_OK){hc_provisioning_stop();return err;}
    is_subbox=subbox;esp_fill_random(challenge,32);deadline=esp_timer_get_time()+180000000ULL;window_generation++;
    if(xTaskCreate(expiry_task,"hc_pair_timeout",3072,(void *)(uintptr_t)window_generation,3,NULL)!=pdPASS){hc_provisioning_stop();return ESP_ERR_NO_MEM;}
    return ESP_OK;
}

static void button_task(void *arg) {
    bool subbox=(bool)(uintptr_t)arg,opened=false;
    int64_t pressed=0;
    for(;;){
        int64_t now=esp_timer_get_time();
        if(gpio_get_level(GPIO_NUM_0)==0){
            if(!pressed)pressed=now;
            if(!opened && now-pressed>=3000000){opened=true;hc_provisioning_start(subbox);}
            if(now-pressed>=10000000 && hc_provisioning_reset()==ESP_OK){

                while(gpio_get_level(GPIO_NUM_0)==0)vTaskDelay(pdMS_TO_TICKS(50));
                esp_restart();
            }
        }else{pressed=0;opened=false;}
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}
esp_err_t hc_provisioning_button_init(bool subbox) {
    gpio_config_t cfg={.pin_bit_mask=1ULL<<GPIO_NUM_0,.mode=GPIO_MODE_INPUT,.pull_up_en=GPIO_PULLUP_ENABLE};
    esp_err_t err=gpio_config(&cfg);if(err!=ESP_OK)return err;
    return xTaskCreate(button_task,"hc_physical",4096,(void *)(uintptr_t)subbox,3,NULL)==pdPASS?ESP_OK:ESP_ERR_NO_MEM;
}
