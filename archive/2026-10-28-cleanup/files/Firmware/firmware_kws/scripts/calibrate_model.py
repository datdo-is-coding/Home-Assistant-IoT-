"""Fine-tune existing TinyKWS into a separate candidate; never flash or replace active weights."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import wave

import numpy as np
import torch
from train_model import TinyKWS

ROOT = Path(__file__).resolve().parents[3]
KWS = ROOT / 'Firmware/firmware_kws'
COMMON = ROOT / 'Firmware/firmware_esp/common/kws'
LABELS = json.loads((KWS/'data/labels.json').read_text())['classes']
MEAN, STD = -9.295776, 35.392517


def load_model(path):
    model = TinyKWS(len(LABELS))
    model.load_state_dict(torch.load(path, map_location='cpu', weights_only=True))
    return model.eval()


def load_manifest(path):
    path = Path(path)
    rows = json.loads(path.read_text())
    if not isinstance(rows, list) or not rows:
        raise ValueError('nonempty recording manifest required')
    hashes = set()
    for row in rows:
        if row.get('label') not in LABELS or row.get('split') not in ('train', 'val', 'test'):
            raise ValueError('invalid recording label/split')
        row['path'] = (path.parent / row['path']).resolve()
        digest = hashlib.sha256(row['path'].read_bytes()).hexdigest()
        if digest in hashes:
            raise ValueError('recording reused; split complete sessions before augmentation')
        hashes.add(digest)
        row['sha256'] = digest
    return rows


def export_header(model, template, output):
    text = Path(template).read_text()
    for name, layer, bn in [('c1',model.conv1,model.bn1), ('dw2',model.dw2,None),
                            ('pw2',model.pw2,model.bn2), ('dw3',model.dw3,None),
                            ('pw3',model.pw3,model.bn3), ('fc',model.fc,None)]:
        weight = layer.weight.detach().clone()
        bias = layer.bias.detach().clone()
        if bn is not None:
            factor = bn.weight.detach() / torch.sqrt(bn.running_var + bn.eps)
            weight *= factor.reshape((-1,) + (1,)*(weight.ndim-1))
            bias = (bias-bn.running_mean)*factor + bn.bias.detach()
        scales = weight.flatten(1).abs().amax(1).clamp_min(1e-10)/127
        quantized = torch.round(weight/scales.reshape((-1,)+(1,)*(weight.ndim-1))).clamp(-127,127).to(torch.int8)
        for symbol, values, integer in [(f'w_{name}_int8',quantized,True), (f's_{name}',scales,False), (f'b_{name}_int8',bias,False)]:
            flat = values.flatten().tolist()
            content = ', '.join(str(int(v)) if integer else f'{v:.9e}f' for v in flat)
            pattern = rf'(static const (?:int8_t|float) {symbol}\[{len(flat)}\] = \{{).*?(\}};)'
            text, count = re.subn(pattern, lambda m:m[1]+'\n    '+content+'\n'+m[2], text, flags=re.S)
            if count != 1:
                raise ValueError(f'unsupported export template: {symbol}')
    Path(output).write_text(text)


class Features:
    """Use exactly the firmware MFCC rather than a second preprocessing implementation."""
    def __init__(self, directory):
        directory = Path(directory)
        source = directory/'mfcc.cpp'
        source.write_text('#include "kws_mfcc.h"\nextern "C" void extract(const float*x,float*y){static MFCCExtractor e;static bool ready=e.init();if(ready)e.extract(x,y);}\n')
        library = directory/'mfcc.so'
        subprocess.run(['g++','-std=c++17','-O2','-shared','-fPIC',f'-I{COMMON}',str(source),str(COMMON/'kws_mfcc.cpp'),'-o',str(library)],check=True)
        self.lib = ctypes.CDLL(str(library))
        self.ptr = ctypes.POINTER(ctypes.c_float)
        self.lib.extract.argtypes = [self.ptr,self.ptr]

    def extract(self, pcm):
        pcm = np.ascontiguousarray(pcm, dtype=np.float32)
        if pcm.shape != (16000,):
            raise ValueError('MFCC requires exactly one second')
        result = np.empty((99,13),dtype=np.float32)
        self.lib.extract(pcm.ctypes.data_as(self.ptr),result.ctypes.data_as(self.ptr))
        return result


def recording_features(row, extractor, augment=False):
    with wave.open(str(row['path']),'rb') as wav:
        if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate()) != (1,2,16000):
            raise ValueError('recordings must be PCM16 mono 16kHz')
        pcm = np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(np.float32)/32768
    if len(pcm)<1600:
        raise ValueError('recording too short')
    label = LABELS.index(row['label'])
    # Labels apply to one repeated word per session; exclude windows that contain only background.
    frames = [pcm[i:i+400] for i in range(0,len(pcm)-399,400)]
    energy = np.array([np.mean(frame*frame) for frame in frames])
    if row.get('split') in ('val','test'):
        if augment:
            raise ValueError('holdout augmentation is forbidden')
        # Score one strongest window per session, including quiet failures; do not filter the holdout.
        start=max(0,min(int(energy.argmax())*400-8000,len(pcm)-16000))
        window=pcm[start:start+16000]
        window=np.pad(window,(0,16000-len(window)))
        return extractor.extract(window)[None],np.array([label],dtype=np.int64)
    threshold = max(float(np.percentile(energy,20))*6.25, (500/32768)**2)
    active = np.flatnonzero(energy>threshold)
    if row['label'] not in ('noise','unknown') and not len(active):
        raise ValueError(f'no speech detected in {row["path"]}')
    result = []
    for end in range(4000,len(pcm)+4000,4000):
        end = min(end,len(pcm)); start=max(0,end-16000)
        if row['label'] not in ('noise','unknown'):
            if np.sum((active*400>=start)&(active*400<end))<6:
                continue
        window = np.pad(pcm[start:end],(16000-(end-start),0))
        result.append(extractor.extract(window))
    if augment and row['label'] not in ('noise','unknown'):
        # Repeated-word recordings need isolated-word examples, too; never augment holdouts.
        groups = np.split(active, np.flatnonzero(np.diff(active)>2)+1)
        for group in groups:
            if len(group)<4:
                continue
            start=max(0,(int(group[0])-1)*400)
            end=min(len(pcm),(int(group[-1])+2)*400)
            segment=pcm[start:end]
            if len(segment)>12800:
                continue
            for fraction in (0.0,0.5,1.0):
                offset=int((16000-len(segment))*fraction)
                for gain in (0.5,1.0,2.0):
                    window=np.zeros(16000,dtype=np.float32)
                    window[offset:offset+len(segment)]=np.clip(segment*gain,-1.0,1.0)
                    result.append(extractor.extract(window))
    if not result:
        raise ValueError(f'no usable windows in {row["path"]}')
    return np.stack(result), np.full(len(result),label,dtype=np.int64)


def metrics(model, x, y):
    with torch.no_grad():
        probs = model(torch.from_numpy(x[:,None])).softmax(-1).numpy()
    predictions = probs.argmax(1)
    return {'samples':len(y), 'accuracy':float(np.mean(predictions==y)),
            'per_class':{label:{'count':int(np.sum(y==i)), 'accuracy':float(np.mean(predictions[y==i]==i)) if np.any(y==i) else None}for i,label in enumerate(LABELS)}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--epochs',type=int,default=30)
    args=parser.parse_args()
    if not 1 <= args.epochs <= 500:
        parser.error('epochs must be between 1 and 500')
    rows=load_manifest(args.manifest)
    if not any(row['split']=='train' for row in rows):
        parser.error('training sessions required')
    if args.output.exists():
        parser.error('output must be a new directory to preserve earlier candidates')
    args.output.mkdir(parents=True, mode=0o700)
    torch.manual_seed(20261026); np.random.seed(20261026); torch.set_num_threads(4)
    model=load_model(KWS/'models/kws_dscnn_best.pt')
    original={split:((np.load(KWS/f'data/X_{split}.npy')-MEAN)/STD).astype(np.float32)for split in ('train','val','test')}
    labels={split:np.load(KWS/f'data/y_{split}.npy')for split in original}
    mic={split:[] for split in original}; mic_labels={split:[] for split in original}
    with tempfile.TemporaryDirectory() as td:
        extractor=Features(td)
        for row in rows:
            x,y=recording_features(row,extractor,augment=row['split']=='train');mic[row['split']].append(x);mic_labels[row['split']].append(y)
    mic={s:np.concatenate(x)for s,x in mic.items()if x}
    mic_labels={s:np.concatenate(x)for s,x in mic_labels.items()if x}
    baseline=metrics(model,original['test'],labels['test'])
    x=np.concatenate([original['train'],np.tile(mic['train'],(8,1,1))]); y=np.concatenate([labels['train'],np.tile(mic_labels['train'],8)])
    dataset=torch.utils.data.TensorDataset(torch.from_numpy(x[:,None]),torch.from_numpy(y))
    loader=torch.utils.data.DataLoader(dataset,batch_size=64,shuffle=True)
    optimizer=torch.optim.AdamW(model.parameters(),lr=0.0003,weight_decay=1e-4)
    best=-1; history=[]
    for epoch in range(args.epochs):
        model.train()
        for batch,target in loader:
            optimizer.zero_grad();loss=torch.nn.functional.cross_entropy(model(batch),target);loss.backward();optimizer.step()
        model.eval(); score=metrics(model,original['val'],labels['val'])['accuracy']
        mic_score=metrics(model,mic['val'],mic_labels['val'])['accuracy'] if 'val' in mic else None
        selection=score if mic_score is None else (score+mic_score)/2
        history.append({'epoch':epoch+1,'original_val':score,'mic_val':mic_score})
        if selection>best:
            best=selection;torch.save(model.state_dict(),args.output/'candidate.pt')
        print(json.dumps(history[-1]),flush=True)
    model=load_model(args.output/'candidate.pt')
    report={'baseline_original_test':baseline,'candidate_original_test':metrics(model,original['test'],labels['test']),
            'microphone':{s:metrics(model,x,mic_labels[s])for s,x in mic.items()}, 'history':history,
            'recordings':[{**r,'path':str(r['path'])}for r in rows], 'deployment_approved':False}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    export_header(model,COMMON/'kws_model_quantized.h',args.output/'candidate.h')
    print('Candidate saved; no firmware changed. Independent command/noise holdout and C++ parity still required.')

if __name__=='__main__':main()
