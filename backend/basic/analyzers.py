from __future__ import annotations
import numpy as np
from PIL import Image
from ..core.result_builder import make_result
from ..core.visuals import normalize, histogram_chart, color_distribution, montage

def analyze(module_id,ctx):
    rgb=ctx.rgb; gray=ctx.gray
    if module_id=='channels':
        visuals=[]
        for i,name in enumerate(('Red channel','Green channel','Blue channel')):
            plane=np.zeros_like(rgb);plane[...,i]=rgb[...,i]
            visuals.append((name,Image.fromarray(plane)))
        visuals.append(('Grayscale channel',Image.fromarray(normalize(gray))))
        metrics={n:{'min':int(rgb[...,i].min()),'max':int(rgb[...,i].max()),'mean':round(float(rgb[...,i].mean()),2)} for i,n in enumerate(('red','green','blue'))}
        return make_result(ctx,module_id,'Separated RGB channels and grayscale into four independent full-resolution visualizations.',metrics,visuals)
    if module_id=='grayscale':
        v=normalize(gray);return make_result(ctx,module_id,'Converted RGB values to weighted luminance (0.299R + 0.587G + 0.114B).',{'minimum':round(float(gray.min()),2),'maximum':round(float(gray.max()),2),'mean':round(float(gray.mean()),2),'standard_deviation':round(float(gray.std()),2)},[('Grayscale luminance',v)])
    if module_id=='histogram':
        hist,_=np.histogram(gray,bins=256,range=(0,256)); peaks=np.argsort(hist)[-5:][::-1]
        chart_series=[]
        for channel,name,color in ((rgb[...,0],'Red','#ff5d73'),(rgb[...,1],'Green','#42d98b'),(rgb[...,2],'Blue','#5796ff'),(gray,'Luminance','#f4c75b')):
            counts,_=np.histogram(channel,bins=64,range=(0,256))
            chart_series.append({'name':name,'color':color,'x_values':[(i*4)+2 for i in range(64)],'values':counts.tolist()})
        chart={'type':'line','title':'RGB and luminance histogram','x_label':'Intensity (0–255)','y_label':'Pixel count','series':chart_series}
        return make_result(ctx,module_id,'Computed a 256-bin luminance histogram with per-channel distributions.',{'bins':256,'most_populated_bins':[{'intensity':int(i),'pixels':int(hist[i])} for i in peaks],'dark_pixel_fraction':round(float(np.mean(gray<32)),4),'bright_pixel_fraction':round(float(np.mean(gray>223)),4),'median_intensity':round(float(np.median(gray)),2)},[],chart=chart)
    if module_id=='color_distribution':
        q=(rgb.reshape(-1,3)//16).astype(np.uint8); vals,count=np.unique(q,axis=0,return_counts=True); ix=np.argsort(count)[-8:][::-1]
        tops=[{'approx_rgb':[int(v*16+8) for v in vals[i]],'fraction':round(float(count[i]/count.sum()),4)} for i in ix]
        chart_items=[]
        for item in tops:
            r,g,b=item['approx_rgb']
            chart_items.append({'label':f'RGB ({r}, {g}, {b})','value':round(item['fraction']*100,3),'color':f'#{r:02x}{g:02x}{b:02x}'})
        chart={'type':'bar','title':'Dominant colour distribution','x_label':'Share of sampled pixels (%)','items':chart_items,'value_suffix':'%'}
        return make_result(ctx,module_id,'Summarized dominant 16-level RGB quantization buckets (not exact color naming).',{'dominant_quantized_colors':tops,'unique_quantized_colors':int(len(vals))},[],chart=chart)
    return None
