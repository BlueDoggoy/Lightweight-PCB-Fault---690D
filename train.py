"""Train a 32x32 grayscale PCB patch baseline; export full-int8 TFLite."""
import os
import faulthandler
faulthandler.dump_traceback_later(90, repeat=True)
os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import json
from pathlib import Path
import numpy as np
from PIL import Image
import tensorflow as tf

tf.keras.utils.set_random_seed(42)
tf.config.threading.set_intra_op_parallelism_threads(4)
root=Path('data/DeepPCB/PCBData'); out=Path('artifacts'); out.mkdir(exist_ok=True)
rng=np.random.default_rng(42)
def load(lines):
    xs=[]; ys=[]
    for line in lines:
        im,ann=line.split(); p=root/im
        p=p.with_name(p.stem+'_test.jpg')
        image=Image.open(p).convert('L')
        boxes=np.loadtxt(root/ann,dtype=int).reshape(-1,5)
        # Fixed 64px field of view, resized to 32px. Positives centered on faults.
        centers=[((a+c)//2,(b+d)//2,1) for a,b,c,d,_ in boxes]
        for _ in range(len(boxes)):
            for attempt in range(200):
                x=int(rng.integers(32,image.width-32)); y=int(rng.integers(32,image.height-32))
                if not any(x+32>a and x-32<c and y+32>b and y-32<d for a,b,c,d,_ in boxes):
                    centers.append((x,y,0)); break
        for x,y,label in centers:
            x=max(32,min(image.width-32,x)); y=max(32,min(image.height-32,y))
            patch=image.crop((x-32,y-32,x+32,y+32)).resize((32,32),Image.Resampling.NEAREST)
            xs.append(np.asarray(patch)); ys.append(label)
    return np.array(xs,dtype=np.float32)[...,None]/255.,np.array(ys)
lines=(root/'trainval.txt').read_text().splitlines(); rng.shuffle(lines)
splits={'train':lines[200:],'validation':lines[:200],'test':(root/'test.txt').read_text().splitlines()}
(out/'split_manifest.json').write_text(json.dumps(splits,indent=2))
x,y=load(splits['train']); vx,vy=load(splits['validation']); tx,ty=load(splits['test'])
model=tf.keras.Sequential([tf.keras.layers.Input((32,32,1)),
 tf.keras.layers.Conv2D(8,3,padding='same',activation='relu'),tf.keras.layers.MaxPooling2D(),
 tf.keras.layers.Conv2D(16,3,padding='same',activation='relu'),tf.keras.layers.MaxPooling2D(),
 tf.keras.layers.Conv2D(16,3,padding='same',activation='relu'),tf.keras.layers.GlobalAveragePooling2D(),
 tf.keras.layers.Dense(2,activation='softmax')])
model.compile(optimizer='adam',loss='sparse_categorical_crossentropy',metrics=['accuracy'])
model.fit(x,y,validation_data=(vx,vy),epochs=15,batch_size=64,verbose=2,
 callbacks=[tf.keras.callbacks.EarlyStopping(patience=3,restore_best_weights=True)])
print('Training complete; exporting TFLite', flush=True)
np.savez(out/'weights.npz',*model.get_weights())
(out/'architecture.json').write_text(model.to_json())
from tensorflow.python.framework.convert_to_constants import convert_variables_to_constants_v2
fn=tf.function(lambda inputs:model(inputs,training=False)).get_concrete_function(tf.TensorSpec([1,32,32,1],tf.float32))
frozen=convert_variables_to_constants_v2(fn)
converter=tf.lite.TFLiteConverter.from_concrete_functions([frozen])
converter.optimizations=[tf.lite.Optimize.DEFAULT]
converter.representative_dataset=lambda:([x[i:i+1]] for i in range(min(300,len(x))))
converter.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type=tf.int8; converter.inference_output_type=tf.int8
blob=converter.convert(); (out/'pcb_int8.tflite').write_bytes(blob)
interpreter=tf.lite.Interpreter(model_content=blob); interpreter.allocate_tensors()
inp=interpreter.get_input_details()[0]; op=interpreter.get_output_details()[0]
def predict(data):
    scores=[]
    for sample in data:
        scale,z=inp['quantization']; q=np.clip(np.rint(sample/scale+z),-128,127).astype(np.int8)
        interpreter.set_tensor(inp['index'],q[None]); interpreter.invoke()
        scale,z=op['quantization']; scores.append((float(interpreter.get_tensor(op['index'])[0,1])-z)*scale)
    return np.array(scores)
def metrics(scores):
    pred=scores>=.5; tp=int(np.sum(pred & (ty==1))); fp=int(np.sum(pred & (ty==0)))
    fn=int(np.sum(~pred & (ty==1))); tn=int(np.sum(~pred & (ty==0)))
    return dict(accuracy=float(np.mean(pred==ty)),recall=tp/max(tp+fn,1),false_positive_rate=fp/max(fp+tn,1),tp=tp,fp=fp,fn=fn,tn=tn)
result={'float':metrics(model.predict(tx,verbose=0)[:,1]),'int8':metrics(predict(tx)),
 'model_bytes':len(blob),'parameters':model.count_params(),'patches':{k:len(v) for k,v in [('train',y),('validation',vy),('test',ty)]},
 'scope':'Centered 64px PCB patches, 32px input; official test split. Not full-board detection or camera accuracy.'}
(out/'metrics.json').write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))
dest=Path('firmware/include'); dest.mkdir(parents=True,exist_ok=True)
(dest/'model_data.h').write_text('#pragma once\n alignas(16) const unsigned char model_data[] = {'+','.join(map(str,blob))+'};\n')
# Known test input for device parity check.
scale,z=inp['quantization']; q=np.clip(np.rint(tx[0]/scale+z),-128,127).astype(np.int8)
(dest/'test_patch.h').write_text('#pragma once\nconst int8_t test_patch[] = {'+','.join(map(str,q.flatten()))+'};\n')
(out/'device_test.json').write_text(json.dumps({'label':int(ty[0]),'defect_score':float(predict(tx[:1])[0])}))
