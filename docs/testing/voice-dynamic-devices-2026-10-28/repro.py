import asyncio
import hashlib
import json
from pathlib import Path
import sys

repo=Path('/home/tuan/Home-Assistant-IoT-')
sys.path[:0]=[str(repo/'Gateway'),str(repo/'Gateway/tests'),str(repo/'Gateway/gateway')]
from test_pi_speaker_voice import PiSpeakerVoiceTests
from gateway.core_v1.firebase_commissioning import CoreCommissioning
from gateway.core_v1.registry import CoreError
from asr_engine import ASREngine

case=PiSpeakerVoiceTests();case.setUp()
out={}
try:
    f=case.fixture;voice=case.session.voice;user=voice.user
    cloud=CoreCommissioning(f.r,{'home_id':f.home},['audit'])
    def update(**values):
        return cloud.request('audit','POST','/api/device/update',{'device_id':'AB001122334402',**values})
    def resolve(text,source=None):
        try:
            device,on=voice.resolve(user,f.sub,source or f.action,text)
            return {'resolved':True,'on':on,'device':device}
        except CoreError as e:return {'resolved':False,'error':e.code}
    update(ch1_name='Đèn bể cá',ch1_type='light')
    initial=resolve('bật đèn bể cá');assert initial['resolved']
    out['before_rename']=initial
    try:
        update(ch1_name='Máy pha cà phê',ch1_type='den')
        raise AssertionError('Unexpected acceptance of app den kind')
    except CoreError as e:out['actual_app_type_den']={'error':e.code}
    assert resolve('bật đèn bể cá')['resolved']
    update(ch1_name='Máy pha cà phê')
    out['name_only_old_light_category_still_controls_coffee']=resolve('bật đèn')
    update(ch1_name='Máy pha cà phê',ch1_type='custom');f.report(seq=2)
    out['canonical_new_name_on']=resolve('bật máy pha cà phê')
    out['canonical_new_name_off']=resolve('tắt máy pha cà phê')
    assert out['canonical_new_name_on']['device']==initial['device']
    assert out['canonical_new_name_off']['on'] is False
    out['old_exact_name']=resolve('bật đèn bể cá')
    out['old_light_category_after_kind_changed']=resolve('bật đèn')
    assert not out['old_exact_name']['resolved'] and not out['old_light_category_after_kind_changed']['resolved']
    out['short_alias']=resolve('bật máy cà phê')
    out['room_suffix']=resolve('bật máy pha cà phê phòng khách')
    out['polite_suffix']=resolve('bật máy pha cà phê giúp mình')
    try:
        update(ch1_aliases=['máy cà phê'])
        raise AssertionError('Unexpected acceptance of aliases')
    except CoreError as e:out['core_alias_update']={'error':e.code}
    new=f.enroll('HC-001122334403','ACTION_BOX',f.sub);f.online(new)
    out['new_box_unassigned']=resolve('bật máy pha cà phê phụ')
    d=f.r.create_device(f.owner,f.home,'Máy pha cà phê phụ','other','HC-001122334403:CH2')
    f.report(node=new)
    selected=resolve('bật máy pha cà phê phụ');assert selected['device']==d['device_id']
    command=voice.submit(user,f.sub,f.action,'bật máy pha cà phê phụ','c'*32)
    assert command['node_id']==new and command['channel_id']=='HC-001122334403:CH2'
    out['new_box_bound_from_original_mic']={'selected':True,'channel':2,'command_status':command['status']}
    assert resolve('tắt máy pha cà phê phụ',new)['resolved']
    out['new_box_own_mic']={'resolved':True}
    f.r.create_device(f.owner,f.home,'Máy pha cà phê','other','HC-001122334403:CH3')
    out['duplicate_name']=resolve('bật máy pha cà phê');assert out['duplicate_name']['error']=='voice_ambiguous'
    engine=ASREngine()
    scores={text:round(engine._estimate_confidence(text,text.upper(),5,.025),3)
            for text in ('bật đèn','tắt đèn','bật máy pha cà phê','tắt máy pha cà phê','bật đèn bể cá')}
    out['confidence_heuristic_same_duration_and_rms']=scores
    assert scores['bật đèn']>=.7 and scores['bật máy pha cà phê']<.7
    case.server.gateway.asr.transcribe_with_confidence.return_value=('bật máy pha cà phê',scores['bật máy pha cà phê'])
    asyncio.run(voice.process(case.session,user,f.sub,f.action,'d'*32,b'\0\0'*16000,__import__('time').monotonic()))
    last=json.loads(case.socket.send.await_args_list[-1].args[0])
    out['full_voice_pipeline_with_correct_coffee_text']={'verify':last['verify']}
    assert last['verify']=='low_confidence'
    out['live_source_hashes']={name:hashlib.sha256((repo/'Gateway/gateway'/name).read_bytes()).hexdigest()
                               for name in ('asr_engine.py','core_v1/voice.py','core_v1/speaker_voice.py','core_v1/firebase_commissioning.py')}
finally:
    case.tearDown()
print(json.dumps(out,ensure_ascii=False,indent=2))
