"""Security/robustness regression tests for the web app:
path containment, CSRF origin rejection, manifest-corrections validation,
and the upload size cap."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pptx import Presentation

from pptx_template_tool.webapp import app as webapp
from pptx_template_tool.webapp.app import app

client = TestClient(app)


def test_safe_child_blocks_sibling_prefix(tmp_path):
    base = tmp_path / "job"
    evil = tmp_path / "jobevil"          # shares the string prefix
    base.mkdir(), evil.mkdir()
    (evil / "secret.txt").write_text("x")
    ok = webapp._safe_child(base, base / "inside.txt")
    assert ok.name == "inside.txt"
    with pytest.raises(HTTPException):
        webapp._safe_child(base, base / ".." / "jobevil" / "secret.txt")


def test_cross_origin_writes_rejected():
    r = client.post("/api/extract",
                    files={"file": ("t.pptx", b"x")},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    # localhost origins and no-Origin clients still pass the middleware
    r = client.post("/api/extract",
                    files={"file": ("bad.txt", b"x")},
                    headers={"Origin": "http://127.0.0.1:8000"})
    assert r.status_code == 400  # rejected for extension, not origin


def test_put_manifest_rejects_full_replacement(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "template.json").write_text(json.dumps(
        {"colors": [], "assets": [], "layouts": [],
         "slide_geometry": {"width_in": 10, "height_in": 7.5,
                            "aspect_ratio": "4:3"},
         "fonts": {}, "grid": {}}), encoding="utf-8")
    webapp.JOBS["sec1"] = {"status": "done", "dir": str(pkg), "error": None,
                           "step": "", "progress": 1.0}
    r = client.put("/api/jobs/sec1/manifest",
                   json={"slide_geometry": {}, "assets": [], "colors": [],
                         "layouts": []})
    assert r.status_code == 400
    r = client.put("/api/jobs/sec1/manifest", json={"colors": [], "assets": []})
    assert r.status_code == 200


def test_upload_size_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(webapp, "MAX_UPLOAD_BYTES", 1024)
    buf = io.BytesIO()
    Presentation().save(buf)          # a real pptx, > 1 KB
    r = client.post("/api/extract",
                    files={"file": ("big.pptx", buf.getvalue())})
    assert r.status_code == 413
