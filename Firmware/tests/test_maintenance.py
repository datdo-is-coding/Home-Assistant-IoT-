from pathlib import Path
import subprocess,tempfile,unittest

class MaintenanceGuardTests(unittest.TestCase):
    def test_exact_kind_revision_and_short_monotonic_deadline(self):
        root=Path(__file__).resolve().parents[1]/'firmware_esp/common/hc_core'
        source='''#include <assert.h>
#include "hc_maintenance.h"
static void deadline(hc_frame* f,uint64_t value){for(unsigned i=0;i<8;++i)f->payload[i+1]=(uint8_t)(value>>(8*i));}
int main(void){
 hc_frame f={0};f.type=HC_MAINTENANCE;f.config_rev=7;f.payload_len=9;f.payload[0]=2;deadline(&f,2000);
 assert(hc_maintenance_valid(&f,7,1000));
 assert(!hc_maintenance_valid(&f,8,1000));
 assert(!hc_maintenance_valid(&f,7,2001));
 deadline(&f,6001);assert(!hc_maintenance_valid(&f,7,1000));
 deadline(&f,2000);f.payload_len=8;assert(!hc_maintenance_valid(&f,7,1000));
 f.payload_len=9;f.payload[0]=0;assert(!hc_maintenance_valid(&f,7,1000));
 f.payload[0]=4;assert(!hc_maintenance_valid(&f,7,1000));
 f.payload[0]=1;f.type=HC_UNPAIR;assert(!hc_maintenance_valid(&f,7,1000));
}'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'check.c').write_text(source)
            subprocess.run(['cc','-std=c11','-Wall','-Werror','-I',str(root),str(p/'check.c'),'-o',str(p/'check')],check=True)
            subprocess.run([str(p/'check')],check=True)
