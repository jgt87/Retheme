"""Web app: upload -> extraction progress -> review/correction UI ->
download template package (zip).

Run with:  python -m pptx_template_tool.cli serve
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from ..extractor.extract import extract_template
from ..extractor.package import write_package, zip_package

app = FastAPI(title="Retheme")

WORK_ROOT = Path(tempfile.gettempdir()) / "pptx-template-tool"
WORK_ROOT.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 250 * 1024 * 1024  # generous cap for corporate decks
JOB_MAX_AGE_DAYS = 7
MAX_JOBS = 50  # bound in-memory extraction/apply state on a long-lived server

# job_id -> {"status", "step", "progress", "dir", "error"}
JOBS: dict[str, dict] = {}


def _cleanup_stale_jobs() -> None:
    """Remove job directories older than JOB_MAX_AGE_DAYS. Uploaded
    templates should not accumulate in the temp folder indefinitely."""
    cutoff = time.time() - JOB_MAX_AGE_DAYS * 86400
    try:
        for entry in WORK_ROOT.iterdir():
            if entry.is_dir() and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
    except OSError:
        pass


def _evict_oldest(registry: dict, keep: int, root_of) -> None:
    """Drop the oldest entries beyond `keep` and delete their work dirs, so a
    long-running server's memory and temp usage stay bounded. Relies on dict
    insertion order (oldest first); `root_of(job)` yields the dir to remove."""
    while len(registry) > keep:
        old_id = next(iter(registry))
        job = registry.pop(old_id)
        try:
            shutil.rmtree(root_of(job), ignore_errors=True)
        except Exception:
            pass


_cleanup_stale_jobs()


@app.middleware("http")
async def _reject_cross_origin_writes(request: Request, call_next):
    """The API is unauthenticated and local. Browsers will happily send
    cross-origin form POSTs to localhost, so reject state-changing requests
    whose Origin is some other website (CSRF). Non-browser clients (curl,
    the UI itself) send no Origin or a localhost one and pass through."""
    if request.method in ("POST", "PUT", "DELETE"):
        origin = request.headers.get("origin")
        if origin and not origin.startswith(("http://127.0.0.1",
                                             "http://localhost")):
            return JSONResponse({"detail": "cross-origin request rejected"},
                                status_code=403)
    return await call_next(request)


def _save_upload(upload: UploadFile, dest: Path) -> None:
    """Stream an upload to disk with a size cap (never buffer it in RAM)."""
    written = 0
    with dest.open("wb") as out:
        while chunk := upload.file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    413, f"file exceeds the {MAX_UPLOAD_BYTES // 2**20} MB "
                         f"upload limit")
            out.write(chunk)


def _safe_child(base: Path, candidate: Path) -> Path:
    """Resolve `candidate` and require it to be inside `base` (prefix string
    checks are bypassable via sibling dirs sharing a prefix)."""
    base = base.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise HTTPException(404, "not found")
    return resolved


def _run_extraction(job_id: str, pptx_path: Path, out_dir: Path):
    job = JOBS[job_id]

    def progress(step, frac):
        job["step"], job["progress"] = step, frac

    try:
        extract_template(pptx_path, out_dir, progress=progress)
        job["status"] = "done"
    except Exception as exc:  # surfaced to the UI
        job["status"] = "error"
        job["error"] = f"{type(exc).__name__}: {exc}"


@app.post("/api/extract")
async def start_extract(file: UploadFile):
    suffix = Path(file.filename or "t.pptx").suffix.lower()
    if suffix not in (".pptx", ".potx"):
        raise HTTPException(400, "Only .pptx and .potx files are supported")
    job_id = uuid.uuid4().hex[:12]
    job_dir = WORK_ROOT / job_id
    job_dir.mkdir(parents=True)
    src = job_dir / f"source{suffix}"
    _save_upload(file, src)
    out_dir = job_dir / "package"
    JOBS[job_id] = {"status": "running", "step": "queued", "progress": 0.0,
                    "dir": str(out_dir), "source": str(src), "error": None}
    # the package dir is a child of the job dir — evict removes the job dir
    _evict_oldest(JOBS, MAX_JOBS, lambda j: Path(j["dir"]).parent)
    threading.Thread(target=_run_extraction, args=(job_id, src, out_dir),
                     daemon=True).start()
    return {"job_id": job_id}


def _job(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    return job


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = _job(job_id)
    return {k: job[k] for k in ("status", "step", "progress", "error")}


@app.get("/api/jobs/{job_id}/manifest")
def get_manifest(job_id: str):
    job = _job(job_id)
    manifest_path = Path(job["dir"]) / "template.json"
    if not manifest_path.is_file():
        raise HTTPException(409, "extraction not finished")
    return JSONResponse(json.loads(manifest_path.read_text(encoding="utf-8")))


@app.put("/api/jobs/{job_id}/manifest")
async def put_manifest(job_id: str, corrections: dict):
    """Apply partial review corrections:
    {"colors": [{"theme_slot", "role"}...],
     "assets": [{"asset_id", "type"?, "position"?, "size"?, "needs_review"?}]}.
    Rewrites template.json AND regenerates template.md (they cannot diverge).
    """
    job = _job(job_id)
    pkg_dir = Path(job["dir"])
    manifest_path = pkg_dir / "template.json"
    if not manifest_path.is_file():
        raise HTTPException(409, "extraction not finished")
    if not isinstance(corrections, dict) or \
            not {"colors", "assets"} >= set(corrections.keys()):
        raise HTTPException(400, "corrections must contain only "
                                 "'colors' and/or 'assets'")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    by_slot = {c["theme_slot"]: c for c in manifest["colors"]}
    for corr in corrections.get("colors", []):
        color = by_slot.get(corr.get("theme_slot"))
        if color and corr.get("role"):
            color["role"] = corr["role"]
            color["confidence"] = "confirmed"

    geo = manifest["slide_geometry"]
    pct_base = {"x": geo["width_in"], "y": geo["height_in"],
                "width": geo["width_in"], "height": geo["height_in"]}
    by_id = {a["asset_id"]: a for a in manifest["assets"]}
    for corr in corrections.get("assets", []):
        asset = by_id.get(corr.get("asset_id"))
        if not asset:
            continue
        if corr.get("type"):
            asset["type"] = corr["type"]
        for field in ("position", "size"):
            if corr.get(field):
                merged = {**(asset[field] or {}), **corr[field]}
                # keep % coordinates in sync with corrected inches
                for dim, total in pct_base.items():
                    if f"{dim}_in" in merged and total:
                        merged[f"{dim}_pct"] = round(merged[f"{dim}_in"] / total, 4)
                asset[field] = merged
        if "needs_review" in corr:
            asset["needs_review"] = bool(corr["needs_review"])

    write_package(pkg_dir, manifest)  # rewrites both .json and .md
    return {"ok": True}


@app.get("/api/jobs/{job_id}/files/{path:path}")
def get_file(job_id: str, path: str):
    job = _job(job_id)
    target = _safe_child(Path(job["dir"]), Path(job["dir"]) / path)
    if not target.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(target)


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str):
    job = _job(job_id)
    pkg_dir = Path(job["dir"])
    if not (pkg_dir / "template.json").is_file():
        raise HTTPException(409, "extraction not finished")
    zip_path = pkg_dir.parent / "template-package.zip"
    zip_package(pkg_dir, zip_path)
    return FileResponse(zip_path, filename="template-package.zip")


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    job = _job(job_id)
    shutil.rmtree(Path(job["dir"]).parent, ignore_errors=True)
    JOBS.pop(job_id, None)
    return {"ok": True}


# ------------------------------------------------------------ apply flow
# Upload a content-only deck + a brandkit (an extraction job from this
# session, an uploaded template-package zip, or a package folder path).
# Result: HTML preview + on-demand native PPTX download.

import zipfile

from fastapi import Form

APPLY_JOBS: dict[str, dict] = {}


def _resolve_package(job_id: str | None, package_path: str | None,
                     zip_path: Path | None, work_dir: Path) -> Path:
    if job_id:
        job = JOBS.get(job_id)
        if not job or not (Path(job["dir"]) / "template.json").is_file():
            raise HTTPException(400, "extraction job not found or unfinished")
        return Path(job["dir"])
    if zip_path is not None:
        pkg_dir = work_dir / "package"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            total = 0
            for member in zf.infolist():  # guard traversal and zip bombs
                _safe_child(pkg_dir, pkg_dir / member.filename)
                total += member.file_size
                if total > MAX_UPLOAD_BYTES * 4:
                    raise HTTPException(413, "zip expands beyond size limit")
            zf.extractall(pkg_dir)
        if not (pkg_dir / "template.json").is_file():
            # zip may wrap everything in a single top-level folder
            candidates = [p for p in pkg_dir.iterdir() if p.is_dir()
                          and (p / "template.json").is_file()]
            if candidates:
                return candidates[0]
            raise HTTPException(400, "zip does not contain template.json")
        return pkg_dir
    if package_path:
        pkg_dir = Path(package_path.strip().strip('"'))
        if not (pkg_dir / "template.json").is_file():
            raise HTTPException(
                400, f"no template.json found in: {pkg_dir}")
        return pkg_dir
    raise HTTPException(400, "no brandkit supplied")


@app.post("/api/apply")
async def apply_brandkit(content_file: UploadFile,
                         job_id: str | None = Form(None),
                         package_path: str | None = Form(None),
                         package_zip: UploadFile | None = None):
    from ..application.content_extract import extract_content
    from ..application.generator import generate_html

    suffix = Path(content_file.filename or "d.pptx").suffix.lower()
    if suffix not in (".pptx", ".potx", ".ppsx"):
        raise HTTPException(400, "content deck must be .pptx/.potx/.ppsx")

    apply_id = uuid.uuid4().hex[:12]
    work_dir = WORK_ROOT / f"apply-{apply_id}"
    work_dir.mkdir(parents=True)
    deck_path = work_dir / f"content{suffix}"
    _save_upload(content_file, deck_path)

    zip_path = None
    if package_zip:
        zip_path = work_dir / "package.zip"
        _save_upload(package_zip, zip_path)
    pkg_dir = _resolve_package(job_id, package_path, zip_path, work_dir)

    job = {"dir": str(work_dir), "package": str(pkg_dir),
           "deck": str(deck_path), "status": "pending",
           "name": Path(content_file.filename or "deck").stem}
    APPLY_JOBS[apply_id] = job
    # an apply job's dir IS its work dir (parent is WORK_ROOT — never remove
    # that); a session brandkit lives under a separate extraction job dir, so
    # it is unaffected by evicting this apply job
    _evict_oldest(APPLY_JOBS, MAX_JOBS, lambda j: Path(j["dir"]))

    # surface brandkit-vs-deck decisions for the user to confirm before
    # applying (color families, foreign fonts, unmatched layouts, sizing)
    try:
        from ..application.conflicts import analyze_conflicts
        decisions = analyze_conflicts(pkg_dir, deck_path)
    except Exception:
        decisions = []
    if decisions:
        # the UI requests live previews via POST .../preview-draft with the
        # currently selected choices (pre-selected defaults included), so
        # every decision's effect is rendered server-side
        job["decisions"] = decisions
        return {"apply_id": apply_id, "decisions": decisions}
    return _execute_apply(apply_id, {})


def _validated_choices(body: dict) -> dict:
    choices = body.get("choices", {})
    if not isinstance(choices, dict) or \
            not all(isinstance(k, str) and isinstance(v, str)
                    for k, v in choices.items()):
        raise HTTPException(400, "choices must map decision ids to values")
    return choices


def _render_draft(job: dict, choices: dict) -> str:
    """Retheme the deck with `choices` and return the rendered HTML,
    cached per choice combination (toggling back and forth is instant)."""
    work_dir = Path(job["dir"])
    key = hashlib.sha1(json.dumps(choices, sort_keys=True)
                       .encode()).hexdigest()[:12]
    cache = work_dir / f"draft-{key}.html"
    lock = job.setdefault("draft_lock", threading.Lock())
    with lock:
        if cache.is_file():
            return cache.read_text(encoding="utf-8")
        from ..application.preview_render import render_deck_html
        from ..application.retheme import retheme_pptx
        draft = work_dir / f"draft-{key}.pptx"
        try:
            retheme_pptx(Path(job["package"]), Path(job["deck"]), draft,
                         choices=choices)
            html, _ = render_deck_html(Path(job["package"]), draft,
                                       job["name"])
        except FileNotFoundError:
            raise HTTPException(404, "no draft preview for this package")
        except Exception as exc:
            raise HTTPException(422, f"preview failed: "
                                     f"{type(exc).__name__}: {exc}")
        finally:
            draft.unlink(missing_ok=True)
        cache.write_text(html, encoding="utf-8")
        return html


@app.post("/api/apply/{apply_id}/preview-draft", response_class=HTMLResponse)
def apply_preview_draft(apply_id: str, body: dict):
    """Live decision preview rendered from the user's current choices."""
    choices = _validated_choices(body)
    return _render_draft(_apply_job(apply_id), choices)


@app.get("/api/apply/{apply_id}/preview-draft", response_class=HTMLResponse)
def apply_preview_draft_defaults(apply_id: str):
    """Back-compat for browsers still running a cached older UI (which
    GETs this path): render the preview with every decision's default."""
    job = _apply_job(apply_id)
    defaults = {d["id"]: d["default"] for d in job.get("decisions", [])
                if d.get("default")}
    return _render_draft(job, defaults)


def _execute_apply(apply_id: str, choices: dict) -> dict:
    from ..application.content_extract import extract_content
    from ..application.generator import generate_html

    job = _apply_job(apply_id)
    work_dir = Path(job["dir"])
    pkg_dir = Path(job["package"])
    deck_path = Path(job["deck"])
    try:
        content, warnings = extract_content(deck_path, pkg_dir)
        # retheme immediately: the PPTX export is the source of truth and
        # the preview is rendered FROM it, so the two cannot diverge
        try:
            from ..application.preview_render import render_deck_html
            from ..application.retheme import retheme_pptx
            branded = work_dir / "branded.pptx"
            gen_warnings = retheme_pptx(pkg_dir, deck_path, branded,
                                        choices=choices)
            html_doc, pv_warnings = render_deck_html(pkg_dir, branded,
                                                     job["name"])
            gen_warnings += pv_warnings
        except FileNotFoundError:
            # old package without embedded source: rebuild-from-text path
            html_doc, gen_warnings = generate_html(pkg_dir, content,
                                                   inline_assets=True)
    except Exception as exc:
        raise HTTPException(422, f"apply failed: {type(exc).__name__}: {exc}")

    (work_dir / "preview.html").write_text(html_doc, encoding="utf-8")
    (work_dir / "content.json").write_text(
        json.dumps(content, ensure_ascii=False), encoding="utf-8")
    # the per-choice draft previews were only needed during confirmation
    for stale in work_dir.glob("draft-*"):
        stale.unlink(missing_ok=True)
    job["status"] = "done"
    return {"apply_id": apply_id,
            "slides": len(content.get("slides", [])),
            "warnings": warnings + gen_warnings}


@app.post("/api/apply/{apply_id}/confirm")
async def apply_confirm(apply_id: str, body: dict):
    return _execute_apply(apply_id, _validated_choices(body))


def _apply_job(apply_id: str) -> dict:
    job = APPLY_JOBS.get(apply_id)
    if not job:
        raise HTTPException(404, "unknown apply job")
    return job


@app.get("/api/apply/{apply_id}/preview", response_class=HTMLResponse)
def apply_preview(apply_id: str):
    job = _apply_job(apply_id)
    return (Path(job["dir"]) / "preview.html").read_text(encoding="utf-8")


@app.get("/api/apply/{apply_id}/html")
def apply_html(apply_id: str):
    job = _apply_job(apply_id)
    return FileResponse(Path(job["dir"]) / "preview.html",
                        filename=f'{job["name"]}-branded.html')


@app.get("/api/apply/{apply_id}/pptx")
def apply_pptx(apply_id: str):
    job = _apply_job(apply_id)
    work_dir = Path(job["dir"])
    out_path = work_dir / "branded.pptx"
    try:
        # the apply step already rethemed the deck; serve that exact file
        # (it is also what the preview was rendered from)
        deck = job.get("deck")
        try:
            if out_path.is_file():
                return FileResponse(out_path,
                                    filename=f'{job["name"]}-branded.pptx')
            if not deck or not Path(deck).is_file():
                raise FileNotFoundError("no content deck stored")
            from ..application.retheme import retheme_pptx
            warnings = retheme_pptx(job["package"], deck, out_path)
        except FileNotFoundError:
            from ..application.pptx_generator import generate_pptx
            content = json.loads(
                (work_dir / "content.json").read_text(encoding="utf-8"))
            warnings = generate_pptx(job["package"], content, out_path)
    except Exception as exc:
        raise HTTPException(500, f"pptx generation failed: "
                                 f"{type(exc).__name__}: {exc}")
    headers = {"X-Warnings": str(len(warnings))}
    return FileResponse(out_path, filename=f'{job["name"]}-branded.pptx',
                        headers=headers)


@app.get("/", response_class=HTMLResponse)
def index():
    from .. import __version__
    html = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
    # single source of truth for the version shown in the header pill;
    # no-store so the UI can never go stale across tool upgrades
    return HTMLResponse(html.replace("{{version}}", __version__),
                        headers={"Cache-Control": "no-store"})
