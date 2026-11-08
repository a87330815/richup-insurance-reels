# -*- coding: utf-8 -*-
import os,json,re,textwrap
from PIL import Image,ImageDraw,ImageFont,ImageOps
W,H=1080,1350
NAVY=(7,35,78); YELLOW=(255,214,0); BLACK=(10,10,10); WHITE=(255,255,255)
FONT="/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
def f(sz): return ImageFont.truetype(FONT,sz,index=0)
def clean(s): return re.sub(r"<[^>]+>","",s or "")
def wrap(d,s,ft,maxw):
    out=[]; cur=""
    for ch in clean(s):
        if d.textlength(cur+ch,font=ft)>maxw and cur: out.append(cur);cur=ch
        else: cur+=ch
    if cur: out.append(cur)
    return out
def photo(path):
    im=Image.open(path).convert("RGB")
    return ImageOps.fit(im,(W,700),method=Image.Resampling.LANCZOS,centering=(.5,.45))
def load_photos(p):
    try:
        m=json.load(open(os.path.join(p,"photos.json"),encoding="utf-8"))
        return {k:os.path.join(p,v) for k,v in m.get("photos",{}).items()}
    except: return {}
def title_parts(s):
    parts=[]; pos=0
    for m in re.finditer(r"<y>(.*?)</y>",s or ""):
        if m.start()>pos: parts.append((s[pos:m.start()],WHITE))
        parts.append((m.group(1),YELLOW));pos=m.end()
    if pos<len(s or ""): parts.append((s[pos:],WHITE))
    return parts
def draw_center_parts(d,parts,y,ft):
    widths=[d.textlength(t,font=ft) for t,c in parts]; x=(W-sum(widths))/2
    for (t,c),ww in zip(parts,widths): d.text((x,y),t,font=ft,fill=c); x+=ww
def page(sc,slot,photos,i,total):
    im=Image.new("RGB",(W,H),WHITE); d=ImageDraw.Draw(im)
    if slot in photos: im.paste(photo(photos[slot]),(0,0)); d=ImageDraw.Draw(im)
    else: im.paste(Image.new("RGB",(W,700),NAVY),(0,0)); d=ImageDraw.Draw(im)
    d.rounded_rectangle((35,665,1045,825),radius=70,fill=NAVY)
    if slot=="cover":
        draw_center_parts(d,title_parts("".join(sc.get("cover",{}).get("lines",[]))),720,f(61))
        body=" ".join(sc.get("scenes",[{}])[0].get("body","").split())
    else:
        s=sc["scenes"][i-1]; draw_center_parts(d,title_parts(s.get("subtitle","")),705,f(55)); body=s.get("body","")
    ft=f(47); lines=wrap(d,body,ft,900); y=885
    for line in lines[:6]: d.text((72,y),line,font=ft,fill=BLACK); y+=68
    d.rectangle((0,1240,W,H),fill=NAVY)
    d.text((420,1280),"굿리치 리치업지점",font=f(34),fill=WHITE)
    return im
def outro():
    im=Image.new("RGB",(W,H),NAVY); d=ImageDraw.Draw(im)
    d.rectangle((120,78,960,88),fill=YELLOW); d.rectangle((120,1260,960,1270),fill=YELLOW)
    d.text((250,390),"굿리치",font=f(100),fill=WHITE)
    d.text((250,520),"리치업지점",font=f(92),fill=YELLOW)
    d.rounded_rectangle((90,700,990,835),radius=35,fill=YELLOW)
    d.text((210,745),"구독·좋아요 부탁드립니다",font=f(53),fill=NAVY)
    d.text((210,930),"보험과 경제 소식을",font=f(48),fill=WHITE)
    d.text((210,1000),"빠르게 전해드립니다",font=f(48),fill=WHITE)
    return im
def main():
    import argparse
    a=argparse.ArgumentParser();a.add_argument("script");a.add_argument("-o",required=True);a.add_argument("-p",required=True);x=a.parse_args()
    sc=json.load(open(x.script,encoding="utf-8")); os.makedirs(x.o,exist_ok=True); ps=load_photos(x.p)
    page(sc,"cover",ps,0,7).save(os.path.join(x.o,"01_cover.png"))
    for i in range(1,6): page(sc,"scene"+str(i),ps,i,7).save(os.path.join(x.o,f"{i+1:02d}_scene.png"))
    outro().save(os.path.join(x.o,"07_outro.png"))
if __name__=="__main__": main()
