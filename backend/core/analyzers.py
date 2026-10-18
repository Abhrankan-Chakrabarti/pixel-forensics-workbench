from __future__ import annotations
from PIL import Image, ImageDraw
import numpy as np
from .result_builder import make_result
from .visuals import pixel_grid

def analyze(module_id, ctx):
    m=ctx.metadata; rgb=ctx.rgb; gray=ctx.gray; h,w=gray.shape
    if module_id=='image_loader':
        return make_result(ctx,module_id,'Image decoded successfully and normalized to RGB for shared analysis.',{'original_dimensions':f"{m['width']} × {m['height']}",'analysis_dimensions':f"{w} × {h}",'file_size':m['file_size_human'],'alpha_channel':m['has_alpha']},[('Source preview',ctx.image)])
    if module_id=='image_info':
        metrics={k:m[k] for k in ('filename','format','source_mode','width','height','oriented_width','oriented_height','analysis_width','analysis_height','file_size_human','has_alpha','exif_count','sha256')}
        return make_result(ctx,module_id,'Extracted file and decoded-image properties. Metadata alone does not prove image authenticity.',metrics,[('Image information',ctx.image)],['EXIF values can be absent, edited, or copied from another image.'])
    if module_id=='pixel_reader':
        yy,xx=h//2,w//2; r,g,b=[int(v) for v in rgb[yy,xx]]
        return make_result(ctx,module_id,'Sampled the center pixel after EXIF orientation and analysis-size scaling.',{'sample_x_analysis':xx,'sample_y_analysis':yy,'rgb':[r,g,b],'hex':f'#{r:02x}{g:02x}{b:02x}','analysis_dimensions':f'{w} × {h}'},[('Pixel grid preview',pixel_grid(rgb))],['Coordinates are relative to the scaled analysis copy, not necessarily the original full-resolution file.'])
    if module_id=='coordinate':
        im=ctx.image.copy().convert('RGB'); d=ImageDraw.Draw(im); x=w//2;y=h//2
        d.rectangle((x-30,y-30,x+30,y+30),outline=(255,72,190),width=3);d.line((x,0,x,h),fill=(255,72,190),width=1);d.line((0,y,w,y),fill=(255,72,190),width=1)
        r,g,b=[int(v) for v in rgb[y,x]]
        return make_result(ctx,module_id,'Marked the image center as a reference coordinate and reported its RGB value.',{'x_analysis':x,'y_analysis':y,'rgb':[r,g,b],'normalized_x':round(x/max(w-1,1),5),'normalized_y':round(y/max(h-1,1),5)},[('Center coordinate',im)],['The marker uses analysis-image coordinates; export coordinates should be rescaled to the source dimensions.'])
    return None
