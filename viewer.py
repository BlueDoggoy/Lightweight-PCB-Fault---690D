"""USB camera preview for the XIAO PCB firmware. No network connection required."""
import argparse
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path
import serial
from PIL import Image, ImageDraw, ImageTk

def read_exact(port, length):
    data=bytearray()
    while len(data)<length:
        chunk=port.read(length-len(data))
        if not chunk:
            raise TimeoutError('Incomplete frame. Reconnect the viewer.')
        data.extend(chunk)
    return bytes(data)

def receive(port):
    port.write(b'V')
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        line=port.readline()
        if not line.startswith(b'FRAME '):
            continue
        _,w,h,n,score,latency=line.decode('ascii').split()
        w,h,n=int(w),int(h),int(n)
        if not(0<w<=640 and 0<h<=480 and n==w*h):
            raise ValueError('Invalid frame header')
        pixels=read_exact(port,n)
        return Image.frombytes('L',(w,h),pixels),float(score),int(latency)
    raise TimeoutError('No camera frame received. Check firmware and camera.')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',default='COM6')
    parser.add_argument('--snapshot',action='store_true')
    args=parser.parse_args()
    if args.snapshot:
        with serial.Serial(args.port,115200,timeout=3,write_timeout=3) as port:
            im,score,us=receive(port)
            Path('artifacts').mkdir(exist_ok=True)
            im.save('artifacts/camera_preview.png')
            print(f'Frame={im.size} score={score} inference_ms={us/1000:.1f}')
        return
    root=tk.Tk();root.title('PCB Camera · XIAO ESP32-S3');root.geometry('980x660')
    root.configure(bg='#15202b')
    ttk.Label(root,text='PCB camera preview',font=('Segoe UI',20,'bold')).pack(anchor='w',padx=20,pady=12)
    ttk.Label(root,text='USB preview • outlined area is the only region inspected • no fault bounding boxes').pack(anchor='w',padx=20)
    panel=ttk.Frame(root);panel.pack(padx=20,pady=16)
    full=ttk.Label(panel);full.grid(row=0,column=0,padx=8)
    crop=ttk.Label(panel);crop.grid(row=0,column=1,padx=8,sticky='n')
    ttk.Label(panel,text='Full frame · 320 × 240').grid(row=1,column=0)
    ttk.Label(panel,text='Model input · 32 × 32 (enlarged)').grid(row=1,column=1)
    status=tk.StringVar(value=f'Connecting to {args.port}…')
    ttk.Label(root,textvariable=status,font=('Segoe UI',12)).pack(anchor='w',padx=24)
    ttk.Label(root,text='Aim a sharply focused PCB region inside the square. Score ≥ 0.5 flags a possible defect.\nThis is an experimental classifier; lighting and focus affect results.').pack(anchor='w',padx=24,pady=12)
    messages=queue.Queue(maxsize=2);stop=threading.Event()
    def worker():
        try:
            with serial.Serial(args.port,115200,timeout=3,write_timeout=3) as port:
                while not stop.is_set():
                    result=receive(port)
                    if messages.full():messages.get_nowait()
                    messages.put(result)
        except Exception as exc:
            if messages.full():messages.get_nowait()
            messages.put(str(exc))
    threading.Thread(target=worker,daemon=True).start()
    last=[0]
    def update():
        try:
            item=messages.get_nowait()
            if isinstance(item,str):status.set('Disconnected: '+item)
            else:
                im,score,us=item;w,h=im.size;left,top=(w-64)//2,(h-64)//2
                small=im.crop((left,top,left+64,top+64)).resize((32,32),Image.Resampling.NEAREST)
                display=im.convert('RGB').resize((640,480),Image.Resampling.NEAREST)
                color='#ff746b' if score>=.5 else '#48dec0'
                ImageDraw.Draw(display).rectangle((left*2,top*2,(left+64)*2-1,(top+64)*2-1),outline=color,width=3)
                full.image=ImageTk.PhotoImage(display);full.configure(image=full.image)
                crop.image=ImageTk.PhotoImage(small.resize((192,192),Image.Resampling.NEAREST));crop.configure(image=crop.image)
                now=time.monotonic();interval=now-last[0] if last[0] else 0;last[0]=now
                label='Possible defect' if score>=.5 else 'Below defect threshold'
                status.set(f'{label}  |  Score {score:.3f}  |  Inference {us/1000:.1f} ms  |  Preview interval {interval:.1f} s')
        except queue.Empty:pass
        root.after(100,update)
    def close():stop.set();root.destroy()
    root.protocol('WM_DELETE_WINDOW',close);update();root.mainloop()

if __name__=='__main__':main()
