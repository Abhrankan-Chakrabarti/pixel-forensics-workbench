from __future__ import annotations
import numpy as np
from PIL import Image, ImageDraw
from ..core.result_builder import make_result
from ..core.visuals import normalize, montage, heatmap
from ..core.analysis_utils import residual, gradient_magnitude, pixel_dhash

def analyze(module_id,ctx):
    gray=ctx.gray;rgb=ctx.rgb
    if module_id=='normalization':
        lo,hi=np.percentile(gray,[1,99]);norm=np.clip((gray-lo)/max(float(hi-lo),1e-6)*255,0,255).astype(np.uint8)
        return make_result(ctx,module_id,'Stretched luminance contrast between the 1st and 99th percentiles for viewing.',{'lower_percentile':round(float(lo),3),'upper_percentile':round(float(hi),3),'input_range':[round(float(gray.min()),3),round(float(gray.max()),3)]},[('Contrast-normalized image',norm)],['This visualization changes display contrast; the source pixels are not modified.'])
    if module_id=='visualization':
        r=np.abs(residual(gray,5));g=gradient_magnitude(gray)
        visuals=[('Original image',ctx.image),('Grayscale image',Image.fromarray(normalize(gray))),('Residual map',Image.fromarray(heatmap(r))),('Gradient map',Image.fromarray(heatmap(g,'mono')))]
        return make_result(ctx,module_id,'Created independent full-size views of the source and derived image signals.',{'panels':['source','grayscale','residual','gradient'],'separate_visuals':len(visuals)},visuals)
    if module_id=='export':
        return make_result(ctx,module_id,'This run can be exported as a self-contained HTML report or PDF summary after analysis. Use the HTML Report or PDF Report buttons in the results toolbar.',{'html_report_endpoint':'/api/report/{session_id}/html','pdf_report_endpoint':'/api/report/{session_id}/pdf','includes':['image metadata','selected module results','metrics','warnings','visual artifact images']},[],['Visual artifact files are temporary and will be removed with their session after the configured inactivity window.'])
    if module_id=='hashing':
        from hashlib import sha256
        return make_result(ctx,module_id,'Computed a cryptographic SHA-256 digest of the original uploaded file and a perceptual difference hash of the decoded image.',{'sha256_original_file':ctx.metadata['sha256'],'difference_hash_64bit':pixel_dhash(ctx.image),'note':'Perceptual hashes are useful for similarity triage, not cryptographic identity.'},[])
    return None
