"""Offline signer for the existing ESP32-S3 application-only OTA format."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec,utils
from .manifest import key_id,target_header,verify_target


def sign(image,private,compatibility_id,role,counter,security_epoch=0):
    if not isinstance(private,ec.EllipticCurvePrivateKey) or not isinstance(private.curve,ec.SECP256R1):
        raise ValueError('P-256 private signing key required')
    if (not isinstance(image,bytes) or len(image)<288 or image[0]!=0xe9
            or not 1<=image[1]<=16 or struct.unpack_from('<H',image,12)[0]!=9
            or struct.unpack_from('<I',image,32)[0]!=0xabcd5432):
        raise ValueError('invalid ESP32-S3 application image')
    version=image[48:80].split(b'\0',1)[0].decode('ascii')
    if b'HCF2' in image:
        raise ValueError('factory bootstrap images must not be released')
    m=dict(schema=2,role=role,artifact_type=1,flags=0,compatibility_id=compatibility_id,
           version=version,size=len(image),sha256=hashlib.sha256(image).hexdigest(),
           min_agent=2,min_bootloader=1,protocol_min=1,protocol_max=1,
           release_counter=counter,security_epoch=security_epoch,key_id=key_id(private.public_key()))
    header=target_header(m)
    r,s=utils.decode_dss_signature(private.sign(header,ec.ECDSA(hashes.SHA256())))
    packet=header+r.to_bytes(32,'big')+s.to_bytes(32,'big')
    verify_target(packet,private.public_key(),compatibility_id=compatibility_id,role=role,image=image)
    return packet,m


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('key','image','compatibility-id','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--role',type=int,choices=(1,2),required=True)
    p.add_argument('--release-counter',type=int,required=True)
    p.add_argument('--security-epoch',type=int,default=0)
    a=p.parse_args();key=Path(a.key)
    if key.is_symlink() or not key.is_file() or key.stat().st_mode&0o077:
        raise ValueError('private signing key must be a private regular file')
    private=serialization.load_pem_private_key(key.read_bytes(),password=None)
    packet,m=sign(Path(a.image).read_bytes(),private,a.compatibility_id,a.role,a.release_counter,a.security_epoch)
    with Path(a.output).open('xb') as out:out.write(packet)
    print(json.dumps(m,sort_keys=True))


if __name__=='__main__':main()
