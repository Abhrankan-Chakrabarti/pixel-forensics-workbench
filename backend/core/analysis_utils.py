"""Reusable image signals. These are screening heuristics, not authenticity verdicts."""
from __future__ import annotations
import numpy as np
from PIL import Image, ImageFilter
from .visuals import box_mean, normalize, heatmap, overlay

def local_variance(gray: np.ndarray, window: int = 9) -> np.ndarray:
    mean=box_mean(gray,window); sq=box_mean(gray*gray,window)
    return np.maximum(sq-mean*mean,0)

def local_entropy(gray: np.ndarray, window: int = 9) -> np.ndarray:
    # Entropy of a quantized local grayscale histogram. 16 bins keep the screen quick.
    q=np.clip((gray/16).astype(np.int16),0,15); ent=np.zeros_like(gray,dtype=np.float32)
    for b in range(16):
        p=box_mean((q==b).astype(np.float32),window)
        ent -= np.where(p>1e-7,p*np.log2(np.maximum(p,1e-7)),0)
    return ent

def gradient_magnitude(gray: np.ndarray) -> np.ndarray:
    gx=np.zeros_like(gray,dtype=np.float32);gy=np.zeros_like(gray,dtype=np.float32)
    gx[:,1:-1]=(gray[:,2:]-gray[:,:-2])*.5;gx[:,0]=gray[:,1]-gray[:,0];gx[:,-1]=gray[:,-1]-gray[:,-2]
    gy[1:-1,:]=(gray[2:,:]-gray[:-2,:])*.5;gy[0,:]=gray[1,:]-gray[0,:];gy[-1,:]=gray[-1,:]-gray[-2,:]
    return np.sqrt(gx*gx+gy*gy)

def residual(gray: np.ndarray, window: int = 5) -> np.ndarray:
    smooth=box_mean(gray,window)
    return gray-smooth

def robust_z(a: np.ndarray) -> np.ndarray:
    a=np.asarray(a,dtype=np.float32); med=float(np.median(a)); mad=float(np.median(np.abs(a-med)))
    return (a-med)/max(1.4826*mad,1e-5)

def detect_periodicity(gray: np.ndarray, min_lag: int | None = None, max_lag: int | None = None) -> dict:
    h,w=gray.shape
    # Derive the search bounds from the current image geometry instead of assuming
    # a challenge-specific Magic Eye period. Caller overrides remain available.
    if min_lag is None: min_lag=max(2,int(round(min(h,w)*0.018)))
    if max_lag is None: max_lag=min(w//2,max(min_lag+6,int(round(w*0.42))))
    max_lag=min(max_lag,w//2)
    if max_lag < min_lag+3:
        return {"best_lag":None,"best_correlation":None,"peaks":[],"lags":[],"scores":[]}
    # Sample up to ~80 rows for performance; the image itself is never modified.
    stride=max(1,h//80); a=gray[::stride, :].astype(np.float32)
    scores=[];lags=[]
    for lag in range(min_lag,max_lag+1):
        x=a[:,:-lag]; y=a[:,lag:]
        x=x-x.mean();y=y-y.mean()
        denom=float(np.sqrt(np.sum(x*x)*np.sum(y*y)))
        corr=float(np.sum(x*y)/denom) if denom>1e-8 else 0.0
        scores.append(corr);lags.append(lag)
    sc=np.asarray(scores,dtype=np.float32)
    # Rank local peaks. Ignore trivial near-neighbour effects by evaluating only requested lags.
    peaks=[]
    for i in range(1,len(sc)-1):
        if sc[i]>=sc[i-1] and sc[i]>=sc[i+1]: peaks.append((float(sc[i]),int(lags[i])))
    peaks.sort(reverse=True)
    distinct=[]
    for val,lag in peaks:
        if all(abs(lag-oldlag)>max(3,int(oldlag*.025)) for _,oldlag in distinct): distinct.append((val,lag))
        if len(distinct)>=6: break
    bi=int(np.argmax(sc))
    return {"best_lag":int(lags[bi]),"best_correlation":float(sc[bi]),"peaks":[{"lag":l,"correlation":v} for v,l in distinct],"lags":lags,"scores":[float(v) for v in sc]}

def pixel_dhash(image: Image.Image, hash_size: int = 8) -> str:
    g=image.convert("L").resize((hash_size+1,hash_size),Image.Resampling.LANCZOS)
    a=np.asarray(g,dtype=np.int16);bits=(a[:,1:]>a[:,:-1]).flatten()
    n=0
    for b in bits:n=(n<<1)|int(b)
    return f"{n:0{(hash_size*hash_size+3)//4}x}"

def block_boundary_scores(gray: np.ndarray, block: int = 8) -> dict:
    h,w=gray.shape
    if h < block*2 or w < block*2:return {"vertical_boundary_mean":None,"horizontal_boundary_mean":None,"off_boundary_mean":None,"ratio":None}
    dx=np.abs(gray[:,1:]-gray[:,:-1]);dy=np.abs(gray[1:,:]-gray[:-1,:])
    vx=np.arange(1,w)%block==0;hy=np.arange(1,h)%block==0
    vb=float(dx[:,vx].mean()) if np.any(vx) else 0.0
    hb=float(dy[hy,:].mean()) if np.any(hy) else 0.0
    vo=float(dx[:,~vx].mean()) if np.any(~vx) else 0.0
    ho=float(dy[~hy,:].mean()) if np.any(~hy) else 0.0
    off=(vo+ho)/2; boundary=(vb+hb)/2
    return {"vertical_boundary_mean":vb,"horizontal_boundary_mean":hb,"off_boundary_mean":off,"ratio":boundary/max(off,1e-6)}
