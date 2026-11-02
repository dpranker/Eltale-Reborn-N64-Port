python
import os
gdb.execute("source tests/gdb/dl_common.py")
import struct, zlib
def png(path, w, h, rgb):
    def chunk(t,d): return struct.pack(">I",len(d))+t+d+struct.pack(">I",zlib.crc32(t+d))
    raw=b"".join(b"\0"+bytes(rgb[y*w*3:(y+1)*w*3]) for y in range(h))
    open(path,"wb").write(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",w,h,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(raw))+chunk(b"IEND",b""))
orig=dl_check.Checker.__init__
def init(self,*a,**k):
    orig(self,*a,**k); self.trace=[]; traces.append(self)
dl_check.Checker.__init__=init
traces=[]
def view(name):
    row=capture(name)
    tr=traces[-1].trace
    W,H=320,240
    img=bytearray(W*H*3); count=[0]*(W*H)
    for clip,vp,area,cyc in tr:
        if any(p[3]<=1e-3 for p in clip): continue
        s=[(vp[2]+p[0]/p[3]*vp[0], vp[3]-p[1]/p[3]*vp[1]) for p in clip]
        x0=max(int(min(q[0] for q in s)),0); x1=min(int(max(q[0] for q in s))+1,W-1)
        y0=max(int(min(q[1] for q in s)),0); y1=min(int(max(q[1] for q in s))+1,H-1)
        for y in range(y0,y1+1):
            for x in range(x0,x1+1):
                d=[(s[(i+1)%3][0]-s[i][0])*(y-s[i][1])-(s[(i+1)%3][1]-s[i][1])*(x-s[i][0]) for i in range(3)]
                if all(v>=0 for v in d) or all(v<=0 for v in d): count[y*W+x]+=1
    for i,c in enumerate(count):
        v=min(c*50,255); img[i*3]=v; img[i*3+1]=v; img[i*3+2]=v
    png(f"build/shots/dlview_{name}.png",W,H,img)
    big=sorted(((a,c) for _,_,a,c in tr),reverse=True)[:12]
    print("VIEW",name,"drawn",len(tr),"sum",round(sum(a for _,_,a,_ in tr)),"biggest",[(round(a),c) for a,c in big],"mean coverage",round(sum(count)/len(count),2),"uncovered%",round(sum(1 for c in count if c==0)/len(count)*100),"viewport",tr[0][1],flush=True)
new_game()
clear_scene()
warp(2)
wait_polls(120)
view("plain")
melrode_street()
view("town")
finish()
end
