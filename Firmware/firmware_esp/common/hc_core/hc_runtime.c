#include "hc_runtime.h"
#include "hc_ota.h"
#include "hc_provisioning.h"
#include "esp_system.h"
#include "nvs.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "esp_now.h"
#include "esp_wifi.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "psa/crypto.h"
#include <string.h>
#include <math.h>
#include <stdatomic.h>

#define HC_PEERS 4

typedef struct { uint32_t node; uint8_t mac[6], lmk[16]; } peer;
typedef struct { uint8_t mac[6], data[HC_MAX_FRAME]; uint16_t len; bool mqtt; int64_t arrived; } rx_item;
typedef struct { uint64_t id; uint8_t channel,state,status; uint32_t revision; } ack_entry;
static atomic_bool enabled, registered;
static uint8_t claim_nonce[32];
static bool is_subbox;
static uint32_t node_id, parent_id, revision, sequence;
static uint64_t boot_id;
static uint8_t key[32], nonce[16];
static peer peers[HC_PEERS];
static unsigned peer_count;
static hc_replay gateway_window;
typedef struct {uint8_t type,len,data[HC_MAX_PAYLOAD];} tx_item;
static QueueHandle_t queue,tx_queue;
static hc_send_up_fn send_up;
static hc_apply_fn apply_relay;
static hc_sample_fn sample_channel;
static ack_entry acks[32];
static unsigned next_ack;
static uint64_t channel_generation[3];
static atomic_int_fast64_t last_gateway;
static bool handshake_pending=true;

static uint32_t u32(const uint8_t *p) { return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24); }
static void p32(uint8_t *p,uint32_t v) { for(unsigned i=0;i<4;++i) p[i]=(uint8_t)(v>>(8*i)); }
static void p64(uint8_t *p,uint64_t v) { for(unsigned i=0;i<8;++i) p[i]=(uint8_t)(v>>(8*i)); }
static int mac(void *ctx,const uint8_t *data,size_t len,uint8_t out[16]) {
    (void)ctx;
    psa_key_attributes_t attr=PSA_KEY_ATTRIBUTES_INIT;
    psa_set_key_type(&attr,PSA_KEY_TYPE_HMAC);
    psa_set_key_bits(&attr,256);
    psa_set_key_usage_flags(&attr,PSA_KEY_USAGE_SIGN_MESSAGE);
    psa_set_key_algorithm(&attr,PSA_ALG_HMAC(PSA_ALG_SHA_256));
    mbedtls_svc_key_id_t handle=0;
    uint8_t digest[32]; size_t length=0;
    psa_status_t result=psa_import_key(&attr,key,sizeof(key),&handle);
    if(result==PSA_SUCCESS) result=psa_mac_compute(handle,PSA_ALG_HMAC(PSA_ALG_SHA_256),data,len,digest,sizeof(digest),&length);
    if(handle) psa_destroy_key(handle);
    psa_reset_key_attributes(&attr);
    if(result!=PSA_SUCCESS || length!=32) {
        static bool reported;
        if(!reported) {ESP_LOGE("HC","Frame authentication failed: PSA %ld, length %u",(long)result,(unsigned)length);reported=true;}
        return -1;
    }
    memcpy(out,digest,16); memset(digest,0,sizeof(digest)); return 0;
}
static bool send_frame(uint8_t type,const uint8_t *payload,size_t len,uint64_t id) {
    if(len>HC_MAX_PAYLOAD || sequence==UINT32_MAX) return false;
    hc_frame f={0}; uint8_t raw[HC_MAX_FRAME];
    f.type=type; f.message_id=id?id:(uint64_t)sequence+1; f.source=node_id; f.destination=0;
    f.boot_id=boot_id; f.sequence=++sequence; f.config_rev=revision; f.payload_len=(uint8_t)len;
    if(payload) memcpy(f.payload,payload,len);
    int size=hc_encode(&f,raw,sizeof(raw),mac,NULL);
    if(size<0) return false;
    if(is_subbox) return send_up && send_up(raw,(size_t)size);
    return peer_count==1 && esp_now_send(peers[0].mac,raw,(size_t)size)==ESP_OK;
}
static void send_ack(const ack_entry *entry) {
    uint8_t payload[10]; p64(payload,entry->id); payload[8]=entry->status; payload[9]=entry->state;
    send_frame(HC_COMMAND_ACK,payload,sizeof(payload),0);
}
static void report(void) {
    uint8_t payload[32]={0};
    p64(payload,(uint64_t)(esp_timer_get_time()/1000));
    if(is_subbox) { send_frame(HC_HEARTBEAT,payload,8,0); return; }
    for(uint8_t ch=1;ch<=3;++ch) {
        bool on=false,valid=false; float current=0; uint16_t fault=0;
        if(!sample_channel || !sample_channel(ch,&on,&current,&valid,&fault)) { valid=false; fault|=0x8000; }
        if(!isfinite(current) || current<0 || current>1000) { valid=false; current=0; }
        uint8_t *p=payload+8+(ch-1)*8;
        p[0]=ch; p[1]=(on?1:0)|(valid?2:0);
        uint32_t bits; memcpy(&bits,&current,4); p32(p+2,bits);
        p[6]=(uint8_t)fault; p[7]=(uint8_t)(fault>>8);
    }
    send_frame(HC_STATE_REPORT,payload,sizeof(payload),0);
}
static bool known_mac(const uint8_t *mac_addr,uint32_t child) {
    for(unsigned i=0;i<peer_count;++i)
        if((!child || peers[i].node==child) && memcmp(peers[i].mac,mac_addr,6)==0) return true;
    return false;
}
static esp_err_t load_peers(const hc_provisioned_config *c) {
    for(unsigned i=0;i<c->peer_count;++i){
        esp_now_peer_info_t info={0};memcpy(info.peer_addr,c->peers[i].mac,6);memcpy(info.lmk,c->peers[i].lmk,16);
        info.ifidx=WIFI_IF_STA;info.channel=0;info.encrypt=true;
        esp_err_t err=esp_now_is_peer_exist(info.peer_addr)?esp_now_mod_peer(&info):esp_now_add_peer(&info);
        if(err!=ESP_OK)return err;
        peers[i].node=c->peers[i].node_id;memcpy(peers[i].mac,c->peers[i].mac,6);memcpy(peers[i].lmk,c->peers[i].lmk,16);
    }
    peer_count=c->peer_count;return ESP_OK;
}
static void enrollment_receipt(void) {
    uint8_t receipt[HC_ENROLLMENT_RECEIPT_SIZE];
    if(hc_provisioning_receipt(!handshake_pending && gateway_window.boot!=0,receipt)==ESP_OK)
        send_frame(HC_PAIR_REQUEST,receipt,sizeof(receipt),0);
}
static void process(rx_item *item) {
    if(!item->mqtt && item->len==HC_PAIR_HELLO_SIZE && (!memcmp(item->data,"HCQ1",4)||!memcmp(item->data,"HCS1",4))){
        uint8_t reply[HC_PAIR_HELLO_SIZE];
        if(hc_provisioning_pair_receive(item->mac,item->data,item->len,reply)!=ESP_OK)return;
        if(is_subbox){
            esp_now_send(item->mac,reply,sizeof(reply));
            uint8_t receipt[HC_PEER_RECEIPT_SIZE];
            if(hc_provisioning_peer_receipt(item->mac,item->data,item->len,receipt)==ESP_OK)
                send_frame(HC_PAIR_REQUEST,receipt,sizeof(receipt),0);
        }else enrollment_receipt();
        return;
    }

    uint32_t source=u32(item->data+14),dest=u32(item->data+18);
    if(is_subbox && registered && item->mqtt && dest!=node_id) {
        for(unsigned i=0;i<peer_count;++i) if(peers[i].node==dest) {
            esp_now_send(peers[i].mac,item->data,item->len); return;
        }
        return;
    }
    if(is_subbox && registered && !item->mqtt) {
        if(dest==0 && known_mac(item->mac,source) && send_up) send_up(item->data,item->len);
        return;
    }
    if(!is_subbox && !known_mac(item->mac,parent_id)) return;
    hc_frame f;
    if(hc_decode(item->data,item->len,&f,mac,NULL)!=HC_OK || f.source!=0 || f.destination!=node_id) return;
    if(f.type==HC_IDENTITY_CHALLENGE) {
        if(f.payload_len!=32 || memcmp(f.payload,nonce,16)!=0) return;
        if(!handshake_pending) {
            if(f.boot_id==gateway_window.boot) send_frame(HC_IDENTITY_RESPONSE,f.payload+16,16,0);
            return;
        }
        handshake_pending=false;
        hc_replay_admit(&gateway_window,f.boot_id);
        if(hc_replay_check(&gateway_window,f.boot_id,f.sequence)==HC_STALE) return;
        send_frame(HC_IDENTITY_RESPONSE,f.payload+16,16,0);
        last_gateway=esp_timer_get_time(); if(!registered)enrollment_receipt(); return;
    }
    hc_replay_result replay=hc_replay_check(&gateway_window,f.boot_id,f.sequence);
    if(replay!=HC_NEW && replay!=HC_DUPLICATE) return;
    last_gateway=esp_timer_get_time();
    if(f.type==HC_PAIR_ACCEPT && replay==HC_NEW){
        if(f.payload_len==32 && memcmp(f.payload,claim_nonce,32)==0){
            if(!registered && hc_provisioning_commit()==ESP_OK){
                registered=true;memset(&gateway_window,0,sizeof(gateway_window));handshake_pending=true;esp_fill_random(nonce,sizeof(nonce));last_gateway=0;
            }
        }else if(registered && is_subbox && f.payload_len==HC_PEER_GRANT_SIZE){
            if(hc_provisioning_install_peer(f.payload,f.payload_len)==ESP_OK){
                hc_provisioned_config c;if(hc_provisioning_load(&c)==ESP_OK)load_peers(&c);memset(&c,0,sizeof(c));
            }
        }
        return;
    }
    if(!registered)return;
    if((f.type==HC_UNPAIR || f.type==HC_FACTORY_RESET_REQUEST) && replay==HC_NEW){
        if(!is_subbox && apply_relay)for(uint8_t ch=1;ch<=3;++ch)apply_relay(ch,false);
        registered=false;
        if(hc_provisioning_reset()==ESP_OK)esp_restart();
        return;
    }
    if(f.type==HC_COMMAND && f.payload_len==18 && !is_subbox) {
        for(unsigned i=0;i<32;++i) if(acks[i].id==f.message_id) {
            if(acks[i].channel==f.payload[0] && acks[i].state==f.payload[1] && acks[i].revision==f.config_rev) send_ack(&acks[i]);
            return;
        }
        if(replay!=HC_NEW || f.config_rev!=revision || f.payload[0]<1 || f.payload[0]>3 || f.payload[1]>1) return;
        uint64_t deadline=(uint64_t)u32(f.payload+2)|((uint64_t)u32(f.payload+6)<<32);
        uint64_t now=(uint64_t)(esp_timer_get_time()/1000);
        uint64_t generation=(uint64_t)u32(f.payload+10)|((uint64_t)u32(f.payload+14)<<32);
        if(!hc_command_admit(channel_generation,f.payload[0],f.payload[1],generation,deadline,now)) return;
        ack_entry *entry=&acks[next_ack++%32];
        *entry=(ack_entry){.id=f.message_id,.channel=f.payload[0],.state=f.payload[1],.revision=revision,.status=3};
        if(apply_relay && apply_relay(entry->channel,entry->state!=0)) entry->status=2;
        send_ack(entry); report();
    } else if(f.type==HC_CONFIG_PUSH && f.payload_len==4) {
        uint32_t next=u32(f.payload);
        if(next<revision || next!=f.config_rev) return;
        if(next>revision) {
            if(hc_provisioning_revision(next)!=ESP_OK)return;
            revision=next; memset(acks,0,sizeof(acks));
        }
        send_frame(HC_CONFIG_ACK,f.payload,4,0); report();
    } else if(f.type==HC_STATE_SYNC_REQUEST) report();
    else if(f.type==HC_OTA_START || f.type==HC_OTA_CHUNK || f.type==HC_OTA_OFFER || f.type==HC_OTA_ABORT || f.type==HC_OTA_RESULT)
        hc_ota_receive(f.type,f.payload,f.payload_len);
}
static bool ota_emit(uint8_t type,const uint8_t *data,size_t len) {
    if(!tx_queue || len>HC_MAX_PAYLOAD)return false;
    tx_item item={.type=type,.len=(uint8_t)len};if(len)memcpy(item.data,data,len);
    return xQueueSend(tx_queue,&item,0)==pdTRUE;
}
static void worker(void *arg) {
    (void)arg;
    rx_item item;
    int64_t last_hello=0,last_report=0,last_hop=0,last_pair=0;
    unsigned channel=1;
    for(;;) {
        if(xQueueReceive(queue,&item,pdMS_TO_TICKS(20))==pdTRUE) process(&item);
        tx_item tx;if(xQueueReceive(tx_queue,&tx,0)==pdTRUE)send_frame(tx.type,tx.data,tx.len,0);
        int64_t now=esp_timer_get_time();
        if((!gateway_window.boot || now-last_gateway>15000000) && now-last_hello>1000000) {
            if(!handshake_pending) { esp_fill_random(nonce,sizeof(nonce)); handshake_pending=true; }
            send_frame(HC_HELLO,nonce,sizeof(nonce),0); last_hello=now;
        }
        if(!registered && now-last_pair>1000000){
            if(!is_subbox){uint8_t hello[HC_PAIR_HELLO_SIZE];if(hc_provisioning_pair_hello(hello)==ESP_OK)esp_now_send(peers[0].mac,hello,sizeof(hello));}
            if(gateway_window.boot)enrollment_receipt();
            last_pair=now;
        }
        if(registered && gateway_window.boot && now-last_report>2000000) { report(); last_report=now; }
        /* Keep the probe channel long enough for the Gateway challenge to return. */
        if(!is_subbox && !hc_provisioning_active() && now-last_gateway>15000000 && now-last_hop>250000 && now-last_hello>500000) {
            wifi_country_t country;
            if(esp_wifi_get_country(&country)==ESP_OK) {
                if(channel<country.schan || channel>=country.schan+country.nchan) channel=country.schan;
                esp_wifi_set_channel((uint8_t)channel++,WIFI_SECOND_CHAN_NONE);
            }
            last_hop=now;
        }
    }
}
bool hc_runtime_enabled(void) { return enabled; }
bool hc_runtime_registered(void) { return enabled && registered; }
uint32_t hc_runtime_peer_node_id(const uint8_t mac_addr[6]) {
    if(!registered||!mac_addr)return 0;
    for(unsigned i=0;i<peer_count;++i)if(memcmp(peers[i].mac,mac_addr,6)==0)return peers[i].node;
    return 0;
}
bool hc_runtime_online(void) { return enabled && registered && last_gateway && esp_timer_get_time()-last_gateway<15000000; }
bool hc_runtime_parent_mac(uint8_t out[6]) {
    if(!enabled || is_subbox || peer_count!=1 || !out) return false;
    memcpy(out,peers[0].mac,6); return true;
}
uint32_t hc_runtime_node_id(void) { return node_id; }
bool hc_runtime_trusted_peer(const uint8_t mac_addr[6]) { return enabled && known_mac(mac_addr,0); }
static bool enqueue(const uint8_t *mac_addr,const uint8_t *data,size_t len,bool mqtt) {
    if(!enabled || !queue || !data || len<54 || len>HC_MAX_FRAME || data[0]!='H' || data[1]!='C') return false;
    rx_item item={0}; if(mac_addr) memcpy(item.mac,mac_addr,6);
    memcpy(item.data,data,len); item.len=(uint16_t)len; item.mqtt=mqtt; item.arrived=esp_timer_get_time();
    return xQueueSend(queue,&item,0)==pdTRUE;
}
bool hc_runtime_receive_radio(const uint8_t mac_addr[6],const uint8_t *data,size_t length) {
    return enabled && known_mac(mac_addr,0) && enqueue(mac_addr,data,length,false);
}
bool hc_runtime_receive_mqtt(const uint8_t *data,size_t length) { return enqueue(NULL,data,length,true); }
esp_err_t hc_runtime_init(bool subbox,hc_send_up_fn uplink,hc_apply_fn apply,hc_sample_fn sample) {
    if(enabled)return ESP_ERR_INVALID_STATE;
    hc_provisioned_config c={0};
    esp_err_t err=hc_provisioning_load(&c);
    if(err==ESP_ERR_NVS_NOT_FOUND)return ESP_OK;
    if(err!=ESP_OK)return err;
    if((bool)c.subbox!=subbox){memset(&c,0,sizeof(c));return ESP_ERR_INVALID_ARG;}
    node_id=c.node_id;parent_id=c.parent_id;revision=c.revision;registered=c.committed!=0;
    memcpy(key,c.key,32);memcpy(claim_nonce,c.claim_nonce,32);
    if(psa_crypto_init()!=PSA_SUCCESS){memset(&c,0,sizeof(c));return ESP_FAIL;}
    err=esp_now_set_pmk(c.pmk);
    if(err==ESP_OK)err=load_peers(&c);
    if(err==ESP_OK && !subbox)err=esp_wifi_set_channel(c.channel,WIFI_SECOND_CHAN_NONE);
    memset(&c,0,sizeof(c));if(err!=ESP_OK)return err;
    is_subbox=subbox; send_up=uplink; apply_relay=apply; sample_channel=sample;
    esp_fill_random(&boot_id,sizeof(boot_id)); boot_id|=1; esp_fill_random(nonce,sizeof(nonce));
    queue=xQueueCreate(16,sizeof(rx_item)); if(!queue) return ESP_ERR_NO_MEM;
    tx_queue=xQueueCreate(8,sizeof(tx_item));if(!tx_queue){vQueueDelete(queue);return ESP_ERR_NO_MEM;}
    err=hc_ota_init(ota_emit,subbox);if(err!=ESP_OK){vQueueDelete(queue);vQueueDelete(tx_queue);return err;}
    enabled=true;
    if(xTaskCreate(worker,"hc_core",6144,NULL,4,NULL)!=pdPASS) { enabled=false; vQueueDelete(queue); queue=NULL; return ESP_ERR_NO_MEM; }
    ESP_LOGI("HC","Home Competition core active: node %lu",(unsigned long)node_id);
    return ESP_OK;
}
