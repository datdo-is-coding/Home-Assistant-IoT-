#include "hc_factory.h"
#ifdef HC_FACTORY_BOOTSTRAP
#include "hc_provisioning.h"
#include "esp_mac.h"
#include "nvs.h"
#include <string.h>
#include <stdio.h>

extern const unsigned char factory_start[] asm("_binary_hc_factory_bundle_start");
extern const unsigned char factory_end[] asm("_binary_hc_factory_bundle_end");
_Static_assert(sizeof(hc_provisioned_config)==752,"factory enrollment ABI");

static esp_err_t blob(nvs_handle_t h,const char *key,const void *value,size_t size) {
    static unsigned char old[752];size_t length=sizeof(old);
    esp_err_t err=nvs_get_blob(h,key,old,&length);
    if(err==ESP_OK)return length==size && memcmp(old,value,size)==0?ESP_OK:ESP_ERR_INVALID_STATE;
    return err==ESP_ERR_NVS_NOT_FOUND?nvs_set_blob(h,key,value,size):err;
}
static esp_err_t text(nvs_handle_t h,const char *key,const char *value) {
    char old[65];size_t length=sizeof(old);
    esp_err_t err=nvs_get_str(h,key,old,&length);
    if(err==ESP_OK)return strcmp(old,value)==0?ESP_OK:ESP_ERR_INVALID_STATE;
    return err==ESP_ERR_NVS_NOT_FOUND?nvs_set_str(h,key,value):err;
}
esp_err_t hc_factory_apply(void) {
    if(factory_end-factory_start!=957 || memcmp(factory_start,"HCF2",4)!=0 || factory_start[11]!=0)return ESP_ERR_INVALID_ARG;
    uint8_t mac[6];esp_err_t err=esp_efuse_mac_get_default(mac);
    if(err!=ESP_OK || memcmp(mac,factory_start+4,6)!=0)return ESP_ERR_INVALID_MAC;
    /* Only app_main calls the factory bootstrap; keep NVS work off its small stack. */
    static hc_provisioned_config c,existing;
    uint8_t kind=factory_start[10];memcpy(&c,factory_start+12,sizeof(c));
    const uint8_t *compat=factory_start+764,*secret=factory_start+796;
    const char *setup=(const char*)factory_start+828,*password=(const char*)factory_start+893;
    char id[16];snprintf(id,sizeof(id),"HC-%02X%02X%02X%02X%02X%02X",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
    if((kind!=1 && kind!=2) || c.schema!=1 || !c.node_id || !c.revision || c.subbox!=(kind==1) ||
       c.peer_count>4 || c.channel<1 || c.channel>13 || c.ota_pubkey[0]!=4 ||
       memcmp(c.factory_id,id,16)!=0 || !memchr(setup,0,65) || !memchr(password,0,64) ||
       strlen(setup)<12 || strlen(password)<12 || (!c.subbox && (c.peer_count!=1 || !c.parent_id)))return ESP_ERR_INVALID_ARG;
    if(hc_provisioning_load(&existing)==ESP_OK) {
        /* A factory recovery image must not reset later enrollment/key rotation. */
        bool same=existing.node_id==c.node_id && existing.subbox==c.subbox && memcmp(existing.factory_id,c.factory_id,16)==0;
        memset(&existing,0,sizeof(existing));memset(&c,0,sizeof(c));
        return same?ESP_OK:ESP_ERR_INVALID_STATE;
    }
    nvs_handle_t h;err=nvs_open("hc_factory",NVS_READWRITE,&h);if(err!=ESP_OK)return err;
    uint8_t old_kind=0;err=nvs_get_u8(h,"kind",&old_kind);
    if(err==ESP_ERR_NVS_NOT_FOUND)err=nvs_set_u8(h,"kind",kind);
    else if(err==ESP_OK && old_kind!=kind)err=ESP_ERR_INVALID_STATE;
    if(err==ESP_OK)err=blob(h,"secret",secret,32);
    if(err==ESP_OK)err=text(h,"setup",setup);
    if(err==ESP_OK)err=text(h,"ap_pass",password);
    if(err==ESP_OK)err=nvs_commit(h);
    nvs_close(h);if(err!=ESP_OK)return err;
    err=nvs_open("hc_core",NVS_READWRITE,&h);if(err!=ESP_OK)return err;
    if(err==ESP_OK)err=blob(h,"enrollment",&c,sizeof(c));
    if(err==ESP_OK)err=blob(h,"ota_compat",compat,32);
    if(err==ESP_OK)err=nvs_commit(h);
    nvs_close(h);
    memset(&c,0,sizeof(c));return err;
}
#else
esp_err_t hc_factory_apply(void) {return ESP_OK;}
#endif
