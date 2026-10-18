"""Environment-driven configuration for Pixel Forensics Workbench."""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent

def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))

class Config:
    # Public deployment MUST set PIXEL_FORENSICS_SECRET to a long random value.
    SECRET_KEY = os.environ.get("PIXEL_FORENSICS_SECRET", "")
    ALLOWED_HOSTS = [host.strip().lower() for host in os.environ.get("PIXEL_FORENSICS_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if host.strip()]
    MAX_UPLOAD_BYTES = _int_env("PIXEL_FORENSICS_MAX_UPLOAD_BYTES", 20 * 1024 * 1024, 1024 * 1024, 20 * 1024 * 1024)
    # Allow a little multipart/form-data overhead beyond the file's own cap.
    MAX_CONTENT_LENGTH = MAX_UPLOAD_BYTES + 1024 * 1024
    UPLOAD_FOLDER = Path(os.environ.get("PIXEL_FORENSICS_UPLOAD_DIR", str(BASE_DIR / "uploads"))).resolve()
    RESULTS_FOLDER = Path(os.environ.get("PIXEL_FORENSICS_RESULTS_DIR", str(BASE_DIR / "results"))).resolve()
    REPORTS_FOLDER = Path(os.environ.get("PIXEL_FORENSICS_REPORTS_DIR", str(BASE_DIR / "reports"))).resolve()
    DATA_FOLDER = Path(os.environ.get("PIXEL_FORENSICS_DATA_DIR", str(BASE_DIR / "data"))).resolve()
    # Retention is capped at 10 minutes; operators may choose a shorter period.
    SESSION_TTL_SECONDS = _int_env("PIXEL_FORENSICS_TTL_SECONDS", 600, 60, 600)
    CLEANUP_INTERVAL_SECONDS = 15
    MAX_IMAGE_PIXELS = _int_env("PIXEL_FORENSICS_MAX_IMAGE_PIXELS", 20_000_000, 1_000_000, 20_000_000)
    MAX_ANALYSIS_DIMENSION = 1400
    MAX_SESSION_ARTIFACT_BYTES = _int_env("PIXEL_FORENSICS_MAX_SESSION_ARTIFACT_BYTES", 150 * 1024 * 1024, 16 * 1024 * 1024, 250 * 1024 * 1024)
    MAX_MODULES_PER_RUN = _int_env("PIXEL_FORENSICS_MAX_MODULES_PER_RUN", 44, 1, 44)
    MAX_ACTIVE_ANALYSES = 1
    JSON_SORT_KEYS = False
