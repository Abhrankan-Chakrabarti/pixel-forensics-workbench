"""Orchestrates module execution with per-module failure isolation."""
from __future__ import annotations
import time
from .result_builder import make_result
from .image_context import ImageContext
from ..registry import module_lookup, all_modules
from ..basic.analyzers import analyze as analyze_basic
from .analyzers import analyze as analyze_core
from ..relationships.analyzers import analyze as analyze_relationships
from ..anomaly.analyzers import analyze as analyze_anomaly
from ..forensic.analyzers import analyze as analyze_forensic
from ..data_hiding.analyzers import analyze as analyze_data_hiding
from ..investigation.analyzers import analyze as analyze_investigation
from ..utilities.analyzers import analyze as analyze_utilities

DISPATCH={
 'core':analyze_core,'basic':analyze_basic,'relationships':analyze_relationships,
 'anomaly':analyze_anomaly,'forensic':analyze_forensic,'data_hiding':analyze_data_hiding,
 'investigation':analyze_investigation,'utilities':analyze_utilities,
}

def run_modules(ctx: ImageContext, requested_ids: list[str]) -> list[dict]:
    lookup=module_lookup()
    unknown=[x for x in requested_ids if x not in lookup]
    if unknown: raise ValueError(f"Unknown module IDs: {', '.join(unknown[:8])}")
    wanted=set(requested_ids)
    if not wanted: raise ValueError("Select at least one analysis module.")
    results=[]
    # Always run in registry order so selected modules and exported reports are reproducible.
    for mod in all_modules():
        mid=mod['id']
        if mid not in wanted:continue
        start=time.perf_counter()
        try:
            ctx.previous_results=results
            fn=DISPATCH[mod['key']]
            result=fn(mid,ctx)
            if result is None:raise NotImplementedError(f"Module '{mid}' has no analyzer implementation.")
            result['elapsed_ms']=round((time.perf_counter()-start)*1000,2)
            results.append(result)
        except Exception as exc:
            # Keep the run alive and expose only the error class, not paths or internal details.
            ctx.previous_results=results
            failed=make_result(ctx,mid,'This module failed; other selected modules will continue.',{},[],[f"{type(exc).__name__}: analysis failed; internal details are withheld."],'error')
            failed['elapsed_ms']=round((time.perf_counter()-start)*1000,2)
            results.append(failed)
    return results
