"""Small dependency-free visualization helpers (NumPy + Pillow only)."""
from __future__ import annotations
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from .image_context import array_to_image

def normalize(a: np.ndarray, low: float = 1, high: float = 99) -> np.ndarray:
    x = np.nan_to_num(np.asarray(a, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    if x.size == 0: return np.zeros((1, 1), dtype=np.uint8)
    lo, hi = np.percentile(x, [low, high])
    if hi - lo < 1e-7: return np.zeros(x.shape, dtype=np.uint8)
    return np.clip((x - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)

def heatmap(a: np.ndarray, palette: str = "spectrum") -> np.ndarray:
    v = normalize(a).astype(np.float32) / 255.0
    if palette == "red":
        return np.stack([v * 255, (v ** 2) * 55, (v ** 3) * 35], axis=-1).astype(np.uint8)
    if palette == "ice":
        return np.stack([v * 45, v * 180, 90 + v * 165], axis=-1).clip(0,255).astype(np.uint8)
    if palette == "mono":
        return np.stack([v * 255] * 3, axis=-1).astype(np.uint8)
    # Smooth blue -> cyan -> yellow -> red ramp, useful for ranking maps.
    stops = np.array([[16, 25, 130], [0, 190, 255], [255, 226, 50], [230, 30, 40]], dtype=np.float32)
    u = v * (len(stops) - 1)
    ix = np.minimum(u.astype(np.int32), len(stops) - 2)
    frac = (u - ix)[..., None]
    return (stops[ix] * (1 - frac) + stops[ix + 1] * frac).clip(0,255).astype(np.uint8)

def overlay(base_rgb: np.ndarray, score: np.ndarray, alpha: float = .48) -> np.ndarray:
    hm = heatmap(score)
    if hm.shape[:2] != base_rgb.shape[:2]:
        hm = np.asarray(Image.fromarray(hm).resize((base_rgb.shape[1], base_rgb.shape[0]), Image.Resampling.BILINEAR))
    return np.clip(base_rgb.astype(np.float32) * (1-alpha) + hm.astype(np.float32) * alpha, 0, 255).astype(np.uint8)

def box_mean(a: np.ndarray, window: int = 9) -> np.ndarray:
    """Mean box filter using integral images; window is forced to an odd integer."""
    w = max(1, int(window)); w = w if w % 2 else w + 1
    x = np.asarray(a, dtype=np.float32)
    if x.ndim != 2: raise ValueError("box_mean accepts 2-D arrays")
    r = w // 2
    padded = np.pad(x, ((r, r), (r, r)), mode="reflect" if min(x.shape) > 1 else "edge")
    integral = np.pad(padded, ((1,0),(1,0)), mode="constant").cumsum(0).cumsum(1)
    sums = integral[w:, w:] - integral[:-w, w:] - integral[w:, :-w] + integral[:-w, :-w]
    return sums / float(w*w)

def line_chart(values: np.ndarray, title: str = "Signal", width: int = 760, height: int = 330, color=(71, 184, 255)) -> Image.Image:
    vals = np.asarray(values, dtype=np.float32).flatten()
    img = Image.new("RGB", (width, height), (7, 15, 29)); d = ImageDraw.Draw(img)
    left, right, top, bottom = 48, width-18, 38, height-36
    for i in range(5):
        y = top + (bottom-top) * i / 4
        d.line((left, y, right, y), fill=(29, 49, 74), width=1)
    for i in range(7):
        x = left + (right-left) * i / 6
        d.line((x, top, x, bottom), fill=(20, 37, 59), width=1)
    d.text((left, 12), title[:80], fill=(201, 223, 246))
    if len(vals) > 1:
        lo, hi = np.nanmin(vals), np.nanmax(vals)
        if hi <= lo: hi = lo + 1
        pts=[]
        for i,v in enumerate(vals):
            x = left + (right-left)*i/(len(vals)-1)
            y = bottom - (bottom-top)*(float(v)-float(lo))/(float(hi)-float(lo))
            pts.append((x,y))
        d.line(pts, fill=color, width=2)
    return img

def histogram_chart(gray: np.ndarray, rgb: np.ndarray | None = None, width: int = 760, height: int = 320) -> Image.Image:
    img = Image.new("RGB", (width,height), (7,15,29)); d=ImageDraw.Draw(img)
    l,r,t,b=42,width-16,32,height-35
    for i in range(5):
        y=t+(b-t)*i/4; d.line((l,y,r,y), fill=(29,49,74))
    if rgb is None:
        h,_=np.histogram(gray,bins=256,range=(0,256)); hs=[(h,(100,180,255))]
    else:
        hs=[]
        for c,col in enumerate([(255,83,83),(64,231,135),(75,135,255)]):
            arr=np.asarray(rgb[...,c]); hh,_=np.histogram(arr,bins=256,range=(0,256));hs.append((hh,col))
    maxv=max(float(v.max()) for v,_ in hs) or 1
    for vals,col in hs:
        pts=[]
        for i,v in enumerate(vals): pts.append((l+(r-l)*i/255, b-(b-t)*float(v)/maxv))
        d.line(pts, fill=col, width=2)
    d.text((l,10),"Intensity distribution",fill=(201,223,246));d.text((l,b+8),"0",fill=(135,160,190));d.text((r-23,b+8),"255",fill=(135,160,190))
    return img

def color_distribution(rgb: np.ndarray, width: int = 760, height: int = 320) -> Image.Image:
    # Quantized bins avoid allocating a huge unique-color table for high-resolution photos.
    q=(rgb.reshape(-1,3)//32).astype(np.uint8); counts={}
    for row in q[::max(1,len(q)//150000)]:
        k=tuple(int(v) for v in row);counts[k]=counts.get(k,0)+1
    top=sorted(counts.items(),key=lambda z:z[1],reverse=True)[:8]
    if not top: top=[((4,4,4),1)]
    vals=np.array([n for _,n in top],dtype=np.float64); total=vals.sum()
    img=Image.new("RGB",(width,height),(7,15,29));d=ImageDraw.Draw(img)
    cx,cy=145,160;radius=100;start=-90
    for (qcol,n) in top:
        extent=float(n/total*360); col=tuple(min(255,int(v*32+16)) for v in qcol)
        d.pieslice((cx-radius,cy-radius,cx+radius,cy+radius),start,start+extent,fill=col,outline=(8,15,28));start+=extent
    d.text((300,18),"Dominant quantized colors",fill=(201,223,246))
    for i,((qcol,n),) in enumerate(zip(top,)):
        y=52+i*30;col=tuple(min(255,int(v*32+16)) for v in qcol);d.rectangle((305,y,325,y+15),fill=col)
        d.text((338,y),f"RGB≈{col}  ·  {n/total*100:.1f}%",fill=(185,207,230))
    return img

def montage(images: list[tuple[str, Image.Image]], cell=(250,170), columns=3) -> Image.Image:
    if not images: return Image.new("RGB",cell,(7,15,29))
    rows=math.ceil(len(images)/columns); out=Image.new("RGB",(columns*cell[0],rows*(cell[1]+28)),(7,15,29));d=ImageDraw.Draw(out)
    for i,(label,im) in enumerate(images):
        im=im.convert("RGB");im.thumbnail((cell[0]-8,cell[1]-8),Image.Resampling.LANCZOS)
        x=(i%columns)*cell[0]+(cell[0]-im.width)//2;y=(i//columns)*(cell[1]+28)+(cell[1]-im.height)//2
        out.paste(im,(x,y));d.text(((i%columns)*cell[0]+8,(i//columns)*(cell[1]+28)+cell[1]+4),label[:32],fill=(205,225,245))
    return out

def pixel_grid(rgb: np.ndarray, size=(760,300), grid=24) -> Image.Image:
    im=Image.fromarray(rgb).convert("RGB"); im.thumbnail((size[0],size[1]),Image.Resampling.LANCZOS)
    pix=np.asarray(im); h,w=pix.shape[:2]
    # Pixel-grid visualization is sampled down first so a source image stays readable.
    step=max(1,int(max(w,h)/grid)); sampled=Image.fromarray(pix).resize((max(1,w//step),max(1,h//step)),Image.Resampling.NEAREST)
    sampled=sampled.resize(size,Image.Resampling.NEAREST)
    d=ImageDraw.Draw(sampled);sw,sh=sampled.size
    for x in range(0,sw,max(1,sw//grid)):d.line((x,0,x,sh),fill=(80,130,170),width=1)
    for y in range(0,sh,max(1,sh//grid)):d.line((0,y,sw,y),fill=(80,130,170),width=1)
    return sampled

def tile_stats(gray: np.ndarray, rows: int=8, cols: int=8) -> tuple[np.ndarray,np.ndarray]:
    h,w=gray.shape;means=np.zeros((rows,cols),np.float32);stds=np.zeros_like(means)
    for iy in range(rows):
        for ix in range(cols):
            tile=gray[iy*h//rows:(iy+1)*h//rows,ix*w//cols:(ix+1)*w//cols]
            if tile.size:means[iy,ix]=tile.mean();stds[iy,ix]=tile.std()
    return means,stds
