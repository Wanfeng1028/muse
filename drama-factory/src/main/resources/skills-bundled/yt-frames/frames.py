"""Sample video frames for brightness, approximate cuts/motion and face detections.
Optional dependencies: opencv-python and numpy. No media is uploaded.
"""
import argparse,json,math,sys
from pathlib import Path
VENDOR=Path(__file__).resolve().parent/"vendor"
if VENDOR.exists(): sys.path.insert(0,str(VENDOR))

def inspect(path,sample_fps=4,cut_threshold=0.35):
    if sample_fps<=0 or not 0<cut_threshold<1: raise ValueError('Invalid sampling settings')
    try: import cv2; import numpy as np
    except ImportError as e: raise RuntimeError('Frame inspection requires opencv-python and numpy') from e
    if not hasattr(cv2,'CascadeClassifier'): raise RuntimeError('Use OpenCV 4.x; install the pinned requirements.txt in this folder')
    cap=cv2.VideoCapture(str(path))
    if not cap.isOpened(): raise ValueError('Cannot decode video')
    fps=cap.get(cv2.CAP_PROP_FPS)
    if not math.isfinite(fps) or fps<=0: raise ValueError('Invalid video frame rate')
    stride=max(1,round(fps/sample_fps));detector=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    index=0;previous=None;hist_prev=None;shots=[];shot={'start':0.0,'motion':[],'face_samples':0,'samples':0};first=None
    while True:
        ok,frame=cap.read()
        if not ok: break
        if index%stride==0:
            gray=cv2.cvtColor(cv2.resize(frame,(320,180)),cv2.COLOR_BGR2GRAY);t=index/fps
            if first is None: first=float(gray.mean()/255)
            hist=cv2.calcHist([gray],[0],None,[32],[0,256]);cv2.normalize(hist,hist,alpha=1,norm_type=cv2.NORM_L1)
            cut=hist_prev is not None and cv2.compareHist(hist_prev,hist,cv2.HISTCMP_BHATTACHARYYA)>cut_threshold
            if cut:
                shot['end']=t;shots.append(shot);shot={'start':t,'motion':[],'face_samples':0,'samples':0}
            elif previous is not None: shot['motion'].append(float(np.abs(gray.astype(float)-previous.astype(float)).mean()/255))
            shot['samples']+=1;shot['face_samples']+=int(len(detector.detectMultiScale(gray,scaleFactor=1.1,minNeighbors=5))>0)
            previous=gray;hist_prev=hist
        index+=1
    cap.release()
    if first is None: raise ValueError('No decoded frames')
    shot['end']=index/fps;shots.append(shot)
    for s in shots:
        m=s.pop('motion');s['mean_frame_change']=sum(m)/len(m) if m else None
        s['face_detected']=s['face_samples']>0
    return {'first_frame_brightness_0_1':first,'sample_interval_seconds':stride/fps,'cut_threshold':cut_threshold,'shots':shots,
            'limitations':'Cuts are approximate sample boundaries. Frame change includes camera movement and lighting. Frontal-face detector misses small, stylized, angled or obscured faces; no detection does not prove absence. Brightness is not a quality score.'}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('video');p.add_argument('--sample-fps',type=float,default=4);p.add_argument('--cut-threshold',type=float,default=.35);a=p.parse_args()
    try: print(json.dumps(inspect(a.video,a.sample_fps,a.cut_threshold),indent=2))
    except (ValueError,RuntimeError) as e:p.error(str(e))
