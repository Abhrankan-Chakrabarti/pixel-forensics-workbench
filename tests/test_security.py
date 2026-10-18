from io import BytesIO
import time
import uuid
from pathlib import Path

from PIL import Image

import app as application


def _png_bytes(size=(16, 12)):
    stream = BytesIO()
    Image.new("RGB", size, (12, 34, 56)).save(stream, format="PNG")
    return stream.getvalue()


def test_security_headers_and_static_pages():
    client = application.app.test_client()
    for path in ("/", "/about", "/privacy", "/terms", "/contact"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" in response.headers
        assert response.headers.get("Cache-Control", "").startswith("no-store")
    page = client.get("/about").get_data(as_text=True)
    assert "om ctf osint industries" in page
    assert "linkedin.com" not in page.lower()


def test_cross_origin_mutation_is_rejected():
    client = application.app.test_client()
    response = client.post("/api/analyze", json={}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_upload_and_absolute_expiry_cleanup(tmp_path, monkeypatch):
    client = application.app.test_client()
    monkeypatch.setitem(application.app.config, "UPLOAD_FOLDER", tmp_path / "uploads")
    monkeypatch.setitem(application.app.config, "RESULTS_FOLDER", tmp_path / "results")
    monkeypatch.setitem(application.app.config, "REPORTS_FOLDER", tmp_path / "reports")
    monkeypatch.setitem(application.app.config, "DATA_FOLDER", tmp_path / "data")
    monkeypatch.setitem(application.app.config, "SESSION_TTL_SECONDS", 600)
    response = client.post("/api/upload", data={"image": (BytesIO(_png_bytes()), "test.png")}, content_type="multipart/form-data")
    assert response.status_code == 201, response.get_data(as_text=True)
    data = response.get_json()
    sid = data["session_id"]
    assert (tmp_path / "uploads" / sid).exists()
    session = application.SESSIONS[sid]
    session.created_at = time.time() - 601
    for root in (tmp_path / "uploads", tmp_path / "results", tmp_path / "reports", tmp_path / "data" / "temp"):
        folder = root / sid
        if folder.exists():
            marker = folder / ".created_at"
            marker.write_text(str(time.time() - 601), encoding="ascii")
    application._cleanup_old_directories()
    assert sid not in application.SESSIONS
    assert not (tmp_path / "uploads" / sid).exists()


def test_malformed_image_rejected():
    client = application.app.test_client()
    response = client.post("/api/upload", data={"image": (BytesIO(b"not an image"), "fake.png")}, content_type="multipart/form-data")
    assert response.status_code == 400


def test_unknown_module_is_rejected_before_analysis():
    client = application.app.test_client()
    response = client.post("/api/analyze", json={"session_id": str(uuid.uuid4()), "modules": ["not-a-real-module"]})
    assert response.status_code == 400
