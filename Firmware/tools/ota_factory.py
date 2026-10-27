"""Offline trusted-USB bootstrap: append new NVS keys, preserving live values.

No flash operations. Only an ACTIVE page's unused entries/bitmap may change;
all headers, used entries, other pages and one erased reserve stay intact.
"""
import base64
import csv
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from zlib import crc32

PAGE=4096
class Peer(ctypes.LittleEndianStructure):
    _fields_=[('node_id',ctypes.c_uint32),('mac',ctypes.c_uint8*6),('lmk',ctypes.c_uint8*16),('nonce',ctypes.c_uint8*32)]
class Enrollment(ctypes.LittleEndianStructure):
    _fields_=[('schema',ctypes.c_uint32),('node_id',ctypes.c_uint32),('parent_id',ctypes.c_uint32),('revision',ctypes.c_uint32),
      ('peer_generation',ctypes.c_uint64),('key',ctypes.c_uint8*32),('pmk',ctypes.c_uint8*16),
      ('channel',ctypes.c_uint8),('subbox',ctypes.c_uint8),('committed',ctypes.c_uint8),('peer_count',ctypes.c_uint8),
      ('factory_id',ctypes.c_char*16),('model',ctypes.c_char*32),('wifi_ssid',ctypes.c_char*33),
      ('wifi_password',ctypes.c_char*65),('mqtt_uri',ctypes.c_char*128),('ota_pubkey',ctypes.c_uint8*65),
      ('claim_nonce',ctypes.c_uint8*32),('claim_id',ctypes.c_char*32),('room_id',ctypes.c_char*32),('peers',Peer*4)]

def parser(idf):
    path=Path(idf)/'components/nvs_flash/nvs_partition_tool/nvs_parser.py'
    spec=importlib.util.spec_from_file_location('factory_nvs_parser',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def parsed(raw,idf):
    if len(raw)%PAGE or len(raw)<3*PAGE:raise ValueError('invalid_partition_size')
    partition=parser(idf).NVS_Partition('factory',bytearray(raw))
    for page in partition.pages:
        if not page.is_empty and (page.header['status'] not in ('Active','Full') or page.header['crc']['original']!=page.header['crc']['computed']):
            raise ValueError('invalid_page')
        for entry in page.entries:
            if entry.state=='Written' and (entry.is_empty or entry.metadata['crc']['original']!=entry.metadata['crc']['computed']):
                raise ValueError('invalid_entry')
    return partition

def values(raw,idf):
    pages=sorted((p for p in parsed(raw,idf).pages if not p.is_empty),key=lambda p:p.header['page_index'])
    namespaces={};result={}
    for page in pages:
        for e in page.entries:
            if e.state=='Written' and e.metadata['namespace']==0:namespaces[e.data['value']]=e.key
    for page in pages:
        for e in page.entries:
            if e.state!='Written' or e.metadata['namespace']==0:continue
            ns=namespaces.get(e.metadata['namespace']);typ=e.metadata['type']
            if ns is None:raise ValueError('unknown_namespace')
            if typ=='blob_index':continue
            if typ in ('blob','blob_data','string'):
                data=b''.join(bytes(c.raw) for c in e.children)[:e.data['size']]
                if typ=='string':data=data.rstrip(b'\0').decode('utf8')
                else:typ='blob'
            else:data=e.data['value']
            key=(ns,e.key)
            if key in result and typ=='blob':result[key]=(typ,result[key][1]+data)
            else:result[key]=(typ,data)
    return result

def generated_partition(idf,additions):
    tool=Path(idf)/'components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py'
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);source=root/'input.csv';image=root/'nvs.bin'
        with source.open('w',newline='') as out:
            writer=csv.writer(out);writer.writerow(['key','type','encoding','value'])
            for namespace,entries in additions.items():
                writer.writerow([namespace,'namespace','',''])
                for key,value in entries.items():
                    if isinstance(value,bytes):encoding='base64';value=base64.b64encode(value).decode()
                    elif isinstance(value,str):encoding='string'
                    elif type(value)is int and 0<=value<=255:encoding='u8'
                    else:raise ValueError('unsupported_value')
                    writer.writerow([key,'data',encoding,value])
        os.chmod(source,0o600)
        subprocess.run([sys.executable,str(tool),'generate',str(source),str(image),'0x5000'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        return image.read_bytes()

def append_values(raw,additions,idf):
    if not additions or any(not isinstance(ns,str) or not 0<len(ns.encode())<=15 for ns in additions):raise ValueError('invalid_namespace')
    if any(not isinstance(key,str) or not 0<len(key.encode())<=15 for entries in additions.values() for key in entries):raise ValueError('invalid_key')
    before=values(raw,idf)
    if any((ns,key) in before for ns,entries in additions.items() for key in entries):raise ValueError('existing_key')
    original=parsed(raw,idf);reserve=sum(p.is_empty for p in original.pages)
    if reserve<1:raise ValueError('no_erased_reserve')
    active=[(i,p) for i,p in enumerate(original.pages) if not p.is_empty and p.header['status']=='Active']
    if len(active)!=1:raise ValueError('expected_one_active_page')
    page_index,page=active[0]
    # Append only at an all-FF tail, never reuse erased slots within a live page.
    bitmap=raw[page_index*PAGE+32:page_index*PAGE+64]
    states=[(bitmap[i//4]>>(2*(i%4)))&3 for i in range(126)]
    start=max((i+1 for i,state in enumerate(states) if state!=3),default=0)
    generated=parsed(generated_partition(idf,additions),idf)
    existing_ns={}
    for p in original.pages:
        for e in p.entries:
            if e.state=='Written' and e.metadata['namespace']==0:existing_ns[e.key]=e.data['value']
    used=set(existing_ns.values());next_index=max(used,default=0)+1
    if next_index+len(additions)>255:raise ValueError('namespace_capacity')
    mapping={};chunks=[]
    for p in generated.pages:
        for e in p.entries:
            if e.state!='Written':continue
            chunk=bytearray(e.raw)
            if e.metadata['namespace']==0:
                if e.key in existing_ns:mapping[e.data['value']]=existing_ns[e.key];continue
                mapping[e.data['value']]=next_index;chunk[24]=next_index;next_index+=1
            else:chunk[0]=mapping[e.metadata['namespace']]
            chunk[4:8]=crc32(chunk[:4]+chunk[8:],0xffffffff).to_bytes(4,'little')
            chunks.append(bytes(chunk))
            chunks.extend(bytes(child.raw) for child in e.children)
    count=len(chunks)
    if start+count>126:raise ValueError('active_page_capacity')
    result=bytearray(raw);base=page_index*PAGE
    for j,chunk in enumerate(chunks,start):
        at=base+64+j*32
        if bytes(result[at:at+32])!=b'\xff'*32:raise ValueError('tail_not_empty')
        result[at:at+32]=chunk
        result[base+32+j//4]&=~(1<<(2*(j%4)))
    after=values(bytes(result),idf)
    for key,value in before.items():
        if after.get(key)!=value:raise ValueError('existing_data_changed')
    for ns,entries in additions.items():
        for key,value in entries.items():
            if after.get((ns,key),(None,None))[1]!=value:raise ValueError('new_data_mismatch')
    if sum(p.is_empty for p in parsed(bytes(result),idf).pages)!=reserve:raise ValueError('reserve_changed')
    return bytes(result)
