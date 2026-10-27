"""Compile the device parser and verify the same signed target with Python P-256."""
import ctypes
import hashlib
import importlib.util
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Gateway'))
spec = importlib.util.spec_from_file_location('target_vectors', ROOT / 'Gateway/tests/test_fleet_ota_manifest.py')
vectors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vectors)
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

U8 = ctypes.c_uint8


class Policy(ctypes.Structure):
    _fields_ = [('role', U8), ('has_compatibility', ctypes.c_bool),
                ('compatibility', U8 * 32), ('model', ctypes.c_char * 16),
                ('agent_version', ctypes.c_uint16), ('bootloader_api', ctypes.c_uint16),
                ('protocol_version', ctypes.c_uint16), ('max_size', ctypes.c_uint32),
                ('key_id', ctypes.c_uint32), ('confirmed_counter', ctypes.c_uint64),
                ('security_epoch', ctypes.c_uint32)]


class Target(ctypes.Structure):
    _fields_ = [('schema', U8), ('version', ctypes.c_char * 16),
                ('size', ctypes.c_uint32), ('sha256', U8 * 32),
                ('release_counter', ctypes.c_uint64), ('security_epoch', ctypes.c_uint32),
                ('key_id', ctypes.c_uint32)]


VERIFY = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.POINTER(U8), ctypes.c_size_t, ctypes.POINTER(U8))


class DeviceManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        library = Path(cls.tmp.name) / 'manifest.so'
        source = ROOT / 'Firmware/firmware_esp/common/hc_core/hc_ota_manifest.c'
        subprocess.run(['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        str(source), '-o', str(library)], check=True, capture_output=True)
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.hc_ota_manifest_parse.argtypes = [ctypes.POINTER(U8), ctypes.c_size_t,
                                                ctypes.POINTER(Policy), VERIFY, ctypes.c_void_p,
                                                ctypes.POINTER(Target)]
        cls.lib.hc_ota_manifest_parse.restype = ctypes.c_bool

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.private, self.image, self.manifest = vectors.vector()
        self.packet = vectors.signed(self.private, self.manifest)
        self.policy = Policy(role=1, has_compatibility=True, model=b'HC-S1',
                             agent_version=2, bootloader_api=1, protocol_version=1,
                             max_size=0x2f0000, key_id=self.manifest['key_id'])
        self.policy.compatibility[:] = bytes.fromhex(self.manifest['compatibility_id'])
        self.verified_lengths = []

        @VERIFY
        def verify(_, header, length, signature):
            self.verified_lengths.append(length)
            raw_signature = bytes(signature[:64])
            der = utils.encode_dss_signature(int.from_bytes(raw_signature[:32], 'big'),
                                             int.from_bytes(raw_signature[32:], 'big'))
            try:
                self.private.public_key().verify(der, bytes(header[:length]), ec.ECDSA(hashes.SHA256()))
                return True
            except Exception:
                return False
        self.verify = verify

    def parse(self, packet=None):
        packet = self.packet if packet is None else packet
        result = Target()
        accepted = self.lib.hc_ota_manifest_parse((U8 * len(packet)).from_buffer_copy(packet),
                                                len(packet), ctypes.byref(self.policy), self.verify,
                                                None, ctypes.byref(result))
        return accepted, result

    def test_shared_vector_and_all_bytes_authenticated(self):
        accepted, target = self.parse()
        self.assertTrue(accepted)
        self.assertEqual(target.schema, 2)
        self.assertEqual(target.version, b'2.0.0')
        self.assertEqual(target.size, len(self.image))
        self.assertEqual(bytes(target.sha256), hashlib.sha256(self.image).digest())
        self.assertEqual(target.release_counter, self.manifest['release_counter'])
        self.assertEqual(target.security_epoch, 3)
        self.assertEqual(self.verified_lengths, [112])
        for at in range(176):
            packet = bytearray(self.packet)
            packet[at] ^= 1
            with self.subTest(at=at):
                self.assertFalse(self.parse(bytes(packet))[0])

    def test_device_policy_enforced(self):
        for name, bad in [('role', 2), ('has_compatibility', False), ('agent_version', 1),
                          ('bootloader_api', 0), ('protocol_version', 2), ('max_size', 1),
                          ('confirmed_counter', self.manifest['release_counter']),
                          ('security_epoch', 4), ('key_id', 0)]:
            old = getattr(self.policy, name)
            setattr(self.policy, name, bad)
            with self.subTest(name=name):
                self.assertFalse(self.parse()[0])
            setattr(self.policy, name, old)

    def test_signed_malformed_fields_are_still_rejected(self):
        for at, value in ((0, b'\x01'), (1, b'\x03'), (2, b'\x02'), (3, b'\x01'),
                          (4, b'\0' * 32), (36, b'a' * 16), (42, b'x'),
                          (52, struct.pack('<I', 0)), (52, struct.pack('<I', 0x2f0001)),
                          (56, b'\0' * 32), (88, b'\0\0'), (90, b'\0\0'),
                          (92, b'\0\0'), (94, b'\0\0'), (96, b'\0' * 8)):
            raw = bytearray(self.packet[:112])
            raw[at:at + len(value)] = value
            r, s = utils.decode_dss_signature(self.private.sign(bytes(raw), ec.ECDSA(hashes.SHA256())))
            packet = bytes(raw) + r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
            with self.subTest(at=at):
                self.assertFalse(self.parse(packet)[0])

    def test_legacy_is_explicit_and_cannot_downgrade_v2(self):
        header = struct.pack('<16s16sI32s', b'HC-S1', b'1.0.1', 512, b'h' * 32)
        r, s = utils.decode_dss_signature(self.private.sign(header, ec.ECDSA(hashes.SHA256())))
        packet = header + r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
        accepted, target = self.parse(packet)
        self.assertTrue(accepted)
        self.assertEqual(target.schema, 1)
        self.assertEqual(self.verified_lengths, [68])
        self.policy.confirmed_counter = 1
        self.assertFalse(self.parse(packet)[0])
        self.policy.confirmed_counter = 0
        self.policy.security_epoch = 1
        self.assertFalse(self.parse(packet)[0])
        self.policy.security_epoch = 0
        self.assertFalse(self.parse(packet + b'\0' * 44)[0])
        for length in (0, 68, 112, 131, 133, 175, 177, 196):
            with self.subTest(length=length):
                self.assertFalse(self.parse((self.packet + b'\0' * 196)[:length])[0])


class LocalHealthTest(unittest.TestCase):
    def test_confirmation_uses_local_actual_image_and_persists_only_success(self):
        """Run the real OTA health helper with local flash/NVS/boot stubs."""
        source = ROOT / 'Firmware/firmware_esp/common/hc_core/hc_ota.c'
        header = r'''
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG 2
#define ESP_ERR_INVALID_STATE 3
#define ESP_ERR_NO_MEM 4
#define ESP_ERR_NVS_NOT_FOUND 5
#define ESP_ERR_NVS_INVALID_LENGTH 6
#define NVS_READWRITE 1
#define NVS_READONLY 0
#define OTA_WITH_SEQUENTIAL_WRITES 0
#define ESP_IMAGE_VERIFY_SILENT 0
#define pdTRUE 1
#define pdPASS 1
#define pdMS_TO_TICKS(x) (x)
#define taskYIELD() ((void)0)
typedef void *QueueHandle_t;
typedef int nvs_handle_t;
typedef uint32_t esp_ota_handle_t;
typedef struct {uint32_t address,size;} esp_partition_t;
typedef struct {uint32_t offset,size;} esp_partition_pos_t;
typedef struct {uint32_t image_len;} esp_image_metadata_t;
typedef struct {char version[32];uint32_t secure_version;} esp_app_desc_t;
typedef int esp_ota_img_states_t;
#define ESP_OTA_IMG_PENDING_VERIFY 1
typedef struct {unsigned sum;} psa_hash_operation_t;
typedef int psa_key_attributes_t;
typedef int psa_status_t;
typedef int mbedtls_svc_key_id_t;
#define PSA_HASH_OPERATION_INIT {0}
#define PSA_KEY_ATTRIBUTES_INIT 0
#define PSA_SUCCESS 0
#define PSA_ALG_SHA_256 1
#define PSA_KEY_TYPE_ECC_PUBLIC_KEY(x) 1
#define PSA_ECC_FAMILY_SECP_R1 1
#define PSA_KEY_USAGE_VERIFY_MESSAGE 1
#define PSA_ALG_ECDSA(x) 1
int psa_hash_setup(psa_hash_operation_t*,int);
int psa_hash_update(psa_hash_operation_t*,const uint8_t*,size_t);
int psa_hash_finish(psa_hash_operation_t*,uint8_t*,size_t,size_t*);
int psa_hash_abort(psa_hash_operation_t*);
int psa_hash_compute(int,const uint8_t*,size_t,uint8_t*,size_t,size_t*);
int psa_crypto_init(void);
void psa_set_key_type(psa_key_attributes_t*,int);
void psa_set_key_bits(psa_key_attributes_t*,int);
void psa_set_key_usage_flags(psa_key_attributes_t*,int);
void psa_set_key_algorithm(psa_key_attributes_t*,int);
int psa_import_key(psa_key_attributes_t*,const uint8_t*,size_t,mbedtls_svc_key_id_t*);
int psa_verify_message(mbedtls_svc_key_id_t,int,const uint8_t*,size_t,const uint8_t*,size_t);
void psa_destroy_key(mbedtls_svc_key_id_t);
void psa_reset_key_attributes(psa_key_attributes_t*);
int esp_partition_read(const esp_partition_t*,uint32_t,void*,size_t);
const esp_partition_t *esp_ota_get_running_partition(void);
const esp_partition_t *esp_ota_get_next_update_partition(void*);
int esp_ota_get_partition_description(const esp_partition_t*,esp_app_desc_t*);
int esp_ota_get_state_partition(const esp_partition_t*,esp_ota_img_states_t*);
int esp_ota_mark_app_valid_cancel_rollback(void);
int esp_ota_mark_app_invalid_rollback_and_reboot(void);
int esp_ota_abort(esp_ota_handle_t);
int esp_ota_begin(const esp_partition_t*,int,esp_ota_handle_t*);
int esp_ota_write(esp_ota_handle_t,const void*,size_t);
int esp_ota_end(esp_ota_handle_t);
int esp_ota_set_boot_partition(const esp_partition_t*);
int esp_image_verify(int,const esp_partition_pos_t*,esp_image_metadata_t*);
int nvs_open(const char*,int,nvs_handle_t*);
int nvs_set_blob(nvs_handle_t,const char*,const void*,size_t);
int nvs_get_blob(nvs_handle_t,const char*,void*,size_t*);
int nvs_erase_key(nvs_handle_t,const char*);
int nvs_commit(nvs_handle_t);
void nvs_close(nvs_handle_t);
int64_t esp_timer_get_time(void);
void esp_restart(void);
void vTaskDelay(int);
int xQueueReceive(QueueHandle_t,void*,int);
int xQueueSend(QueueHandle_t,const void*,int);
QueueHandle_t xQueueCreate(int,size_t);
void vQueueDelete(QueueHandle_t);
int xTaskCreate(void(*)(void*),const char*,int,void*,int,void*);
'''
        runner = r'''
#include <assert.h>
#include <string.h>
#include "hc_ota.c"
static esp_partition_t running={.address=0x10000,.size=4096};
static int marked,rolled_back,writes,commit_error,image_error,mark_error;
static uint8_t saved[12];
int psa_hash_setup(psa_hash_operation_t *op,int alg){(void)alg;op->sum=0;return 0;}
int psa_hash_update(psa_hash_operation_t *op,const uint8_t *p,size_t n){while(n--)op->sum+=*p++;return 0;}
int psa_hash_finish(psa_hash_operation_t *op,uint8_t *p,size_t n,size_t *actual){(void)n;memset(p,op->sum,32);*actual=32;return 0;}
int psa_hash_abort(psa_hash_operation_t *op){(void)op;return 0;}
int esp_partition_read(const esp_partition_t *p,uint32_t at,void *out,size_t n){(void)p;(void)at;memset(out,1,n);return 0;}
const esp_partition_t *esp_ota_get_running_partition(void){return &running;}
int esp_ota_get_partition_description(const esp_partition_t *p,esp_app_desc_t *out){(void)p;memset(out,0,sizeof(*out));strcpy(out->version,"2.0.0");return 0;}
int esp_image_verify(int mode,const esp_partition_pos_t *p,esp_image_metadata_t *out){(void)mode;(void)p;out->image_len=64;return image_error;}
int esp_ota_get_state_partition(const esp_partition_t *p,esp_ota_img_states_t *state){(void)p;*state=ESP_OTA_IMG_PENDING_VERIFY;return 0;}
int esp_ota_mark_app_valid_cancel_rollback(void){++marked;return mark_error;}
int esp_ota_mark_app_invalid_rollback_and_reboot(void){++rolled_back;return 0;}
int nvs_open(const char *name,int mode,nvs_handle_t *out){(void)name;(void)mode;*out=1;return 0;}
int nvs_set_blob(nvs_handle_t h,const char *name,const void *p,size_t n){(void)h;assert(!strcmp(name,"ota_confirm"));assert(n==12);memcpy(saved,p,n);++writes;return 0;}
int nvs_commit(nvs_handle_t h){(void)h;return commit_error;}
void nvs_close(nvs_handle_t h){(void)h;}
int main(void){
    uint8_t result[49];
    pending_target=(hc_ota_target){.schema=2,.size=64,.release_counter=9,.security_epoch=3};
    strcpy(pending_target.version,"2.0.0");memset(pending_target.sha256,64,32);
    mark_error=-1;assert(!finalize_pending(result));assert(writes==0 && policy.confirmed_counter==0);
    mark_error=0;
    assert(finalize_pending(result));assert(marked==2 && writes==1 && !rolled_back);
    assert(result[48]==1 && !strcmp((char*)result,"2.0.0") && result[16]==64);
    assert(saved[0]==9 && saved[8]==3 && policy.confirmed_counter==9 && policy.security_epoch==3);
    pending_target.release_counter=10;strcpy(pending_target.version,"3.0.0");
    memset(pending_target.sha256,99,32);
    assert(finalize_pending(result));assert(result[48]==2 && result[16]==64);
    assert(!strcmp((char*)result,"2.0.0") && writes==1 && policy.confirmed_counter==9 && rolled_back==1);
    strcpy(pending_target.version,"2.0.0");memset(pending_target.sha256,64,32);
    commit_error=-1;assert(!finalize_pending(result));assert(policy.confirmed_counter==9);
    commit_error=0;pending_target.schema=1;pending_target.release_counter=0;
    int before=writes;assert(finalize_pending(result));assert(writes==before && policy.confirmed_counter==9);
    image_error=-1;assert(!finalize_pending(result));assert(policy.confirmed_counter==9);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'host.h').write_text(header)
            for name in ('esp_err.h', 'esp_ota_ops.h', 'esp_partition.h', 'esp_system.h',
                         'esp_timer.h', 'nvs.h', 'esp_image_format.h', 'psa/crypto.h',
                         'freertos/FreeRTOS.h', 'freertos/task.h', 'freertos/queue.h'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#include "host.h"\n')
            (root / 'runner.c').write_text(runner)
            proc = subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                   '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
                                   '-I' + str(root), '-I' + str(source.parent),
                                   str(root / 'runner.c'), '-o', str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            subprocess.run([str(root / 'check')], check=True)


if __name__ == '__main__':
    unittest.main()
