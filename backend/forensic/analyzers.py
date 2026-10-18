from __future__ import annotations
import io, math
import numpy as np
from PIL import Image, ImageDraw
from ..core.result_builder import make_result
from ..core.visuals import normalize, heatmap, overlay, line_chart, box_mean
from ..core.analysis_utils import residual, gradient_magnitude, block_boundary_scores

def _laplacian(a):
    p=np.pad(a,((1,1),(1,1)),mode='reflect')
    return p[1:-1,:-2]+p[1:-1,2:]+p[:-2,1:-1]+p[2:,1:-1]-4*p[1:-1,1:-1]

def _dct_coefficients(gray):
    h,w=gray.shape;h-=h%8;w-=w%8
    if h<8 or w<8:return None
    a=gray[:h,:w].reshape(h//8,8,w//8,8).transpose(0,2,1,3).astype(np.float32)-128
    n=np.arange(8);k=n[:,None]
    c=np.cos((2*n[None,:]+1)*k*np.pi/16).astype(np.float32)
    c[0]*=1/np.sqrt(2);c*=np.sqrt(2/8)
    coeff=np.einsum('ij,abjk,lk->abil',c,a,c,optimize=True)
    return coeff

def analyze(module_id,ctx):
    rgb=ctx.rgb;gray=ctx.gray
    if module_id=='residual':
        r=residual(gray,5)
        return make_result(ctx,module_id,'Computed the signed residual from a 5-pixel local mean.',{'residual_mean':round(float(r.mean()),4),'residual_std':round(float(r.std()),4),'absolute_residual_p95':round(float(np.percentile(np.abs(r),95)),4)},[('Signed residual',heatmap(r,'mono')),('Residual magnitude',heatmap(np.abs(r)))],['Residual differences can arise from natural texture, sharpening and compression.'])
    if module_id=='highpass':
        hp=gray-box_mean(gray,3)
        return make_result(ctx,module_id,'Applied a simple high-pass operation (image minus 3×3 local mean).',{'highpass_mean':round(float(hp.mean()),4),'highpass_std':round(float(hp.std()),4),'absolute_p95':round(float(np.percentile(np.abs(hp),95)),4)},[('High-pass detail',heatmap(np.abs(hp),'mono'))])
    if module_id=='lowpass':
        lp=box_mean(gray, 9)
        return make_result(ctx,module_id,'Applied a 9×9 local mean to show low-frequency structure.',{'lowpass_mean':round(float(lp.mean()),3),'lowpass_std':round(float(lp.std()),3)},[('Low-pass image',normalize(lp))])
    if module_id=='gradient':
        grad=gradient_magnitude(gray)
        return make_result(ctx,module_id,'Estimated luminance gradient magnitude from centered first differences.',{'gradient_mean':round(float(grad.mean()),3),'gradient_p95':round(float(np.percentile(grad,95)),3),'gradient_max':round(float(grad.max()),3)},[('Gradient magnitude',heatmap(grad,'mono'))])
    if module_id=='edges':
        grad=gradient_magnitude(gray);threshold=float(np.percentile(grad,88));edges=(grad>=threshold).astype(np.uint8)*255
        return make_result(ctx,module_id,'Marked the strongest 12% of gradient values as edge candidates.',{'adaptive_threshold':round(threshold,3),'edge_pixel_fraction':round(float(np.mean(edges>0)),5)},[('Edge candidates',edges),('Edge overlay',overlay(rgb,edges,.55))],['This percentile-based detector is a visual aid, not a semantic edge detector.'])
    if module_id=='laplacian':
        lap=_laplacian(gray)
        return make_result(ctx,module_id,'Computed a four-neighbor discrete Laplacian over luminance.',{'laplacian_mean':round(float(lap.mean()),4),'laplacian_std':round(float(lap.std()),4),'abs_p99':round(float(np.percentile(np.abs(lap),99)),3)},[('Laplacian response',heatmap(np.abs(lap),'mono'))])
    if module_id=='fft_analysis':
        work=gray
        if max(work.shape)>512:
            ratio=512/max(work.shape);work=np.asarray(Image.fromarray(normalize(work)).resize((max(16,int(work.shape[1]*ratio)),max(16,int(work.shape[0]*ratio))),Image.Resampling.BILINEAR),dtype=np.float32)
        spectrum=np.log1p(np.abs(np.fft.fftshift(np.fft.fft2(work-work.mean()))))
        return make_result(ctx,module_id,'Computed a bounded 2-D FFT magnitude spectrum on a resized analysis image.',{'fft_dimensions':list(work.shape[::-1]),'spectrum_mean':round(float(spectrum.mean()),4),'spectrum_p99':round(float(np.percentile(spectrum,99)),4),'dc_center_suppressed':True},[('Log FFT magnitude',heatmap(spectrum))],['Frequency peaks can reflect regular scene texture, scaling or compression as well as processing artifacts.'])
    if module_id=='dct_analysis':
        coeff=_dct_coefficients(gray)
        if coeff is None:return make_result(ctx,module_id,'Image is too small for 8×8 DCT blocks.',{},[],['At least 8×8 pixels are required.'],'warning')
        ac=coeff.copy();ac[...,0,0]=0;flat=ac.ravel();hist,_=np.histogram(flat,bins=100,range=(-100,100))
        sample=np.clip(np.abs(coeff[0: min(20,coeff.shape[0]),0:min(20,coeff.shape[1])]).mean(axis=(0,1)),0,255)
        chart={'type':'line','title':'DCT AC coefficient distribution','x_label':'AC coefficient value','y_label':'Coefficient count','series':[{'name':'AC coefficients','color':'#b799ff','x_values':np.linspace(-99,99,100).round(2).tolist(),'values':hist.astype(int).tolist()}]}
        return make_result(ctx,module_id,'Computed orthonormal 8×8 DCT coefficients on aligned luminance blocks.',{'block_grid':[int(coeff.shape[1]),int(coeff.shape[0])],'coefficient_mean':round(float(flat.mean()),4),'coefficient_std':round(float(flat.std()),4),'zero_or_near_zero_fraction':round(float(np.mean(np.abs(flat)<1)),5),'ac_histogram_bins':100},[('Mean block coefficient map',heatmap(np.mean(np.abs(coeff),axis=(2,3))))],['DCT statistics vary with content and encoding; isolated patterns are not proof of editing.'],chart=chart)
    if module_id=='jpeg_analysis':
        b=block_boundary_scores(gray,8);is_jpeg=str(ctx.metadata['format']).upper() in ('JPEG','JPG')
        return make_result(ctx,module_id,'Checked decoded pixels for 8-pixel boundary differences and read the original file format.',{'container_format':ctx.metadata['format'],'jpeg_encoded_container':is_jpeg,**{k:(round(v,4) if isinstance(v,float) else v) for k,v in b.items()}},[('Eight-pixel boundary map',heatmap(np.abs(np.diff(gray,axis=1)[:,7::8]).mean(axis=0)[None,:] if gray.shape[1]>8 else np.zeros((1,1))))],['A JPEG file or 8-pixel boundary signal alone does not establish manipulation or recompression history.'])
    if module_id=='double_compression':
        coeff=_dct_coefficients(gray)
        if coeff is None:return make_result(ctx,module_id,'Image is too small for block-DCT screening.',{},[],['At least 8×8 pixels are required.'],'warning')
        ac=coeff[...,1:,:].ravel();ac=ac[np.isfinite(ac)];ac=np.clip(ac,-64,64)
        hist,_=np.histogram(ac,bins=129,range=(-64.5,64.5));peaks=np.argsort(hist)[-8:][::-1]
        chart={'type':'line','title':'DCT coefficient distribution','x_label':'Quantized coefficient value','y_label':'Coefficient count','series':[{'name':'Coefficient count','color':'#ffb64d','x_values':np.linspace(-64,64,129).tolist(),'values':hist.astype(int).tolist()}]}
        return make_result(ctx,module_id,'Ran a coarse DCT coefficient histogram screen for quantization-like patterns.',{'heuristic':'coarse DCT histogram; not a validated double-JPEG detector','coefficient_std':round(float(ac.std()),4),'histogram_peak_bins':[int(i) for i in peaks[:5]],'histogram_peak_counts':[int(hist[i]) for i in peaks[:5]]},[],['This heuristic cannot establish double compression. Reliable JPEG history analysis requires format-specific quantization tables, aligned block analysis and independent corroboration.'],'warning',chart=chart)
    if module_id=='ela':
        buf=io.BytesIO();ctx.image.save(buf,format='JPEG',quality=90,optimize=True);buf.seek(0)
        rec=np.asarray(Image.open(buf).convert('RGB'),dtype=np.int16);src=rgb.astype(np.int16);diff=np.abs(src-rec).astype(np.uint8);score=diff.max(axis=2)
        return make_result(ctx,module_id,'Re-encoded the current RGB analysis copy as JPEG quality 90 and compared pixel differences.',{'recompression_quality':90,'mean_absolute_difference':round(float(diff.mean()),4),'p95_channel_difference':round(float(np.percentile(diff,95)),3),'high_difference_fraction':round(float(np.mean(score>32)),5)},[('ELA-style difference',heatmap(score,'red')),('Difference amplified ×4',np.clip(diff.astype(np.int16)*4,0,255).astype(np.uint8))],['ELA is highly dependent on original format, quality and editing history; highlighted regions are not proof of tampering.'])
    return None
