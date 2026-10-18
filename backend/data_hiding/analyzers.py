from __future__ import annotations
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from ..core.result_builder import make_result
from ..core.visuals import normalize, heatmap, montage
from ..core.analysis_utils import pixel_dhash

MAGIC={
 'ZIP local file header':b'PK\x03\x04','PDF header':b'%PDF-','RAR header':b'Rar!','7-Zip header':b'7z\xbc\xaf\x27\x1c',
 'PNG header':b'\x89PNG\r\n\x1a\n','GIF header':b'GIF8','ELF header':b'\x7fELF','OLE compound document':b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
}


def _readable_font(size: int, *, mono: bool = False):
    """Load a readable cross-platform font for the hex/ASCII artifact."""
    candidates = (
        [
            r"C:\Windows\Fonts\consola.ttf",
            r"C:\Windows\Fonts\cour.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
            "DejaVuSansMono.ttf",
        ] if mono else [
            r"C:\Windows\Fonts\segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "DejaVuSans.ttf",
        ]
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()

def analyze(module_id,ctx):
    rgb=ctx.rgb;gray=ctx.gray;raw=ctx.original_bytes
    if module_id=='lsb':
        planes=(rgb&1)*255;frac=[round(float(np.mean(rgb[...,c]&1)),5) for c in range(3)]
        viz=np.stack([planes[...,0],planes[...,1],planes[...,2]],axis=2).astype(np.uint8)
        return make_result(ctx,module_id,'Extracted the least-significant bit from each decoded RGB channel and measured its balance.',{'lsb_one_fraction_by_channel':frac,'ideal_random_balance_reference':0.5,'channel_lsb_mean_difference':round(float(np.ptp(frac)),5)},[('RGB LSB planes',viz),('Grayscale LSB map',((np.asarray(ctx.image.convert('L'),dtype=np.uint8)&1)*255))],['A balanced LSB distribution neither proves nor rules out hidden payloads. Pixel decoding discards file-container bytes and may transform palette/alpha data.'])
    if module_id=='bit_extraction':
        # Preserve each low bit-plane as a separate full-resolution visualization.
        visual_planes=[]
        plane_fraction={}
        for channel,idx in [('Red',0),('Green',1),('Blue',2)]:
            for bit in (0,1):
                plane=(((rgb[...,idx]>>bit)&1)*255).astype(np.uint8)
                visual_planes.append((f'{channel} channel - bit {bit}',plane))
                plane_fraction[f'{channel[0]}_bit_{bit}']=round(float(np.mean((rgb[...,idx]>>bit)&1)),5)
        return make_result(ctx,module_id,'Extracted bit positions 0 and 1 from each RGB channel. Each plane is saved separately at analysis resolution.',{'channels':3,'bit_positions':[0,1],'one_fraction':plane_fraction,'separate_plane_images':len(visual_planes)},visual_planes,['Visual patterns in low bit planes need corroboration; normal quantization and sensor noise can look structured.'])
    if module_id=='bitstream':
        sample=raw[:256]
        im=Image.new('RGB',(1680,760),(7,15,29));d=ImageDraw.Draw(im)
        title_font=_readable_font(27)
        row_font=_readable_font(20,mono=True)
        d.text((24,18),'HEX / ASCII VIEW - FIRST 256 ORIGINAL FILE BYTES',font=title_font,fill=(86,219,255))
        d.line((24,60,1656,60),fill=(44,84,121),width=2)
        rows=[]
        for row in range(16):
            chunk=sample[row*16:(row+1)*16]
            if not chunk:break
            hexs=' '.join(f'{b:02X}' for b in chunk)
            ascii_text=''.join(chr(b) if 32<=b<127 else '.' for b in chunk)
            row_text=f'{row*16:04X}   {hexs:<47}   {ascii_text}'
            rows.append(row_text)
            y=76+row*41
            if row%2==0:d.rounded_rectangle((18,y-4,1662,y+31),radius=5,fill=(11,25,43))
            d.text((28,y),row_text,font=row_font,fill=(205,225,244))
        return make_result(ctx,module_id,'Readable 256-byte hex/ASCII sample from the original file. This is a byte view, not OCR or a claim of hidden content.',{'file_bytes':len(raw),'sampled_bytes':len(sample),'first_16_bytes_hex':raw[:16].hex(' '),'printable_ascii_fraction':round(sum(32<=b<127 for b in sample)/max(1,len(sample)),5),'hex_ascii_rows':rows},[('Readable hex and ASCII sample',im)],['The preview does not extract, execute, or open an embedded payload. ASCII glyphs are shown at a larger readable size.'])
    if module_id=='channel_order':
        means=rgb.reshape(-1,3).mean(axis=0);stds=rgb.reshape(-1,3).std(axis=0);corr=np.corrcoef(rgb.reshape(-1,3).astype(np.float32),rowvar=False)
        visuals=[]
        for i,name in enumerate(('Red channel','Green channel','Blue channel')):
            plane=np.zeros_like(rgb);plane[...,i]=rgb[...,i];visuals.append((name,Image.fromarray(plane)))
        return make_result(ctx,module_id,'Compared channel statistics and linear correlations in the decoded RGB image. Each channel is shown independently.',{'channel_means':{n:round(float(v),3) for n,v in zip(('R','G','B'),means)},'channel_stddevs':{n:round(float(v),3) for n,v in zip(('R','G','B'),stds)},'correlation_matrix':np.round(corr,4).tolist()},visuals)
    if module_id=='payload_analysis':
        found=[]
        for name,magic in MAGIC.items():
            start=0;count=0
            while True:
                idx=raw.find(magic,start)
                if idx<0:break
                found.append({'signature':name,'offset':idx,'after_initial_header':idx>32});count+=1;start=idx+1
                if count>=8:break
        fmt=str(ctx.metadata.get('format','')).upper();trailing=None
        if fmt in ('JPEG','JPG'):
            end=raw.rfind(b'\xff\xd9');trailing=len(raw)-(end+2) if end>=0 else None
        elif fmt=='PNG':
            end=raw.rfind(b'IEND\xaeB`\x82');trailing=len(raw)-(end+8) if end>=0 else None
        return make_result(ctx,module_id,'Scanned the original file bytes for a small set of common embedded-file signatures and checked a known end marker where practical.',{'container_format':fmt,'signature_hits':found,'jpeg_bytes_after_last_eoi':trailing if fmt in ('JPEG','JPG') else None,'png_bytes_after_last_iend':trailing if fmt=='PNG' else None},[],['Signature strings can occur by chance inside compressed data. A hit is a lead only, not proof that a valid embedded file exists.'])
    return None
