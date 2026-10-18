"""Shared, validated image context for all analysis modules."""
from __future__ import annotations
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any
import hashlib
import numpy as np
from PIL import Image, ImageOps, ImageFile, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 20_000_000
ImageFile.LOAD_TRUNCATED_IMAGES = False

@dataclass
class ImageContext:
    path: Path
    session_id: str
    result_dir: Path
    source_filename: str | None = None
    max_dimension: int = 1400
    original_bytes: bytes = b""
    image: Image.Image = field(init=False)
    rgb: np.ndarray = field(init=False)
    gray: np.ndarray = field(init=False)
    metadata: dict[str, Any] = field(init=False)
    previous_results: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.original_bytes = self.path.read_bytes()
        with Image.open(BytesIO(self.original_bytes)) as im:
            im.verify()
        with Image.open(BytesIO(self.original_bytes)) as im:
            source_format = im.format or self.path.suffix.lstrip(".").upper() or "Unknown"
            source_mode = im.mode
            original_size = im.size
            exif = {}
            try:
                exif_raw = im.getexif()
                for k, v in exif_raw.items():
                    exif[str(k)] = str(v)[:240]
            except Exception:
                pass
            oriented_image = ImageOps.exif_transpose(im).copy()
            oriented_size = oriented_image.size
            has_alpha = oriented_image.mode in ("RGBA", "LA") or "transparency" in oriented_image.info
            self.image = oriented_image.convert("RGB")
        if max(self.image.size) > self.max_dimension:
            ratio = self.max_dimension / max(self.image.size)
            dims = (max(1, int(self.image.width * ratio)), max(1, int(self.image.height * ratio)))
            self.image = self.image.resize(dims, Image.Resampling.LANCZOS)
        self.rgb = np.asarray(self.image, dtype=np.uint8).copy()
        arr = self.rgb.astype(np.float32)
        self.gray = (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]).astype(np.float32)
        self.metadata = {
            "filename": self.source_filename or self.path.name,
            "format": source_format,
            "source_mode": source_mode,
            "width": int(original_size[0]),
            "height": int(original_size[1]),
            "oriented_width": int(oriented_size[0]),
            "oriented_height": int(oriented_size[1]),
            "analysis_width": int(self.image.width),
            "analysis_height": int(self.image.height),
            "file_size_bytes": len(self.original_bytes),
            "file_size_human": _human_size(len(self.original_bytes)),
            "has_alpha": bool(has_alpha),
            "exif_count": len(exif),
            "exif_preview": dict(list(exif.items())[:20]),
            "sha256": hashlib.sha256(self.original_bytes).hexdigest(),
        }
        self.result_dir.mkdir(parents=True, exist_ok=True)

    def save_visual(self, image: Image.Image | np.ndarray, label: str, module_id: str) -> dict[str, str]:
        """Save a bounded PNG artifact and return a local route URL."""
        if isinstance(image, np.ndarray):
            image = array_to_image(image)
        image = image.copy()
        if image.mode not in ("RGB", "RGBA", "L"):
            image = image.convert("RGB")
        image.thumbnail((1800, 1200), Image.Resampling.LANCZOS)
        safe_module = "".join(c for c in module_id if c.isalnum() or c in "-_ ").strip().replace(" ", "_")[:45] or "module"
        safe_label = "".join(c for c in label if c.isalnum() or c in "-_ ").strip().replace(" ", "_")[:35] or "visual"
        name = f"{safe_module}_{safe_label}.png"
        target = self.result_dir / name
        counter = 1
        while target.exists():
            target = self.result_dir / f"{safe_module}_{safe_label}_{counter}.png"
            counter += 1
        image.save(target, format="PNG", optimize=True)
        return {"label": label, "url": f"/artifacts/{self.session_id}/{target.name}"}

def _human_size(n: int) -> str:
    if n < 1024: return f"{n} B"
    if n < 1024 * 1024: return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"

def array_to_image(arr: np.ndarray) -> Image.Image:
    a = np.asarray(arr)
    if a.dtype != np.uint8:
        finite = np.nan_to_num(a, nan=0.0, posinf=255.0, neginf=0.0)
        if finite.size and (finite.min() < 0 or finite.max() > 255):
            lo, hi = np.percentile(finite, [1, 99]) if finite.size > 20 else (finite.min(), finite.max())
            finite = (finite - lo) / max(float(hi - lo), 1e-9) * 255
        a = np.clip(finite, 0, 255).astype(np.uint8)
    if a.ndim == 2:
        return Image.fromarray(a, mode="L")
    if a.ndim == 3 and a.shape[2] == 3:
        return Image.fromarray(a, mode="RGB")
    if a.ndim == 3 and a.shape[2] == 4:
        return Image.fromarray(a, mode="RGBA")
    raise ValueError("Unsupported visualization array shape")
