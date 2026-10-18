from __future__ import annotations
import numpy as np
from PIL import Image, ImageDraw
from ..core.result_builder import make_result
from ..core.visuals import heatmap, overlay, tile_stats, normalize, line_chart
from ..core.analysis_utils import local_variance, local_entropy, residual, gradient_magnitude, robust_z

def analyze(module_id,ctx):
    rgb=ctx.rgb;gray=ctx.gray;h,w=gray.shape
    if module_id=='region_compare':
        regions=[]
        boxes=[('top-left',0,0,w//2,h//2),('top-right',w//2,0,w,h//2),('bottom-left',0,h//2,w//2,h),('bottom-right',w//2,h//2,w,h)]
        vis=ctx.image.copy().convert('RGB');d=ImageDraw.Draw(vis)
        for name,x1,y1,x2,y2 in boxes:
            tile=gray[y1:y2,x1:x2]
            regions.append({'region':name,'mean_luminance':round(float(tile.mean()),3),'std_luminance':round(float(tile.std()),3),'dimensions':[x2-x1,y2-y1]})
            d.rectangle((x1,y1,x2-1,y2-1),outline=(57,231,255),width=3);d.text((x1+7,y1+7),name,fill=(255,255,255),stroke_width=2,stroke_fill=(5,15,30))
        return make_result(ctx,module_id,'Compared image quadrants as a first-pass regional summary; no custom ROI has been selected.',{'regions':regions,'mean_luminance_range':round(max(r['mean_luminance'] for r in regions)-min(r['mean_luminance'] for r in regions),3)},[('Quadrant overview',vis)],['Quadrant differences commonly reflect normal scene content or lighting.'])
    if module_id=='hotspot_map':
        r=np.abs(residual(gray,5));v=local_variance(gray,9);g=gradient_magnitude(gray)
        score=.45*normalize(r).astype(np.float32)+.30*normalize(v).astype(np.float32)+.25*normalize(g).astype(np.float32)
        thresh=float(np.percentile(score,98));mask=score>=thresh
        im=ctx.image.copy().convert('RGB');d=ImageDraw.Draw(im);ys,xs=np.where(mask)
        # Draw a restrained set of high-score points so the preview remains legible.
        step=max(1,len(xs)//1500)
        for x,y in zip(xs[::step],ys[::step]):d.point((int(x),int(y)),fill=(255,54,100))
        return make_result(ctx,module_id,'Ranked high-residual, high-variance and high-gradient pixels as candidate hotspots.',{'signal_weights':{'residual':0.45,'variance':0.30,'gradient':0.25},'top_2_percent_threshold':round(thresh,3),'marked_pixels':int(mask.sum()),'marked_fraction':round(float(mask.mean()),5)},[('Hotspot score map',heatmap(score)),('Hotspots on source',im)],['Hotspots are only investigation priorities; no manipulation conclusion is inferred.'])
    if module_id=='tile_analysis':
        means,stds=tile_stats(gray,8,8);zs=robust_z(stds);hmean=robust_z(means)
        rows=[]
        for y in range(8):
            for x in range(8):rows.append({'tile_x':x,'tile_y':y,'mean':round(float(means[y,x]),3),'std':round(float(stds[y,x]),3),'texture_z':round(float(zs[y,x]),3)})
        ranked=sorted(rows,key=lambda r:abs(r['texture_z']),reverse=True)[:8]
        return make_result(ctx,module_id,'Computed mean luminance and texture variability for an 8×8 tile grid.',{'grid':'8 × 8','tile_mean_std':round(float(means.std()),3),'tile_texture_std_std':round(float(stds.std()),3),'most_different_tiles':ranked},[('Tile mean map',heatmap(means)),('Tile texture map',heatmap(stds))])
    if module_id=='fusion':
        numeric=[]
        for result in ctx.previous_results:
            if result.get('module_id')=='fusion':continue
            for k,v in (result.get('metrics') or {}).items():
                if isinstance(v,(int,float)) and not isinstance(v,bool) and np.isfinite(v):numeric.append({'module':result.get('name',result.get('module_id')),'metric':k,'value':float(v),'status':result.get('status','ok')})
        numeric.sort(key=lambda a:abs(a['value']),reverse=True)
        warnings=['Evidence fusion is a descriptive roll-up; metrics have different units and are not directly comparable as probabilities.']
        vals=np.array([min(abs(x['value']),1e6) for x in numeric[:24]],dtype=np.float32)
        chart={'type':'bar','title':'Absolute numeric metrics (mixed units)','x_label':'Absolute recorded value','items':[{'label':f"{x['module']}: {x['metric']}",'value':round(min(abs(x['value']),1e6),5),'color':'#ff68ad' if x['status']=='warning' else '#53a8ff'} for x in numeric[:16]]} if len(numeric)>1 else None
        return make_result(ctx,module_id,'Collected numeric screening metrics from modules that already completed in this run.',{'prior_modules_reviewed':len(ctx.previous_results),'numeric_metrics_collected':len(numeric),'largest_absolute_metrics':numeric[:12]},[],warnings,'warning',chart=chart)
    return None
