import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('ota_factory',ROOT/'Firmware/tools/ota_factory.py')
mod=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(mod)
IDF=Path('/home/tuan/.espressif/v6.0.2/esp-idf')

@unittest.skipUnless(IDF.exists(),'ESP-IDF NVS tool required')
class FactoryAppend(unittest.TestCase):
 def test_preserves_existing_values_and_erased_reserve(self):
  raw=mod.generated_partition(IDF,{'existing':{'name':'keep','calibration':b'\x01\x02'}})
  result=mod.append_values(raw,{'hc_factory':{'secret':b'k'*32,'kind':2},'hc_core':{'enrollment':b'e'*752,'ota_compat':b'c'*32}},IDF)
  before=mod.values(raw,IDF);after=mod.values(result,IDF)
  for key,value in before.items():self.assertEqual(after[key],value)
  self.assertEqual(after[('hc_factory','secret')][1],b'k'*32)
  self.assertEqual(result[4096:],raw[4096:])
  self.assertEqual(result[:32],raw[:32])
 def test_refuses_existing_key_invalid_pages_and_insufficient_space(self):
  raw=mod.generated_partition(IDF,{'hc_factory':{'secret':b'old'}})
  with self.assertRaises(ValueError):mod.append_values(raw,{'hc_factory':{'secret':b'new'}},IDF)
  broken=bytearray(raw);broken[4]^=1
  with self.assertRaises(ValueError):mod.append_values(bytes(broken),{'hc_core':{'ota_compat':b'c'*32}},IDF)
  raw=mod.generated_partition(IDF,{'existing':{'large':b'x'*3400}})
  with self.assertRaises(ValueError):mod.append_values(raw,{'hc_core':{'enrollment':b'e'*752}},IDF)
 def test_enrollment_matches_target_abi(self):
  c=mod.Enrollment()
  self.assertEqual(mod.ctypes.sizeof(c),752)
  self.assertEqual(mod.Enrollment.ota_pubkey.offset,350)
  self.assertEqual(mod.Enrollment.peers.offset,512)

class FactoryFirmware(unittest.TestCase):
 def test_real_factory_bootstrap_checks_mac_before_writing_and_rejects_existing_identity(self):
  import ctypes,subprocess
  c=mod.Enrollment();c.schema=1;c.node_id=1;c.revision=1;c.subbox=1;c.channel=1
  c.factory_id=b'HC-010203040506';c.ota_pubkey[0]=4
  packet=b'HCF2'+bytes(range(1,7))+b'\x01\0'+bytes(c)+b'c'*32+b's'*32+b'private-setup\0'.ljust(65,b'\0')+b'private-ap-pass\0'.ljust(64,b'\0')
  self.assertEqual(len(packet),957)
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'bundle.bin').write_bytes(packet)
   (root/'esp_err.h').write_text('typedef int esp_err_t;\n#define ESP_OK 0\n#define ESP_ERR_INVALID_ARG 1\n#define ESP_ERR_INVALID_MAC 2\n#define ESP_ERR_INVALID_STATE 3\n#define ESP_ERR_NVS_NOT_FOUND 4\n')
   (root/'esp_mac.h').write_text('#include <stdint.h>\nint esp_efuse_mac_get_default(uint8_t*);\n')
   (root/'nvs.h').write_text('#include <stddef.h>\n#include <stdint.h>\ntypedef int nvs_handle_t;\n#define NVS_READWRITE 1\nint nvs_open(const char*,int,nvs_handle_t*);\nint nvs_get_blob(int,const char*,void*,size_t*);\nint nvs_set_blob(int,const char*,const void*,size_t);\nint nvs_get_str(int,const char*,char*,size_t*);\nint nvs_set_str(int,const char*,const char*);\nint nvs_get_u8(int,const char*,uint8_t*);\nint nvs_set_u8(int,const char*,uint8_t);\nint nvs_commit(int);\nvoid nvs_close(int);\n')
   (root/'main.c').write_text(r'''
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include "hc_factory.h"
#include "hc_provisioning.h"
asm(".section .rodata\n.global _binary_hc_factory_bundle_start\n_binary_hc_factory_bundle_start:\n.incbin \"BUNDLE\"\n.global _binary_hc_factory_bundle_end\n_binary_hc_factory_bundle_end:\n.text");
extern const unsigned char _binary_hc_factory_bundle_start[];
static int wrong_mac,writes,commits,existing_kind,existing_enrollment;
int hc_provisioning_load(hc_provisioned_config *c){if(!existing_enrollment)return 4;memcpy(c,_binary_hc_factory_bundle_start+12,sizeof(*c));c->revision=9;if(existing_enrollment==2)c->node_id++;return 0;}
int esp_efuse_mac_get_default(uint8_t *m){for(int i=0;i<6;i++)m[i]=i+1;m[0]+=wrong_mac;return 0;}
int nvs_open(const char*n,int mode,int*h){(void)n;(void)mode;*h=1;return 0;}
int nvs_get_blob(int h,const char*k,void*v,size_t*n){(void)h;(void)k;(void)v;(void)n;return 4;}
int nvs_set_blob(int h,const char*k,const void*v,size_t n){(void)h;(void)k;(void)v;(void)n;writes++;return 0;}
int nvs_get_str(int h,const char*k,char*v,size_t*n){(void)h;(void)k;(void)v;(void)n;return 4;}
int nvs_set_str(int h,const char*k,const char*v){(void)h;(void)k;(void)v;writes++;return 0;}
int nvs_get_u8(int h,const char*k,uint8_t*v){(void)h;(void)k;*v=2;return existing_kind?0:4;}
int nvs_set_u8(int h,const char*k,uint8_t v){(void)h;(void)k;(void)v;writes++;return 0;}
int nvs_commit(int h){(void)h;commits++;return 0;}void nvs_close(int h){(void)h;}
int main(void){wrong_mac=1;assert(hc_factory_apply()==2);assert(writes==0);wrong_mac=0;existing_kind=1;assert(hc_factory_apply()==3);assert(writes==0);existing_kind=0;assert(hc_factory_apply()==0);assert(writes==6 && commits==2);writes=commits=0;existing_enrollment=1;assert(hc_factory_apply()==0);assert(writes==0 && commits==0);existing_enrollment=2;assert(hc_factory_apply()==3);assert(writes==0 && commits==0);}
'''.replace('BUNDLE',str(root/'bundle.bin')))
   subprocess.run(['gcc','-std=gnu11','-Wall','-Wextra','-Werror','-DHC_FACTORY_BOOTSTRAP','-I'+str(root),'-I'+str(ROOT/'Firmware/firmware_esp/common/hc_core'),str(root/'main.c'),str(ROOT/'Firmware/firmware_esp/common/hc_core/hc_factory.c'),'-o',str(root/'test')],check=True,capture_output=True)
   subprocess.run([str(root/'test')],check=True,capture_output=True)
