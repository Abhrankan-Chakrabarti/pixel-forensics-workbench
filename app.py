"""Pixel Forensics Workbench local Flask application.

Local-first preview/testing app. Do not expose directly to the public internet without
adding production authentication, CSRF protection, a hardened deployment configuration,
and resource limits appropriate to the deployment environment.
"""
from __future__ import annotations
import json
import html
import base64
import logging
import shutil
import threading
import time
import uuid
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file, abort
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename
from PIL import Image, UnidentifiedImageError

from config import Config
from backend.registry import GROUPS, all_modules
from backend.core.image_context import ImageContext
from backend.core.engine import run_modules

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pixel-forensics")

ALLOWED_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "BMP": ".bmp", "WEBP": ".webp", "TIFF": ".tiff", "GIF": ".gif"}

@dataclass
class Session:
    session_id: str
    upload_path: Path
    original_name: str
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    latest_results: list[dict[str, Any]] = field(default_factory=list)
    report_path: Path | None = None
    busy: bool = False

app = Flask(__name__)
app.config.from_object(Config)
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH
for folder in (app.config["UPLOAD_FOLDER"], app.config["RESULTS_FOLDER"], app.config["REPORTS_FOLDER"], app.config["DATA_FOLDER"] / "cases", app.config["DATA_FOLDER"] / "temp"):
    Path(folder).mkdir(parents=True, exist_ok=True)
SESSIONS: dict[str, Session] = {}
SESSIONS_LOCK = threading.RLock()
ANALYSIS_SEMAPHORE = threading.BoundedSemaphore(Config.MAX_ACTIVE_ANALYSES)
CLEANUP_STARTED = False
# Lightweight per-process abuse controls. Production must additionally use an edge/WAF
# or shared rate-limit store when running more than one application process.
_RATE_BUCKETS: dict[tuple[str, str], list[float]] = {}
_RATE_LOCK = threading.Lock()
RATE_LIMITS = {"upload": (6, 60), "analyze": (4, 60), "other": (90, 60)}


def _safe_session_id(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def _session_roots() -> tuple[Path, ...]:
    return (Path(app.config["UPLOAD_FOLDER"]), Path(app.config["RESULTS_FOLDER"]),
            Path(app.config["REPORTS_FOLDER"]), Path(app.config["DATA_FOLDER"]) / "temp")

def _remove_session_dirs(session_id: str) -> None:
    # UUID validation is required before this helper is called.
    if not _safe_session_id(session_id):
        return
    for root in _session_roots():
        target = root / session_id
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target, ignore_errors=True)
        except OSError:
            log.warning("Could not remove expired session directory")

def _marker_time(directory: Path) -> float:
    marker = directory / ".created_at"
    try:
        return float(marker.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        try:
            return directory.stat().st_mtime
        except OSError:
            return time.time()

def _cleanup_old_directories() -> int:
    now = time.time(); ttl = app.config["SESSION_TTL_SECONDS"]; removed = 0
    with SESSIONS_LOCK:
        expired = [sid for sid, sess in SESSIONS.items() if now - sess.created_at >= ttl and not sess.busy]
        for sid in expired:
            _remove_session_dirs(sid); SESSIONS.pop(sid, None); removed += 1
    # Absolute retention marker prevents newly written outputs from extending retention.
    for root in _session_roots():
        if not root.exists():
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            try:
                if child.name.startswith("."):
                    continue
                if child.is_symlink():
                    child.unlink(missing_ok=True); removed += 1; continue
                if child.is_dir():
                    if now - _marker_time(child) >= ttl:
                        sid = child.name
                        if _safe_session_id(sid):
                            with SESSIONS_LOCK:
                                sess = SESSIONS.get(sid)
                                if sess and sess.busy:
                                    continue
                                SESSIONS.pop(sid, None)
                            _remove_session_dirs(sid); removed += 1
                        else:
                            # Only app-owned UUID session directories are managed here.
                            continue
                elif now - child.stat().st_mtime >= ttl:
                    child.unlink(missing_ok=True); removed += 1
            except OSError:
                continue
    if removed:
        log.info("Removed %s expired temporary artifact group(s)", removed)
    return removed

def _directory_size(directory: Path) -> int:
    total = 0
    try:
        for item in directory.rglob("*"):
            if item.is_symlink():
                continue
            if item.is_file():
                total += item.stat().st_size
    except OSError:
        return app.config["MAX_SESSION_ARTIFACT_BYTES"] + 1
    return total

def _client_key() -> str:
    # Do not trust X-Forwarded-For unless a trusted reverse proxy is explicitly configured.
    return (request.remote_addr or "unknown")[:64]

def _rate_limited(bucket: str) -> bool:
    limit, window = RATE_LIMITS[bucket]
    now = time.time(); key = (_client_key(), bucket)
    with _RATE_LOCK:
        # Bound memory if random client addresses hit the service.
        if len(_RATE_BUCKETS) > 5000:
            cutoff = now - max(v[1] for v in RATE_LIMITS.values())
            for old_key, timestamps in list(_RATE_BUCKETS.items()):
                kept = [stamp for stamp in timestamps if stamp > cutoff]
                if kept: _RATE_BUCKETS[old_key] = kept
                else: _RATE_BUCKETS.pop(old_key, None)
        timestamps = [stamp for stamp in _RATE_BUCKETS.get(key, []) if now - stamp < window]
        if len(timestamps) >= limit:
            _RATE_BUCKETS[key] = timestamps
            return True
        timestamps.append(now); _RATE_BUCKETS[key] = timestamps
        return False

@app.before_request
def request_guardrails():
    if __import__("os").environ.get("PIXEL_FORENSICS_ENV", "development").lower() == "production":
        host = request.host.split(":", 1)[0].lower()
        if host not in app.config.get("ALLOWED_HOSTS", []):
            return jsonify({"error": "Unrecognized host."}), 400
    if request.path.startswith(("/api/", "/artifacts/")):
        bucket = "upload" if request.path == "/api/upload" else "analyze" if request.path == "/api/analyze" else "other"
        if _rate_limited(bucket):
            response = jsonify({"error": "Too many requests. Please wait and try again."})
            response.status_code = 429
            response.headers["Retry-After"] = "60"
            return response
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("Origin")
        if origin:
            from urllib.parse import urlsplit
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != request.host.lower():
                return jsonify({"error": "Cross-origin requests are not allowed."}), 403

def get_session(session_id: str) -> Session | None:
    if not _safe_session_id(session_id): return None
    with SESSIONS_LOCK:
        session = SESSIONS.get(session_id)
        if session and time.time() - session.created_at < app.config["SESSION_TTL_SECONDS"]:
            session.last_access = time.time()
            return session
    return None

def _cleanup_loop() -> None:
    while True:
        time.sleep(app.config["CLEANUP_INTERVAL_SECONDS"])
        try: _cleanup_old_directories()
        except Exception: log.exception("Cleanup loop error")


def start_cleanup_worker() -> None:
    global CLEANUP_STARTED
    if CLEANUP_STARTED: return
    _cleanup_old_directories()
    thread = threading.Thread(target=_cleanup_loop, name="pixel-forensics-cleanup", daemon=True)
    thread.start(); CLEANUP_STARTED = True



@app.get("/")
def index():
    return render_template("index.html")

@app.get("/about")
def about_page():
    return render_template("info_page.html", page="about")

@app.get("/privacy")
def privacy_page():
    return render_template("info_page.html", page="privacy")

@app.get("/terms")
def terms_page():
    return render_template("info_page.html", page="terms")

@app.get("/contact")
def contact_page():
    return render_template("info_page.html", page="contact")

@app.route("/api/health", methods=["GET", "OPTIONS"])
def health():
    if request.method == "OPTIONS":
        resp = app.make_default_options_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        return resp
    resp = jsonify({
        "status": "ok",
        "app": "Pixel Forensics Workbench",
        "version": "1.0.0",
        "mode": "temporary-processing",
        "modules": len(all_modules()),
        "session_ttl_seconds": app.config["SESSION_TTL_SECONDS"],
    })
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    return resp

@app.get("/api/modules")
def modules():
    groups=[]
    for group in GROUPS:
        groups.append({"name":group["name"],"key":group["key"],"description":group["description"],"items":[{"id":x[0],"name":x[1],"description":x[2]} for x in group["items"]]})
    return jsonify({"groups":groups,"count":len(all_modules())})

@app.post("/api/upload")
def upload_image():
    file=request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error":"Choose an image file first."}),400
    raw=file.stream.read(app.config["MAX_UPLOAD_BYTES"]+1)
    if not raw:return jsonify({"error":"The uploaded file is empty."}),400
    if len(raw)>app.config["MAX_UPLOAD_BYTES"]:
        return jsonify({"error":"Image exceeds the 20 MiB upload limit."}),413
    try:
        # Treat Pillow's decompression-bomb warning as a rejection, not a warning to ignore.
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as im:
                fmt=(im.format or "").upper()
                if fmt not in ALLOWED_FORMATS:
                    return jsonify({"error":"Unsupported image format. Use JPEG, PNG, BMP, WEBP, TIFF, or GIF."}),415
                width,height=im.size
                if width <= 0 or height <= 0 or width*height>app.config["MAX_IMAGE_PIXELS"]:
                    return jsonify({"error":"Image dimensions exceed the configured pixel limit."}),413
                # Validate container structure first, then decode only the first frame/page.
                im.verify()
            with Image.open(BytesIO(raw)) as im:
                im.seek(0)
                im.load()
                mode=im.mode
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        log.info("Rejected invalid image upload (%s)", type(exc).__name__)
        return jsonify({"error":"The file could not be decoded as a safe image."}),400
    original_name=secure_filename(file.filename) or "uploaded_image"
    suffix=ALLOWED_FORMATS[fmt]
    # Keep a filename that reflects the decoded format, not a user-supplied extension.
    stem=Path(original_name).stem[:80] or "image"
    sid=str(uuid.uuid4());created=time.time()
    folder=Path(app.config["UPLOAD_FOLDER"])/sid
    try:
        folder.mkdir(parents=True,exist_ok=False,mode=0o700)
        upload_path=folder/(stem+suffix)
        with upload_path.open("xb") as output:
            output.write(raw)
        try: upload_path.chmod(0o600)
        except OSError: pass
        for root in (Path(app.config["RESULTS_FOLDER"]),Path(app.config["REPORTS_FOLDER"]),Path(app.config["DATA_FOLDER"])/"temp"):
            session_folder=root/sid
            session_folder.mkdir(parents=True,exist_ok=True,mode=0o700)
            (session_folder/".created_at").write_text(str(created),encoding="ascii")
        (folder/".created_at").write_text(str(created),encoding="ascii")
    except OSError:
        _remove_session_dirs(sid)
        log.exception("Could not create temporary image session")
        return jsonify({"error":"The server could not create a temporary analysis session."}),500
    metadata={"filename":original_name,"format":fmt,"width":width,"height":height,"mode":mode,"file_size_bytes":len(raw),"file_size_human":f"{len(raw)/(1024*1024):.2f} MB" if len(raw)>=1024*1024 else f"{len(raw)/1024:.1f} KB"}
    session=Session(sid,upload_path,original_name,created_at=created,last_access=created,metadata=metadata)
    with SESSIONS_LOCK:SESSIONS[sid]=session
    log.info("Temporary image session created (%s, %s bytes)",fmt,len(raw))
    return jsonify({"session_id":sid,"image":metadata,"expires_after_seconds":app.config["SESSION_TTL_SECONDS"]}),201

@app.post("/api/analyze")
def analyze():
    if request.content_length is not None and request.content_length > 64 * 1024:
        return jsonify({"error":"Analysis request is too large."}),413
    payload=request.get_json(silent=True) or {}
    sid=payload.get("session_id");requested=payload.get("modules")
    if not isinstance(sid,str) or not isinstance(requested,list):
        return jsonify({"error":"Provide session_id and a list of module IDs."}),400
    if not requested or len(requested)>app.config["MAX_MODULES_PER_RUN"]:
        return jsonify({"error":f"Select between 1 and {app.config['MAX_MODULES_PER_RUN']} modules per run."}),400
    if any(not isinstance(item,str) or len(item)>80 for item in requested):
        return jsonify({"error":"Module IDs must be strings of a valid length."}),400
    requested=list(dict.fromkeys(requested))
    valid_ids={module["id"] for module in all_modules()}
    unknown=sorted(set(requested)-valid_ids)
    if unknown:
        return jsonify({"error":"One or more selected module IDs are invalid."}),400
    session=get_session(sid)
    if session is None or not session.upload_path.is_file():
        return jsonify({"error":"The image session expired or no longer exists. Upload the image again."}),410
    if not ANALYSIS_SEMAPHORE.acquire(blocking=False):
        return jsonify({"error":"The analyzer is busy. Please wait for the current analysis to finish."}),429
    with SESSIONS_LOCK:
        if session.busy:
            ANALYSIS_SEMAPHORE.release()
            return jsonify({"error":"This image session is already being analyzed."}),409
        session.busy=True
    result_dir=Path(app.config["RESULTS_FOLDER"])/sid
    try:
        if result_dir.exists(): shutil.rmtree(result_dir,ignore_errors=True)
        result_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
        marker_time=session.created_at
        (result_dir/".created_at").write_text(str(marker_time),encoding="ascii")
        ctx=ImageContext(path=session.upload_path,session_id=sid,result_dir=result_dir,source_filename=session.original_name,max_dimension=app.config["MAX_ANALYSIS_DIMENSION"])
        results=run_modules(ctx,requested)
        if _directory_size(result_dir) > app.config["MAX_SESSION_ARTIFACT_BYTES"]:
            shutil.rmtree(result_dir,ignore_errors=True)
            return jsonify({"error":"Generated outputs exceeded the per-session storage limit. Run fewer modules at a time."}),507
        # Avoid keeping large result objects in server memory beyond the response/report.
        report={"application":"Pixel Forensics Workbench","version":"1.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"session_id":sid,"image":ctx.metadata,"requested_module_ids":requested,"summary":{"selected":len(requested),"completed":sum(r['status'] in ('ok','warning') for r in results),"failed":sum(r['status']=='error' for r in results),"warnings":sum(r['status']=='warning' for r in results)},"results":results,"disclaimer":"Screening heuristics and visualizations require manual interpretation; they do not independently prove manipulation or hidden data."}
        report_path=Path(app.config["REPORTS_FOLDER"])/sid/"report.json"
        report_path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
        try: report_path.chmod(0o600)
        except OSError: pass
        session.latest_results=results;session.report_path=report_path
        counts={}
        for r in results: counts[r['group_key']]=counts.get(r['group_key'],0)+1
        return jsonify({"session_id":sid,"image":ctx.metadata,"summary":report["summary"],"group_counts":counts,"results":results,"report_url":f"/api/report/{sid}"})
    except ValueError:
        return jsonify({"error":"The requested analysis could not be started. Check the selected modules and image, then try again."}),400
    except Exception as exc:
        log.exception("Analysis failed")
        return jsonify({"error":"Could not complete analysis for this image.","detail":type(exc).__name__}),422
    finally:
        with SESSIONS_LOCK:
            session.busy=False
        ANALYSIS_SEMAPHORE.release()
        # If retention expired while a job was active, purge immediately after it finishes.
        if time.time()-session.created_at >= app.config["SESSION_TTL_SECONDS"]:
            with SESSIONS_LOCK: SESSIONS.pop(sid,None)
            _remove_session_dirs(sid)

@app.delete("/api/session/<session_id>")
def delete_session(session_id):
    if not _safe_session_id(session_id):
        return jsonify({"error":"Invalid session identifier."}),400
    with SESSIONS_LOCK:
        current=SESSIONS.get(session_id)
        if current and current.busy:
            return jsonify({"error":"Analysis is still running; clear the session when it finishes."}),409
        existed=SESSIONS.pop(session_id,None) is not None
    _remove_session_dirs(session_id)
    return jsonify({"deleted":True,"session_existed":existed})

def _load_report_for_download(session_id: str):
    session = get_session(session_id)
    if session is None or not session.report_path or not session.report_path.is_file():
        return None, (jsonify({"error":"No report is available for this session. Run an analysis first."}), 404)
    try:
        return json.loads(session.report_path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError):
        return None, (jsonify({"error":"The stored report could not be read."}), 500)


def _report_html_document(report: dict[str, Any], session_id: str) -> str:
    def esc(value: Any) -> str:
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, indent=2)
        return html.escape(str(value if value is not None else "—"))

    image = report.get("image") or {}
    summary = report.get("summary") or {}
    results = report.get("results") or []
    result_cards = []
    for result in results:
        status = result.get("status", "unknown")
        metrics = result.get("metrics") or {}
        metric_markup = "".join(
            f'<div class="metric"><span>{esc(key.replace("_", " "))}</span><b>{esc(value)}</b></div>'
            for key, value in metrics.items()
        )
        visual_markup = []
        result_root = (Path(app.config["RESULTS_FOLDER"]) / session_id).resolve()
        for visual in result.get("visuals") or []:
            raw_url = str(visual.get("url") or "")
            filename = Path(raw_url.split("?", 1)[0]).name
            if not filename or not filename.lower().endswith(".png") or filename in {".", ".."}:
                continue
            candidate = (result_root / filename).resolve()
            if result_root not in candidate.parents or not candidate.is_file():
                continue
            try:
                data = base64.b64encode(candidate.read_bytes()).decode("ascii")
            except OSError:
                continue
            visual_markup.append(f'<figure><img src="data:image/png;base64,{data}" alt="{esc(visual.get("label", "Analysis visualization"))}"><figcaption>{esc(visual.get("label", "Visualization"))}</figcaption></figure>')
        warnings_markup = ""
        if result.get("warnings"):
            warnings_markup = '<div class="warnings"><b>Analyst notes</b><ul>' + "".join(f"<li>{esc(warning)}</li>" for warning in result["warnings"]) + "</ul></div>"
        visuals_section = f'<div class="visuals">{"".join(visual_markup)}</div>' if visual_markup else ""
        metrics_section = f'<div class="metrics">{metric_markup}</div>' if metric_markup else ""
        result_cards.append(
            f'<article class="result-card"><header><div><small>{esc(result.get("group", "Analysis"))}</small><h2>{esc(result.get("name", result.get("module_id", "Module")))}</h2></div><span class="status {esc(status)}">{esc(status.upper())}</span></header>'
            f'<p>{esc(result.get("summary", "No summary supplied."))}</p>'
            f'{visuals_section}{metrics_section}{warnings_markup}</article>'
        )
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pixel Forensics Workbench — Report</title>
<style>
:root{{font-family:"Segoe UI",Arial,sans-serif;color:#e9f2ff;background:#07101f}}*{{box-sizing:border-box}}body{{margin:0;font-size:15px;line-height:1.55}}main{{max-width:1200px;margin:auto;padding:32px 22px 55px}}.hero{{padding:26px;border:1px solid #28537a;border-radius:18px;background:linear-gradient(130deg,#0b2240,#0b1425 65%,#15102d);box-shadow:0 0 25px #168bff16}}.eyebrow{{font-size:11px;color:#49d9e9;letter-spacing:.14em;font-weight:800}}h1{{font-size:clamp(26px,4vw,38px);line-height:1.2;margin:8px 0}}.sub{{color:#91abc4;margin:5px 0}}.summary{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:15px 0}}.stat,.meta,.metric{{border:1px solid #263e5b;background:#0c192b;padding:12px;border-radius:10px;overflow-wrap:anywhere}}.stat span,.meta span,.metric span{{display:block;color:#91abc4;font-size:12px;text-transform:capitalize}}.stat b{{font-size:23px;display:block;margin-top:3px;color:#49d9e9}}.meta-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:16px 0}}.meta b{{display:block;margin-top:5px}}.disclaimer{{margin:18px 0;padding:13px 15px;border-left:3px solid #ffc247;background:#211b10;color:#f7dfae;border-radius:4px}}.group-title{{font-size:20px;margin:26px 0 10px;color:#72caff}}.result-card{{border:1px solid #28425f;background:#0b1627;border-radius:14px;margin:12px 0;overflow:hidden;break-inside:avoid}}.result-card>header{{display:flex;justify-content:space-between;gap:14px;align-items:center;padding:16px;border-bottom:1px solid #263e5b}}.result-card h2{{margin:3px 0;font-size:19px}}.result-card header small{{font-size:12px;color:#91abc4}}.result-card>p{{margin:15px 16px;color:#d6e5f7}}.status{{font-size:11px;border:1px solid #4d805f;color:#89e8b7;padding:5px 8px;border-radius:6px}}.status.error{{color:#ff98a5;border-color:#91404a}}.status.warning{{color:#ffd080;border-color:#8b6e3b}}.visuals{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:14px}}figure{{margin:0;border:1px solid #263e5b;border-radius:9px;overflow:hidden;background:#030914}}figure img{{display:block;width:100%;height:auto;max-height:700px;object-fit:contain}}figcaption{{padding:8px 10px;color:#91abc4;font-size:12px;border-top:1px solid #263e5b}}.metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:0 14px 14px}}.metric b{{display:block;margin-top:5px;font-size:13px;white-space:pre-wrap;word-break:break-word}}.warnings{{padding:0 16px 15px;color:#ffd080}}footer{{border-top:1px solid #263e5b;margin-top:30px;padding-top:15px;color:#91abc4;font-size:12px}}@media(max-width:700px){{main{{padding:18px 12px}}.summary{{grid-template-columns:repeat(2,minmax(0,1fr))}}.meta-grid,.metrics,.visuals{{grid-template-columns:1fr}}}}@media print{{:root{{background:#fff;color:#17243a}}body{{background:#fff;color:#17243a}}main{{max-width:none;padding:0}}.hero,.stat,.meta,.metric,.result-card{{background:#fff;color:#17243a;box-shadow:none;border-color:#ccd6e2}}.sub,.meta span,.stat span,.metric span,figcaption,footer{{color:#526277}}.result-card{{break-inside:avoid}}.disclaimer{{background:#fff8e9;color:#634b16}}}}
</style></head><body><main>
<header class="hero"><div class="eyebrow">TEMPORARY IMAGE INVESTIGATION · REPORT</div><h1>Pixel Forensics Workbench</h1><p class="sub">Generated {esc(report.get("generated_at", "—"))}</p><p class="sub">Session: {esc(session_id)}</p></header>
<section class="summary"><div class="stat"><span>Selected modules</span><b>{esc(summary.get("selected", len(results)))}</b></div><div class="stat"><span>Completed</span><b>{esc(summary.get("completed", 0))}</b></div><div class="stat"><span>Warnings</span><b>{esc(summary.get("warnings", 0))}</b></div><div class="stat"><span>Failed</span><b>{esc(summary.get("failed", 0))}</b></div></section>
<div class="meta-grid"><div class="meta"><span>Source image</span><b>{esc(image.get("filename", "—"))}</b></div><div class="meta"><span>Dimensions</span><b>{esc(image.get("width", "—"))} × {esc(image.get("height", "—"))}</b></div><div class="meta"><span>Format / mode</span><b>{esc(image.get("format", "—"))} / {esc(image.get("mode", "—"))}</b></div><div class="meta"><span>File size</span><b>{esc(image.get("file_size_human", image.get("file_size_bytes", "—")))}</b></div><div class="meta"><span>SHA-256</span><b>{esc(image.get("sha256", "SHA-256 not included in session metadata"))}</b></div><div class="meta"><span>Generated modules</span><b>{len(results)}</b></div></div>
<div class="disclaimer"><b>Analyst caution:</b> {esc(report.get("disclaimer", "Screening heuristics require manual verification."))} Visualizations do not independently prove manipulation or hidden content.</div>
{''.join(f'<h2 class="group-title">{esc(group)}</h2>' + ''.join(card for card, result in zip(result_cards, results) if (result.get("group") or "Analysis") == group) for group in dict.fromkeys((result.get("group") or "Analysis") for result in results))}
<footer>Generated by Pixel Forensics Workbench · Built by om ctf osint industries. Temporary files are scheduled for deletion at the 10-minute retention threshold.</footer></main></body></html>'''


def _pdf_safe(value: Any) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=True, separators=(", ", ": "))
    text_value = str(value if value is not None else "—")
    # Core PDF fonts are portable ASCII-only; keep the PDF readable on stock systems.
    text_value = text_value.encode("cp1252", "replace").decode("cp1252").encode("ascii", "replace").decode("ascii")
    return text_value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("\r", " ").replace("\n", " ")


def _report_pdf_bytes(report: dict[str, Any], session_id: str) -> bytes:
    image = report.get("image") or {}; summary = report.get("summary") or {}; results = report.get("results") or []
    lines = [
        "PIXEL FORENSICS WORKBENCH", "IMAGE ANALYSIS REPORT", "",
        f"Generated: {report.get('generated_at', '—')}", f"Session: {session_id}",
        f"Source image: {image.get('filename', '—')}",
        f"Dimensions: {image.get('width', '—')} x {image.get('height', '—')}",
        f"Format / mode: {image.get('format', '—')} / {image.get('mode', '—')}",
        f"File size: {image.get('file_size_human', image.get('file_size_bytes', '—'))}",
        f"SHA-256: {image.get('sha256', 'not included in session metadata')}", "",
        f"Modules selected: {summary.get('selected', len(results))}",
        f"Completed: {summary.get('completed', 0)}   Warnings: {summary.get('warnings', 0)}   Failed: {summary.get('failed', 0)}", "",
        "ANALYST CAUTION: Screening signals need manual verification and do not independently prove manipulation or hidden data.", "",
    ]
    for result in results:
        lines.extend([f"{result.get('name', result.get('module_id', 'Module'))} [{str(result.get('status','unknown')).upper()}]", f"Category: {result.get('group', 'Analysis')}"])
        summary_text = str(result.get('summary', 'No summary supplied.'))
        lines.append("Summary: " + summary_text)
        for key, value in (result.get("metrics") or {}).items():
            metric = f"  {str(key).replace('_', ' ')}: {json.dumps(value, ensure_ascii=True) if isinstance(value, (dict, list)) else value}"
            lines.append(metric)
        for warning in result.get("warnings") or []:
            lines.append("  Analyst note: " + str(warning))
        visuals = result.get("visuals") or []
        if visuals:
            lines.append("  Visuals: " + ", ".join(str(v.get("label", "visual")) for v in visuals))
        lines.append("")
    wrapped: list[str] = []
    for line in lines:
        line = str(line)
        if not line:
            wrapped.append(""); continue
        # Wrap on words, preserving readable indentation for metrics.
        indent = "  " if line.startswith("  ") else ""
        words = line.strip().split()
        current = indent
        for word in words:
            if len(current) + len(word) + 1 > 92 and current.strip():
                wrapped.append(current); current = indent + word
            else:
                current = (current + " " + word).strip() if not current.strip() else current + " " + word
        wrapped.append(current)
    pages = [wrapped[i:i+52] for i in range(0, len(wrapped), 52)] or [["Pixel Forensics Workbench report"]]
    objects: dict[int, bytes] = {1: b"<< /Type /Catalog /Pages 2 0 R >>", 3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
    page_ids = []
    for index, page_lines in enumerate(pages):
        page_id = 4 + index * 2; content_id = page_id + 1; page_ids.append(page_id)
        commands = ["BT", "/F1 10 Tf", "48 790 Td", "13 TL"]
        for line_index, line in enumerate(page_lines):
            if line_index: commands.append("T*")
            commands.append(f"({_pdf_safe(line)}) Tj")
        commands.append("ET")
        stream = ("\n".join(commands)).encode("ascii", "replace")
        objects[content_id] = b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
        objects[page_id] = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode("ascii")
    objects[2] = ("<< /Type /Pages /Kids [" + " ".join(f"{x} 0 R" for x in page_ids) + f"] /Count {len(page_ids)} >>").encode("ascii")
    max_id = max(objects)
    output = bytearray(b"%PDF-1.4\n%PFWB\n")
    offsets = [0] * (max_id + 1)
    for object_id in range(1, max_id + 1):
        offsets[object_id] = len(output)
        output.extend(f"{object_id} 0 obj\n".encode("ascii")); output.extend(objects[object_id]); output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {max_id + 1}\n0000000000 65535 f \n".encode("ascii"))
    for object_id in range(1, max_id + 1): output.extend(f"{offsets[object_id]:010d} 00000 n \n".encode("ascii"))
    output.extend(f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(output)


@app.get("/api/report/<session_id>")
def download_report(session_id):
    # Backwards-compatible report URL now downloads human-readable HTML, never JSON.
    return download_report_format(session_id, "html")


@app.get("/api/report/<session_id>/<format_name>")
def download_report_format(session_id, format_name):
    if format_name not in {"html", "pdf"}:
        return jsonify({"error":"Choose HTML or PDF for report export."}), 404
    report, error = _load_report_for_download(session_id)
    if error:
        return error
    if format_name == "html":
        visual_root = Path(app.config["RESULTS_FOLDER"]) / session_id
        if _directory_size(visual_root) > 60 * 1024 * 1024:
            return jsonify({"error":"The HTML report would be too large to embed safely. Use the PDF report instead."}),413
        content = _report_html_document(report, session_id)
        return send_file(BytesIO(content.encode("utf-8")), as_attachment=True, download_name="pixel_forensics_report.html", mimetype="text/html; charset=utf-8", max_age=0)
    return send_file(BytesIO(_report_pdf_bytes(report, session_id)), as_attachment=True, download_name="pixel_forensics_report.pdf", mimetype="application/pdf", max_age=0)

@app.get("/artifacts/<session_id>/<path:filename>")
def artifact(session_id,filename):
    session=get_session(session_id)
    if session is None:return jsonify({"error":"Session expired."}),410
    # Serve only generated PNG artifacts from this session's result folder.
    if Path(filename).name!=filename or not filename.lower().endswith('.png'):
        abort(404)
    root=(Path(app.config["RESULTS_FOLDER"])/session_id).resolve();target=(root/filename).resolve()
    if root not in target.parents or not target.is_file():abort(404)
    return send_file(target,mimetype="image/png",max_age=0,conditional=True)

@app.errorhandler(RequestEntityTooLarge)
def handle_large_upload(_exc):
    return jsonify({"error":"Request exceeds the upload limit."}),413

@app.errorhandler(404)
def not_found(_exc):
    if request.path.startswith('/api/') or request.path.startswith('/artifacts/'):
        return jsonify({"error":"Resource not found."}),404
    return _exc

@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
    response.headers.setdefault("Cache-Control", "no-store, max-age=0")
    response.headers.setdefault("Pragma", "no-cache")
    return response

if __import__("os").environ.get("PIXEL_FORENSICS_ENV", "development").lower() == "production":
    if len(app.config.get("SECRET_KEY", "")) < 32:
        raise RuntimeError("Set PIXEL_FORENSICS_SECRET to a random value of at least 32 characters for production.")
    if not app.config.get("ALLOWED_HOSTS") or not all("*" not in host for host in app.config["ALLOWED_HOSTS"]):
        raise RuntimeError("Set PIXEL_FORENSICS_ALLOWED_HOSTS to explicit production hostnames; wildcards are not allowed.")

start_cleanup_worker()

if __name__ == '__main__':
    # Debug/reloader is disabled so the cleanup worker is not duplicated.
    app.run(host='127.0.0.1',port=5000,debug=False,threaded=True)
