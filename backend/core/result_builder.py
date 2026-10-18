"""Consistent result schema shared by every analysis module."""
from __future__ import annotations
from typing import Any
from PIL import Image
import numpy as np
from .image_context import ImageContext
from ..registry import module_lookup

def make_result(ctx: ImageContext, module_id: str, summary: str, metrics: dict[str, Any] | None = None,
                visuals: list[tuple[str, Image.Image | np.ndarray]] | None = None,
                warnings: list[str] | None = None, status: str = "ok", chart: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = module_lookup().get(module_id, {"id":module_id,"name":module_id,"group":"Unknown","key":"unknown"})
    visual_refs=[]
    for label,visual in (visuals or []):
        try: visual_refs.append(ctx.save_visual(visual, label, module_id))
        except Exception as exc:
            (warnings := list(warnings or [])).append(f"Visualization '{label}' could not be saved: {type(exc).__name__}")
    return {
        "module_id": module_id, "name": meta["name"], "group": meta["group"], "group_key": meta["key"],
        "status": status, "summary": str(summary), "metrics": json_safe(metrics or {}),
        "visuals": visual_refs, "warnings": list(warnings or []),
        "chart": json_safe(chart) if chart else None,
    }

def json_safe(value: Any) -> Any:
    if isinstance(value, dict): return {str(k):json_safe(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)): return [json_safe(v) for v in value]
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (np.floating,)): return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.ndarray): return json_safe(value.tolist())
    if isinstance(value, (str,int,float,bool)) or value is None: return value
    return str(value)
