from __future__ import annotations
import numpy as np
from PIL import Image
from ..core.result_builder import make_result
from ..core.visuals import normalize, heatmap, line_chart, montage, box_mean
from ..core.analysis_utils import detect_periodicity

def _disparity_map(gray: np.ndarray, period: int):
    h,w=gray.shape
    radius=max(2,min(18,int(round(period*.06))))
    lo=max(4,period-radius);hi=min(w//2,period+radius)
    candidates=list(range(lo,hi+1))
    margin=hi;out_w=w-2*margin
    if out_w<24 or not candidates:return None,[],None
    center=gray[:,margin:w-margin]
    win=max(5,min(17,(period//18)|1));best=np.full((h,out_w),np.inf,np.float32);bestlag=np.zeros((h,out_w),np.float32)
    for lag in candidates:
        prior=gray[:,margin-lag:w-margin-lag]
        diff=np.abs(center-prior)
        score=box_mean(diff,win)
        mask=score<best
        best[mask]=score[mask];bestlag[mask]=lag
    return bestlag,candidates,best

def analyze(module_id,ctx):
    rgb=ctx.rgb;gray=ctx.gray
    if module_id=='difference':
        dx=np.zeros_like(gray);dy=np.zeros_like(gray);dx[:,1:]=np.abs(gray[:,1:]-gray[:,:-1]);dy[1:,:]=np.abs(gray[1:,:]-gray[:-1,:]);combo=np.maximum(dx,dy)
        return make_result(ctx,module_id,'Calculated adjacent horizontal and vertical luminance differences.',{'horizontal_mean_abs_difference':round(float(dx.mean()),3),'vertical_mean_abs_difference':round(float(dy.mean()),3),'maximum_difference':round(float(combo.max()),2)},[('Difference intensity',heatmap(combo,'mono')),('Difference heatmap',heatmap(combo))])
    if module_id=='autostereogram':
        periodic=detect_periodicity(gray)
        lag=periodic.get('best_lag'); corr=periodic.get('best_correlation')
        if lag is None:
            return make_result(ctx,module_id,'Image is too narrow to estimate a meaningful horizontal repeat period.',{'candidate_period_px':None,'correlation':None},[],['Autostereogram recovery is image-dependent; no usable period range was available.'],'warning')
        # When the source is very large, analyze a resized grayscale copy to keep the candidate sweep bounded.
        work=gray
        if max(work.shape)>1100:
            factor=1100/max(work.shape);work=np.asarray(Image.fromarray(normalize(work)).resize((int(gray.shape[1]*factor),int(gray.shape[0]*factor)),Image.Resampling.BILINEAR),dtype=np.float32)
            scale=work.shape[1]/gray.shape[1]; lag=max(4,int(round(lag*scale)))
        else:scale=1.0
        disp,candidates,score=_disparity_map(work,lag)
        visuals=[]
        sample_idx=np.linspace(0,max(0,len(periodic['lags'])-1),min(100,len(periodic['lags'])),dtype=int) if periodic['lags'] else np.array([],dtype=int)
        chart={'type':'line','title':'Horizontal autocorrelation by lag','x_label':'Horizontal lag (pixels)','y_label':'Correlation','series':[{'name':'Correlation','color':'#39e7ff','x_values':[int(periodic['lags'][i]) for i in sample_idx],'values':[float(periodic['scores'][i]) for i in sample_idx]}]} if len(sample_idx) else None
        metrics={'candidate_period_px_original_scale':round(float(periodic['best_lag']),2),'best_global_correlation':round(float(corr),5) if corr is not None else None,'strongest_period_peaks':periodic['peaks'][:5],'candidate_disparity_count':len(candidates),'analysis_scale':round(float(scale),4)}
        warnings=['This is a heuristic candidate depth map, not guaranteed 3-D recovery. Flat/ordinary images can produce misleading periodicity peaks.']
        if disp is not None and score is not None:
            visuals.extend([('Adaptive disparity / depth map',heatmap(disp)),('Best-match error map',heatmap(score,'red'))])
            metrics.update({'estimated_disparity_min_px':round(float(disp.min()/max(scale,1e-9)),2),'estimated_disparity_max_px':round(float(disp.max()/max(scale,1e-9)),2),'mean_local_match_error':round(float(score.mean()),3),'depth_map_variation_std_px':round(float(disp.std()/max(scale,1e-9)),3)})
        else:
            warnings.append('The image width was too small for a stable local disparity map; only the repetition sweep is shown.')
        status='ok' if corr is not None and corr>0.10 else 'warning'
        return make_result(ctx,module_id,'Swept horizontal lags automatically, ranked global repetition candidates, then estimated local disparity around the strongest period.',metrics,visuals,warnings,status,chart=chart)
    if module_id=='xor_analysis':
        x=np.bitwise_xor(rgb[:,1:,:],rgb[:,:-1,:]);xgray=x.astype(np.float32).mean(axis=2)
        ones=[int(np.unpackbits(rgb[...,c].flatten()).sum()) for c in range(3)]
        total=rgb.shape[0]*rgb.shape[1]*8
        return make_result(ctx,module_id,'Applied byte-wise XOR to horizontally adjacent RGB pixels and summarized bit balance.',{'xor_mean':round(float(x.mean()),3),'xor_nonzero_fraction':round(float(np.mean(x!=0)),5),'source_bit_one_fraction_by_channel':[round(v/total,5) for v in ones]},[('Horizontal XOR map',heatmap(xgray)),('XOR contrast',normalize(xgray))])
    if module_id=='correlation':
        p=detect_periodicity(gray)
        if p['best_lag'] is None:return make_result(ctx,module_id,'Image is too narrow to sweep horizontal periodicity.',{},[],['No valid lag range.'],'warning')
        sample_idx=np.linspace(0,len(p['lags'])-1,min(100,len(p['lags'])),dtype=int)
        chart={'type':'line','title':'Horizontal correlation sweep','x_label':'Horizontal lag (pixels)','y_label':'Correlation','series':[{'name':'Correlation','color':'#39e7ff','x_values':[int(p['lags'][i]) for i in sample_idx],'values':[float(p['scores'][i]) for i in sample_idx]}]}
        return make_result(ctx,module_id,'Measured normalized horizontal correlation over a data-derived lag range.',{'best_lag_px':p['best_lag'],'best_correlation':round(p['best_correlation'],5),'ranked_peaks':p['peaks'][:6],'lags_tested':len(p['lags'])},[],chart=chart)
    if module_id=='bit_planes':
        planes=[]
        g=np.clip(gray,0,255).astype(np.uint8)
        for bit in range(7,-1,-1):
            plane=(((g>>bit)&1)*255).astype(np.uint8)
            planes.append((f'Grayscale bit plane {bit}',plane))
        metrics={'planes':8,'per_plane_one_fraction':{f'bit_{i}':round(float(np.mean((g>>i)&1)),5) for i in range(8)},'note':'Bit-plane patterns are not proof of steganography.','separate_plane_images':len(planes)}
        return make_result(ctx,module_id,'Split grayscale values into eight binary planes from most significant to least significant. Each plane is displayed as an independent image.',metrics,planes)
    return None
