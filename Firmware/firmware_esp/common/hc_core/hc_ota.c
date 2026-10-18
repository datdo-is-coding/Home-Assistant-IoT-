#include "hc_ota.h"
#include "hc_provisioning.h"
#include "esp_ota_ops.h"
#include "esp_partition.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "nvs.h"
#include "psa/crypto.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include <string.h>
#include <stdatomic.h>

typedef struct {uint8_t type,len,data[HC_MAX_PAYLOAD];} ota_item;
static QueueHandle_t ota_queue;
static hc_ota_emit_fn emit;
static uint8_t public_key[65],manifest[132],pending[68];
static char model[16];
static uint32_t offset,size;
static esp_ota_handle_t handle;
static const esp_partition_t *target;
static bool transferring,has_pending;
static atomic_bool health_ready;
static int64_t last_activity;
static uint32_t get32(const uint8_t *p) {return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void progress(uint8_t status) {
    uint8_t p[5];for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(offset>>(8*i));p[4]=status;
    if(emit)emit(HC_OTA_PROGRESS,p,sizeof(p));
}
static bool hash_partition(const esp_partition_t *partition,uint32_t length,uint8_t out[32]) {
    psa_hash_operation_t op=PSA_HASH_OPERATION_INIT;
    if(psa_hash_setup(&op,PSA_ALG_SHA_256)!=PSA_SUCCESS)return false;
    uint8_t buffer[1024];size_t actual=0;
    for(uint32_t at=0;at<length;) {
        size_t count=length-at<sizeof(buffer)?length-at:sizeof(buffer);
        if(esp_partition_read(partition,at,buffer,count)!=ESP_OK || psa_hash_update(&op,buffer,count)!=PSA_SUCCESS) {psa_hash_abort(&op);return false;}
        at+=(uint32_t)count;taskYIELD();
    }
    return psa_hash_finish(&op,out,32,&actual)==PSA_SUCCESS && actual==32;
}
static bool verify(const uint8_t *m) {
    if(!memchr(m,0,16) || !memchr(m+16,0,16) || strcmp((const char*)m,model)!=0)return false;
    uint32_t length=get32(m+32);if(!length || length>0x2f0000)return false;
    psa_key_attributes_t attr=PSA_KEY_ATTRIBUTES_INIT;
    psa_set_key_type(&attr,PSA_KEY_TYPE_ECC_PUBLIC_KEY(PSA_ECC_FAMILY_SECP_R1));
    psa_set_key_bits(&attr,256);psa_set_key_usage_flags(&attr,PSA_KEY_USAGE_VERIFY_MESSAGE);
    psa_set_key_algorithm(&attr,PSA_ALG_ECDSA(PSA_ALG_SHA_256));
    mbedtls_svc_key_id_t key=0;
    psa_status_t result=psa_import_key(&attr,public_key,65,&key);
    if(result==PSA_SUCCESS)result=psa_verify_message(key,PSA_ALG_ECDSA(PSA_ALG_SHA_256),m,68,m+68,64);
    if(key) psa_destroy_key(key);
    psa_reset_key_attributes(&attr);
    return result==PSA_SUCCESS;
}
static void abort_transfer(void) {
    if(transferring)esp_ota_abort(handle);
    transferring=false;handle=0;progress(2);
}
static void start(const ota_item *item) {
    if(item->len!=132 || !verify(item->data)){progress(2);return;}
    if(transferring && memcmp(manifest,item->data,132)==0){progress(0);return;}
    if(transferring)abort_transfer();
    target=esp_ota_get_next_update_partition(NULL);size=get32(item->data+32);
    if(!target || size>target->size || target==esp_ota_get_running_partition()){progress(2);return;}
    if(esp_ota_begin(target,OTA_WITH_SEQUENTIAL_WRITES,&handle)!=ESP_OK){progress(2);return;}
    memcpy(manifest,item->data,132);offset=0;transferring=true;last_activity=esp_timer_get_time();progress(0);
}
static void chunk(const ota_item *item) {
    if(!transferring || item->len<=4)return;
    uint32_t at=get32(item->data);size_t length=item->len-4;
    if(at>size || length>size-at){abort_transfer();return;}
    if(at<offset) {
        uint8_t old[192];
        if(at+length>offset || esp_partition_read(target,at,old,length)!=ESP_OK || memcmp(old,item->data+4,length)!=0){abort_transfer();return;}
        progress(0);return;
    }
    if(at!=offset){progress(0);return;}
    if(esp_ota_write(handle,item->data+4,length)!=ESP_OK){abort_transfer();return;}
    offset+=(uint32_t)length;last_activity=esp_timer_get_time();progress(0);
}
static void finish(void) {
    if(!transferring || offset!=size){progress(2);return;}
    uint8_t digest[32];
    if(!hash_partition(target,size,digest) || memcmp(digest,manifest+36,32)!=0){abort_transfer();return;}
    esp_err_t result=esp_ota_end(handle);transferring=false;handle=0;
    if(result!=ESP_OK){progress(2);return;}
    esp_app_desc_t candidate,current;
    if(esp_ota_get_partition_description(target,&candidate)!=ESP_OK ||
       esp_ota_get_partition_description(esp_ota_get_running_partition(),&current)!=ESP_OK ||
       memcmp(candidate.version,manifest+16,16)!=0 ||
       candidate.secure_version<current.secure_version){progress(2);return;}
    nvs_handle_t h;result=nvs_open("hc_core",NVS_READWRITE,&h);
    if(result==ESP_OK){result=nvs_set_blob(h,"ota_pending",manifest,68);if(result==ESP_OK)result=nvs_commit(h);nvs_close(h);}
    if(result!=ESP_OK || esp_ota_set_boot_partition(target)!=ESP_OK){progress(2);return;}
    progress(1);vTaskDelay(pdMS_TO_TICKS(500));esp_restart();
}
static void worker(void *arg) {
    (void)arg;ota_item item;int64_t last_result=0;uint8_t result[49]={0};bool checked=false;
    for(;;) {
        if(xQueueReceive(ota_queue,&item,pdMS_TO_TICKS(100))==pdTRUE) {
            if(item.type==HC_OTA_START)start(&item);
            else if(item.type==HC_OTA_CHUNK)chunk(&item);
            else if(item.type==HC_OTA_OFFER && item.len==0)finish();
            else if(item.type==HC_OTA_ABORT)abort_transfer();
            else if(item.type==HC_OTA_RESULT && item.len==0 && has_pending) {
                nvs_handle_t h;if(nvs_open("hc_core",NVS_READWRITE,&h)==ESP_OK){
                    esp_err_t err=nvs_erase_key(h,"ota_pending");if(err==ESP_OK)err=nvs_commit(h);nvs_close(h);if(err==ESP_OK)has_pending=false;
                }
            }
        }
        int64_t now=esp_timer_get_time();
        if(transferring && now-last_activity>30000000)abort_transfer();
        if(has_pending && !checked && now>120000000) {
            esp_ota_img_states_t state;
            if(esp_ota_get_state_partition(esp_ota_get_running_partition(),&state)==ESP_OK && state==ESP_OTA_IMG_PENDING_VERIFY)
                esp_ota_mark_app_invalid_rollback_and_reboot();
        }
        if(has_pending && atomic_load(&health_ready) && hc_runtime_online() && now>30000000 && now-last_result>5000000) {
            if(!checked) {
                const esp_partition_t *running=esp_ota_get_running_partition();uint8_t digest[32];
                bool matches=hash_partition(running,get32(pending+32),digest) && memcmp(digest,pending+36,32)==0;
                esp_ota_img_states_t state;
                if(!matches && esp_ota_get_state_partition(running,&state)==ESP_OK && state==ESP_OTA_IMG_PENDING_VERIFY)
                    esp_ota_mark_app_invalid_rollback_and_reboot();
                memcpy(result,pending+16,16);memcpy(result+16,pending+36,32);
                result[48]=matches && esp_ota_mark_app_valid_cancel_rollback()==ESP_OK?1:2;
                checked=true;
            }
            if(emit) emit(HC_OTA_RESULT,result,sizeof(result));
            last_result=now;
        }
    }
}
void hc_ota_health_ready(void) {atomic_store(&health_ready,true);}
bool hc_ota_receive(uint8_t type,const uint8_t *data,size_t length) {
    if(!ota_queue || length>HC_MAX_PAYLOAD)return false;
    ota_item item={.type=type,.len=(uint8_t)length};if(length)memcpy(item.data,data,length);
    return xQueueSend(ota_queue,&item,0)==pdTRUE;
}
esp_err_t hc_ota_init(hc_ota_emit_fn callback,bool subbox) {
    (void)subbox;
    hc_provisioned_config c;esp_err_t err=hc_provisioning_load(&c);if(err!=ESP_OK)return err;
    if(c.ota_pubkey[0]!=4){memset(&c,0,sizeof(c));return ESP_OK;}
    if(strnlen(c.model,sizeof(c.model))>=sizeof(model)){memset(&c,0,sizeof(c));return ESP_ERR_INVALID_ARG;}
    memcpy(public_key,c.ota_pubkey,65);strcpy(model,c.model);memset(&c,0,sizeof(c));
    nvs_handle_t h;err=nvs_open("hc_core",NVS_READONLY,&h);if(err!=ESP_OK)return err;
    size_t pending_len=sizeof(pending);has_pending=nvs_get_blob(h,"ota_pending",pending,&pending_len)==ESP_OK && pending_len==68;
    nvs_close(h);
    emit=callback;ota_queue=xQueueCreate(4,sizeof(ota_item));if(!ota_queue)return ESP_ERR_NO_MEM;
    if(xTaskCreate(worker,"hc_ota",6144,NULL,2,NULL)!=pdPASS){vQueueDelete(ota_queue);ota_queue=NULL;return ESP_ERR_NO_MEM;}
    return ESP_OK;
}
