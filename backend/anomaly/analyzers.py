from __future__ import annotations
import numpy as np
from PIL import Image, ImageDraw
from ..core.result_builder import make_result
from ..core.visuals import normalize, heatmap, overlay, box_mean, tile_stats
from ..core.analysis_utils import local_variance, local_entropy, residual, robust_z, gradient_magnitude

def analyze(module_id,ctx):
    rgb=ctx.rgb;gray=ctx.gray
    if module_id=='local_variance':
        v=local_variance(gray, 9)
        return make_result(ctx,module_id,'Estimated local luminance variance with an adaptive-size box neighborhood.',{'window_px':9,'variance_mean':round(float(v.mean()),4),'variance_p95':round(float(np.percentile(v,95)),4),'variance_max':round(float(v.max()),4)},[('Local variance map',heatmap(v)),('Variance overlay',overlay(rgb,v))])
    if module_id=='entropy':
        e=local_entropy(gray, 9)
        return make_result(ctx,module_id,'Estimated local entropy from a 16-bin quantized grayscale neighborhood.',{'window_px':9,'quantization_bins':16,'entropy_mean_bits':round(float(e.mean()),4),'entropy_p95_bits':round(float(np.percentile(e,95)),4),'maximum_possible_bits':4},[('Local entropy map',heatmap(e)),('Entropy overlay',overlay(rgb,e))],['Entropy responds to texture and noise; high entropy is not inherently suspicious.'])
    if module_id=='anomaly_scanner':
        r=np.abs(residual(gray,5));v=local_variance(gray,9);e=local_entropy(gray,9);g=gradient_magnitude(gray)
        score=.38*normalize(r).astype(np.float32)+.27*normalize(v).astype(np.float32)+.20*normalize(e).astype(np.float32)+.15*normalize(g).astype(np.float32)
        return make_result(ctx,module_id,'Combined four generic local signals into a ranked candidate map. Scores are screening cues, not evidence of manipulation.',{'signals':['local residual','local variance','quantized entropy','gradient magnitude'],'candidate_score_mean':round(float(score.mean()),2),'candidate_score_p95':round(float(np.percentile(score,95)),2),'candidate_pixels_above_200_fraction':round(float(np.mean(score>200)),5)},[('Combined candidate heatmap',heatmap(score)),('Candidate overlay',overlay(rgb,score))],['Review source context and independent evidence; normal texture can score highly.'])
    if module_id=='color_outlier':
        center=np.median(rgb.reshape(-1,3),axis=0);dist=np.sqrt(np.sum((rgb.astype(np.float32)-center[None,None,:])**2,axis=2))
        return make_result(ctx,module_id,'Measured Euclidean RGB distance from the image-wide median color.',{'median_rgb':[round(float(v),2) for v in center],'distance_p95':round(float(np.percentile(dist,95)),3),'distance_max':round(float(dist.max()),3),'high_distance_fraction':round(float(np.mean(dist>np.percentile(dist,99))),5)},[('Color-distance outliers',heatmap(dist,'red')),('Outlier overlay',overlay(rgb,dist))],['Natural objects, lighting and small color accents can appear as outliers.'])
    if module_id=='noise_analysis':
        r=residual(gray,5);z=robust_z(r);absr=np.abs(r)
        return make_result(ctx,module_id,'Estimated high-frequency residual after a 5-pixel local mean; this is a simple noise screening method.',{'residual_mean':round(float(r.mean()),4),'residual_std':round(float(r.std()),4),'absolute_residual_p95':round(float(np.percentile(absr,95)),4),'robust_z_outlier_fraction':round(float(np.mean(np.abs(z)>3.5)),5)},[('High-frequency residual',heatmap(absr,'mono')),('Residual overlay',overlay(rgb,absr))],['Demosaicing, sharpening, JPEG compression and natural texture all affect residual statistics.'])
    if module_id=='clone_detection':
        h,w=gray.shape;rows=8;cols=8;patches=[];desc=[]
        # Coarse grid matching deliberately favors speed and reports candidates only.
        for iy in range(rows):
            for ix in range(cols):
                tile=gray[iy*h//rows:(iy+1)*h//rows,ix*w//cols:(ix+1)*w//cols]
                if not tile.size:continue
                small=np.asarray(Image.fromarray(normalize(tile)).resize((12,12),Image.Resampling.BILINEAR),dtype=np.float32)
                patches.append(small);desc.append((ix,iy))
        pairs=[]
        for i in range(len(patches)):
            for j in range(i+1,len(patches)):
                if max(abs(desc[i][0]-desc[j][0]),abs(desc[i][1]-desc[j][1]))<=1:continue
                dist=float(np.mean(np.abs(patches[i]-patches[j])))
                if dist<7.5:pairs.append((dist,i,j))
        pairs.sort();im=ctx.image.copy().convert('RGB');d=ImageDraw.Draw(im);cw=w/cols;ch=h/rows
        for dist,i,j in pairs[:8]:
            for k in (i,j):
                x,y=desc[k];d.rectangle((int(x*cw),int(y*ch),int((x+1)*cw),int((y+1)*ch)),outline=(255,72,190),width=3)
        return make_result(ctx,module_id,'Compared coarse image tiles for near-duplicate normalized texture. This is a low-resolution candidate finder, not precise copy-move detection.',{'tiles_compared':len(patches),'near_duplicate_pairs':len(pairs),'top_candidate_pairs':[{'tile_a':list(desc[i]),'tile_b':list(desc[j]),'mean_difference':round(dist,3)} for dist,i,j in pairs[:10]]},[('Repeated-tile candidates',im)],['Repetitive natural patterns (windows, bricks, foliage) can create false positives.'])
    if module_id=='block_anomaly':
        means,stds=tile_stats(gray,8,8);z=robust_z(stds)
        canvas=Image.fromarray(normalize(gray)).convert('RGB');d=ImageDraw.Draw(canvas);h,w=gray.shape
        for y in range(8):
            for x in range(8):
                if abs(z[y,x])>2.5:
                    d.rectangle((x*w//8,y*h//8,(x+1)*w//8,(y+1)*h//8),outline=(255,75,85),width=3)
        return make_result(ctx,module_id,'Compared mean intensity and local standard deviation across an 8×8 tile grid.',{'grid':'8 × 8','mean_intensity_std':round(float(means.std()),3),'tile_texture_std_std':round(float(stds.std()),3),'tiles_above_robust_z_2_5':int(np.sum(np.abs(z)>2.5))},[('Block variation map',heatmap(stds)),('Flagged tile candidates',canvas)],['Block boundaries can correlate with image content and compression; flags need manual review.'])
    return None
