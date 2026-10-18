"""Single source of truth for UI modules and analyzer dispatch."""
GROUPS = [
 {"name":"Core Modules", "key":"core", "description":"Image loading, metadata and pixel access", "items":[
  ("image_loader","Image Loader","Decode and normalize image input"),("image_info","Image Information","Dimensions, channels, format and file metadata"),("pixel_reader","Pixel Reader","Inspect sampled RGB values"),("coordinate","Coordinate Analysis","Map image coordinates and channel values")]},
 {"name":"Basic Analysis", "key":"basic", "description":"Channels, luminance and statistics", "items":[
  ("channels","Color Channels","RGB and grayscale channel visualizations"),("grayscale","Grayscale Conversion","Luminance map"),("histogram","Histogram Analysis","Intensity distribution and peaks"),("color_distribution","Color Distribution","Dominant quantized color profile")]},
 {"name":"Pixel Relationships", "key":"relationships", "description":"Differences, repetition and bit-level structure", "items":[
  ("difference","Pixel Difference","Horizontal and vertical adjacent-pixel differences"),("autostereogram","Autostereogram (Depth) — Adaptive","Adaptive repetition-period and disparity/depth estimation"),("xor_analysis","XOR Analysis","Bitwise difference maps and bit balance"),("correlation","Correlation Analysis","Horizontal periodicity and autocorrelation"),("bit_planes","Bit Plane Analysis","Visualize the eight grayscale bit planes")]},
 {"name":"Anomaly Detection", "key":"anomaly", "description":"Local irregularities and candidate regions", "items":[
  ("anomaly_scanner","Anomaly Scanner","Fuse residual, local variance and entropy cues"),("local_variance","Local Variance","Local intensity variation map"),("entropy","Entropy Analysis","Local grayscale entropy estimate"),("color_outlier","Color Outlier Detection","Color-distance outlier candidates"),("noise_analysis","Noise Analysis","Residual/noise distribution"),("clone_detection","Clone Detection","Repeated coarse image-tile candidates"),("block_anomaly","Block Anomaly","Block-level statistical deviations")]},
 {"name":"Image Forensics", "key":"forensic", "description":"Spatial, frequency and compression indicators", "items":[
  ("residual","Residual Analysis","Difference from a local smooth estimate"),("highpass","High Pass Filter","Fine detail and abrupt changes"),("lowpass","Low Pass Filter","Low-frequency image structure"),("gradient","Gradient Analysis","Intensity-gradient magnitude"),("edges","Edge Detection","Strong local boundaries"),("laplacian","Laplacian Analysis","Second-order intensity changes"),("fft_analysis","FFT Analysis","Frequency-domain periodicity"),("dct_analysis","DCT Analysis","8×8 block frequency coefficients"),("jpeg_analysis","JPEG Analysis","JPEG markers and 8-pixel boundary screening"),("double_compression","Double Compression","Heuristic DCT histogram screening"),("ela","Error Level Analysis (ELA)","JPEG recompression-difference visualization")]},
 {"name":"Data Hiding & Bitstream", "key":"data_hiding", "description":"Least-significant bits and file structure", "items":[
  ("lsb","LSB Analysis","Least-significant-bit balance and map"),("bit_extraction","Bit Extraction","Extract selected bit planes"),("bitstream","Bitstream Inspection","Inspect an initial bounded byte sample"),("channel_order","Channel Order","Compare RGB channel and bit-order signals"),("payload_analysis","Payload Analysis","Look for common embedded-file signatures and trailing bytes")]},
 {"name":"Investigation & Comparison", "key":"investigation", "description":"Regions, hotspots and evidence correlation", "items":[
  ("region_compare","Region Comparison","Compare quadrant-level statistics"),("hotspot_map","Hotspot Map","Rank candidate irregular areas"),("tile_analysis","Tile Analysis","Compare image tiles statistically"),("fusion","Evidence Fusion","Combine available screening metrics")]},
 {"name":"Utilities & Reporting", "key":"utilities", "description":"Normalization, visualization, export and hashes", "items":[
  ("normalization","Normalization","Normalize contrast for viewing"),("visualization","Visualization","Build a source/channel overview montage"),("export","Export Results","Create an on-screen structured report summary"),("hashing","Image Hashes","SHA-256 and perceptual image hashes")]},
]

def all_modules():
    out=[]
    for group in GROUPS:
        for mid,name,description in group["items"]:
            out.append({"id":mid,"name":name,"description":description,"group":group["name"],"key":group["key"]})
    return out

def module_lookup():
    return {m["id"]:m for m in all_modules()}
