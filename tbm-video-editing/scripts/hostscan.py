import subprocess,sys,numpy as np
def scan(path,fps=4):
    w,h=108,192
    p=subprocess.run(["ffmpeg","-v","error","-i",path,"-vf",f"fps={fps},scale={w}:{h}","-f","rawvideo","-pix_fmt","rgb24","-"],capture_output=True)
    a=np.frombuffer(p.stdout,np.uint8).reshape(-1,h,w,3).astype(float)
    bad=[]
    for i,f in enumerate(a):
        reg=f[int(h*0.72):int(h*0.95),int(w*0.25):int(w*0.85)]
        m=reg.reshape(-1,3).mean(0)
        if m.mean()<25: continue          # black graphic scene
        green = m[1]-m[2]                    # lime shirt: green well above blue (grey jacket ~3)
        if green<9: bad.append(i/fps)
    # merge into ranges
    out=[]
    for t in bad:
        if out and t-out[-1][1]<=0.5: out[-1][1]=t
        else: out.append([t,t])
    return [(round(a,2),round(b+1/fps,2)) for a,b in out]
for p in sys.argv[1:]: print(p.split('/')[-1], scan(p))
