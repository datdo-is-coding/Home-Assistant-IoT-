"""Home Competition standalone management service and offline administration."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import ssl
from aiohttp import web
from cryptography.hazmat.primitives import serialization
from .registry import Registry
from .api import create_app
from .bridge import Bridge,run_mqtt
from .ota import OtaManager
from .ha import HomeAssistantAdapter
from .voice import CoreVoice

def private_file(path,data):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'wb') as f:f.write(data)

def main():
    parser=argparse.ArgumentParser(description='Home Competition Core V1')
    parser.add_argument('--data',type=Path,default=Path('hc-data'))
    sub=parser.add_subparsers(dest='action',required=True)
    init=sub.add_parser('init');init.add_argument('--name',default='Owner');init.add_argument('--home',default='Home Competition')
    serve=sub.add_parser('serve');serve.add_argument('--host',default='127.0.0.1');serve.add_argument('--port',type=int,default=8081)
    factory=sub.add_parser('import-factory');factory.add_argument('file',type=Path)
    backup=sub.add_parser('backup');backup.add_argument('destination',type=Path)
    sub.add_parser('integrity')
    args=parser.parse_args()
    args.data.mkdir(parents=True,exist_ok=True,mode=0o700)
    keyfile=args.data/'master.key';dbfile=args.data/'core.db'
    if args.action=='init':
        if dbfile.exists() or keyfile.exists():parser.error('Data already exists; init never overwrites ownership')
        private_file(keyfile,secrets.token_bytes(32))
    if not keyfile.is_file():parser.error('Run init before starting service')
    if keyfile.stat().st_mode&0o077:parser.error('master.key must be private (chmod 600)')
    r=Registry(dbfile,keyfile.read_bytes(),recover=args.action=='serve')
    dbfile.chmod(0o600)
    try:
        if args.action=='init':
            user,token=r.create_user(args.name);home=r.create_home(user,args.home)

            private_file(args.data/'owner-token.txt',(token+'\n').encode())
            print(json.dumps({'user_id':user,'home_id':home,'token_file':str(args.data/'owner-token.txt')}))
        elif args.action=='import-factory':
            data=json.loads(args.file.read_text())
            r.add_factory_device(data['factory_id'],data['product_type'],data['model'],bytes.fromhex(data['factory_secret']),data['setup_code'])
            print('Factory identity imported; ownership is still unregistered.')
        elif args.action=='backup':
            args.destination.mkdir(mode=0o700)
            r.backup(args.destination/'core.db')
            private_file(args.destination/'master.key',keyfile.read_bytes())
            print('Database and recovery key saved; protect this directory as a credential backup.')
        elif args.action=='integrity':print(r.integrity())
        elif args.action=='serve':
            tls=None
            if os.environ.get('HC_TLS_CERT'):
                tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                tls.load_cert_chain(os.environ['HC_TLS_CERT'],os.environ['HC_TLS_KEY'])
            if args.host not in ('127.0.0.1','::1','localhost') and tls is None:
                parser.error('Non-loopback listener requires HC_TLS_CERT and HC_TLS_KEY')
            ota=None
            if os.environ.get('HC_OTA_PUBLIC_KEY'):
                public=serialization.load_pem_public_key(Path(os.environ['HC_OTA_PUBLIC_KEY']).read_bytes())
                ota=OtaManager(r,args.data/'firmware',public)
            voice=None
            voice_config=os.environ.get('HC_VOICE_NODES')
            voice_raw=None
            if voice_config:
                try:
                    if Path(voice_config).is_file():
                        voice_raw=Path(voice_config).read_text()
                    else:
                        voice_raw=voice_config
                except (OSError,ValueError):
                    voice_raw=voice_config
            elif (args.data / 'voice.json').is_file():
                voice_raw=(args.data / 'voice.json').read_text()
            if voice_raw:
                try:
                    loaded=json.loads(voice_raw)
                    if isinstance(loaded,dict) and loaded:
                        node_users={int(k):str(v) for k,v in loaded.items()}
                        asr=None
                        asr_dir=os.environ.get('HC_ASR_MODEL_DIR')
                        if asr_dir and Path(asr_dir).is_dir():
                            try:
                                from gateway.asr_engine import ASREngine
                                asr=ASREngine(os.environ['HC_ASR_MODEL_DIR'])
                            except Exception:
                                asr=None
                        voice=CoreVoice(r,node_users,asr=asr,tts=None)
                except Exception:
                    pass
            app=create_app(r,ota,os.environ.get('HC_PUBLIC_ORIGIN'),voice=voice)
            if os.environ.get('HC_MQTT_HOST'):
                bridge=Bridge(r);bridge.ota=ota
                if os.environ.get('HC_HA_USER_ID'):
                    bridge.ha=HomeAssistantAdapter(r,os.environ['HC_HA_USER_ID'],os.environ['HC_HA_HOME_ID'])
                async def mqtt_lifecycle(_app):
                    task=asyncio.create_task(run_mqtt(bridge,os.environ['HC_MQTT_HOST'],int(os.environ.get('HC_MQTT_PORT','8883')),
                                                    os.environ['HC_MQTT_USER'],os.environ['HC_MQTT_PASSWORD'],os.environ['HC_MQTT_CA']))
                    yield
                    task.cancel();await asyncio.gather(task,return_exceptions=True)
                app.cleanup_ctx.append(mqtt_lifecycle)
            web.run_app(app,host=args.host,port=args.port,ssl_context=tls,access_log=None)
    finally:r.close()

if __name__=='__main__':main()
