#include "hc_ota.h"
#include "hc_provisioning.h"
#include "hc_ota_manifest.h"
#include "esp_ota_ops.h"
#include "esp_image_format.h"
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
static uint8_t public_key[65],manifest[HC_OTA_V2_TARGET_SIZE];
static size_t manifest_length;
static hc_ota_policy policy;
static hc_ota_target active_target,pending_target;
static uint32_t offset,size;
static esp_ota_handle_t handle;
static const esp_partition_t *target;
static bool transferring,has_pending;
static atomic_bool health_ready;
static int64_t last_activity;
static uint32_t get32(const uint8_t *p) {return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static uint64_t get64(const uint8_t *p) {return (uint64_t)get32(p)|((uint64_t)get32(p+4)<<32);}
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
static bool verify(void *ctx,const uint8_t *m,size_t header_size,const uint8_t signature[64]) {
    (void)ctx;
    psa_key_attributes_t attr=PSA_KEY_ATTRIBUTES_INIT;
    psa_set_key_type(&attr,PSA_KEY_TYPE_ECC_PUBLIC_KEY(PSA_ECC_FAMILY_SECP_R1));
    psa_set_key_bits(&attr,256);psa_set_key_usage_flags(&attr,PSA_KEY_USAGE_VERIFY_MESSAGE);
    psa_set_key_algorithm(&attr,PSA_ALG_ECDSA(PSA_ALG_SHA_256));
    mbedtls_svc_key_id_t key=0;
    psa_status_t result=psa_import_key(&attr,public_key,65,&key);
    if(result==PSA_SUCCESS)result=psa_verify_message(key,PSA_ALG_ECDSA(PSA_ALG_SHA_256),m,header_size,signature,64);
    if(key) psa_destroy_key(key);
    psa_reset_key_attributes(&attr);
    return result==PSA_SUCCESS;
}
static void abort_transfer(void) {
    if(transferring)esp_ota_abort(handle);
    transferring=false;handle=0;progress(2);
}
static void start(const ota_item *item) {
    hc_ota_target parsed;
    esp_ota_img_states_t state;
    const esp_partition_t *running=esp_ota_get_running_partition();
    if(has_pending || (esp_ota_get_state_partition(running,&state)==ESP_OK && state==ESP_OTA_IMG_PENDING_VERIFY) ||
       !hc_ota_manifest_parse(item->data,item->len,&policy,verify,NULL,&parsed)){progress(2);return;}
    if(transferring && manifest_length==item->len && memcmp(manifest,item->data,item->len)==0){progress(0);return;}
    if(transferring)abort_transfer();
    target=esp_ota_get_next_update_partition(NULL);size=parsed.size;
    if(!target || size>target->size || target==running){progress(2);return;}
    if(esp_ota_begin(target,OTA_WITH_SEQUENTIAL_WRITES,&handle)!=ESP_OK){progress(2);return;}
    memcpy(manifest,item->data,item->len);manifest_length=item->len;active_target=parsed;
    offset=0;transferring=true;last_activity=esp_timer_get_time();progress(0);
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
    if(!hash_partition(target,size,digest) || memcmp(digest,active_target.sha256,32)!=0){abort_transfer();return;}
    esp_err_t result=esp_ota_end(handle);transferring=false;handle=0;
    if(result!=ESP_OK){progress(2);return;}
    esp_app_desc_t candidate,current;
    if(esp_ota_get_partition_description(target,&candidate)!=ESP_OK ||
       esp_ota_get_partition_description(esp_ota_get_running_partition(),&current)!=ESP_OK ||
       !memchr(candidate.version,0,sizeof(candidate.version)) || strcmp(candidate.version,active_target.version)!=0 ||
       candidate.secure_version<current.secure_version){progress(2);return;}
    nvs_handle_t h;result=nvs_open("hc_core",NVS_READWRITE,&h);
    size_t pending_length=active_target.schema==1?HC_OTA_V1_HEADER_SIZE:HC_OTA_V2_TARGET_SIZE;
    if(result==ESP_OK){result=nvs_set_blob(h,"ota_pending",manifest,pending_length);if(result==ESP_OK)result=nvs_commit(h);nvs_close(h);}
    if(result!=ESP_OK || esp_ota_set_boot_partition(target)!=ESP_OK){progress(2);return;}
    progress(1);vTaskDelay(pdMS_TO_TICKS(500));esp_restart();
}
static bool finalize_pending(uint8_t result[49]) {
    const esp_partition_t *running=esp_ota_get_running_partition();
    esp_app_desc_t actual;esp_image_metadata_t metadata;uint8_t digest[32];
    if(!running)return false;
    esp_partition_pos_t position={.offset=running->address,.size=running->size};
    if(esp_ota_get_partition_description(running,&actual)!=ESP_OK ||
       !memchr(actual.version,0,sizeof(actual.version)) ||
       esp_image_verify(ESP_IMAGE_VERIFY_SILENT,&position,&metadata)!=ESP_OK ||
       !metadata.image_len || metadata.image_len>running->size ||
       !hash_partition(running,metadata.image_len,digest))return false;
    memset(result,0,49);memcpy(result,actual.version,15);memcpy(result+16,digest,32);result[48]=2;
    bool matches=metadata.image_len==pending_target.size && strcmp(actual.version,pending_target.version)==0 &&
                 memcmp(digest,pending_target.sha256,32)==0;
    if(!matches) {
        esp_ota_img_states_t state;
        if(esp_ota_get_state_partition(running,&state)==ESP_OK && state==ESP_OTA_IMG_PENDING_VERIFY)
            esp_ota_mark_app_invalid_rollback_and_reboot();
        return true;
    }
    if(esp_ota_mark_app_valid_cancel_rollback()!=ESP_OK)return false;
    if(pending_target.schema==2) {
        uint8_t confirmed[12];
        for(unsigned i=0;i<8;++i)confirmed[i]=(uint8_t)(pending_target.release_counter>>(8*i));
        for(unsigned i=0;i<4;++i)confirmed[8+i]=(uint8_t)(pending_target.security_epoch>>(8*i));
        nvs_handle_t h;esp_err_t err=nvs_open("hc_core",NVS_READWRITE,&h);
        if(err==ESP_OK){err=nvs_set_blob(h,"ota_confirm",confirmed,sizeof(confirmed));if(err==ESP_OK)err=nvs_commit(h);nvs_close(h);}
        if(err!=ESP_OK)return false;
        policy.confirmed_counter=pending_target.release_counter;policy.security_epoch=pending_target.security_epoch;
    }
    result[48]=1;return true;
}
static void worker(void *arg) {
    (void)arg;ota_item item;int64_t last_result=0;uint8_t result[49]={0};bool checked=false;
    for(;;) {
        if(xQueueReceive(ota_queue,&item,pdMS_TO_TICKS(100))==pdTRUE) {
            if(item.type==HC_OTA_START)start(&item);
            else if(item.type==HC_OTA_CHUNK)chunk(&item);
            else if(item.type==HC_OTA_OFFER && item.len==0)finish();
            else if(item.type==HC_OTA_ABORT)abort_transfer();
            else if(item.type==HC_OTA_RESULT && item.len==0 && has_pending && checked) {
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
        if(has_pending && atomic_load(&health_ready) && now>30000000 && now-last_result>5000000) {
            if(!checked) {
                checked=finalize_pending(result);
            }
            if(checked && emit) emit(HC_OTA_RESULT,result,sizeof(result));
            last_result=now;
        }
    }
}
void hc_ota_health_ready(void) {atomic_store(&health_ready,true);}
bool hc_ota_receive(uint8_t type,const uint8_t *data,size_t length) {
    if(!ota_queue || length>HC_MAX_PAYLOAD || (length && !data))return false;
    ota_item item={.type=type,.len=(uint8_t)length};if(length)memcpy(item.data,data,length);
    return xQueueSend(ota_queue,&item,0)==pdTRUE;
}
esp_err_t hc_ota_init(hc_ota_emit_fn callback,bool subbox) {
    hc_provisioned_config c;esp_err_t err=hc_provisioning_load(&c);if(err!=ESP_OK)return err;
    if(c.ota_pubkey[0]!=4){memset(&c,0,sizeof(c));return ESP_OK;}
    if(strnlen(c.model,sizeof(c.model))>=sizeof(policy.model)){memset(&c,0,sizeof(c));return ESP_ERR_INVALID_ARG;}
    policy=(hc_ota_policy){.role=subbox?HC_OTA_ROLE_SUBBOX:HC_OTA_ROLE_ACTIONBOX,
        .agent_version=HC_OTA_AGENT_VERSION,.bootloader_api=HC_OTA_BOOTLOADER_API,
        .protocol_version=HC_VERSION,.max_size=HC_OTA_MAX_IMAGE_SIZE};
    memcpy(public_key,c.ota_pubkey,65);strcpy(policy.model,c.model);memset(&c,0,sizeof(c));
    uint8_t digest[32];size_t digest_len;
    if(psa_crypto_init()!=PSA_SUCCESS ||
       psa_hash_compute(PSA_ALG_SHA_256,public_key,sizeof(public_key),digest,sizeof(digest),&digest_len)!=PSA_SUCCESS || digest_len!=32)return ESP_FAIL;
    policy.key_id=get32(digest);
    nvs_handle_t h;err=nvs_open("hc_core",NVS_READONLY,&h);if(err!=ESP_OK)return err;
    size_t length=sizeof(policy.compatibility);err=nvs_get_blob(h,"ota_compat",policy.compatibility,&length);
    if(err==ESP_OK && length==32)policy.has_compatibility=true;
    else if(err!=ESP_ERR_NVS_NOT_FOUND){nvs_close(h);return ESP_ERR_INVALID_STATE;}
    uint8_t confirmed[12];length=sizeof(confirmed);err=nvs_get_blob(h,"ota_confirm",confirmed,&length);
    if(err==ESP_OK && length==sizeof(confirmed)) {
        policy.confirmed_counter=get64(confirmed);policy.security_epoch=get32(confirmed+8);
    } else if(err!=ESP_ERR_NVS_NOT_FOUND){nvs_close(h);return ESP_ERR_INVALID_STATE;}
    uint8_t pending[HC_OTA_V2_TARGET_SIZE];length=sizeof(pending);
    err=nvs_get_blob(h,"ota_pending",pending,&length);nvs_close(h);has_pending=false;
    if(err==ESP_OK && length==HC_OTA_V2_TARGET_SIZE) {
        hc_ota_policy stored=policy;stored.confirmed_counter=0;
        has_pending=hc_ota_manifest_parse(pending,length,&stored,verify,NULL,&pending_target) &&
                    pending_target.release_counter>=policy.confirmed_counter;
        if(!has_pending)return ESP_ERR_INVALID_STATE;
    } else if(err==ESP_OK && length==HC_OTA_V1_HEADER_SIZE) {
        if(!memchr(pending,0,16) || !memchr(pending+16,0,16) || strcmp((const char*)pending,policy.model)!=0 ||
           !get32(pending+32) || get32(pending+32)>HC_OTA_MAX_IMAGE_SIZE)return ESP_ERR_INVALID_STATE;
        pending_target=(hc_ota_target){.schema=1,.size=get32(pending+32)};
        memcpy(pending_target.version,pending+16,16);memcpy(pending_target.sha256,pending+36,32);has_pending=true;
    } else if(err!=ESP_ERR_NVS_NOT_FOUND)return ESP_ERR_INVALID_STATE;
    emit=callback;ota_queue=xQueueCreate(4,sizeof(ota_item));if(!ota_queue)return ESP_ERR_NO_MEM;
    if(xTaskCreate(worker,"hc_ota",6144,NULL,2,NULL)!=pdPASS){vQueueDelete(ota_queue);ota_queue=NULL;return ESP_ERR_NO_MEM;}
    return ESP_OK;
}
