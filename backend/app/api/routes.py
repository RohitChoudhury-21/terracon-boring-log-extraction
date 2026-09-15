import json
import tempfile
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Form, Body, BackgroundTasks
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, FileResponse
from ..core.config import settings
from ..core.logging import get_logger
from ..extraction.field_extractor import extract_fields, extract_fields_from_json
from ..schemas.boring_log_schema import Document
from pipeline import process_image

logger = get_logger(__name__)

# In-memory progress tracker
PROGRESS: dict = {}

router = APIRouter()


# ---------- Manifest helpers ----------

def load_manifest() -> list:
    if not settings.MANIFEST_FILE.exists():
        return []
    try:
        with open(settings.MANIFEST_FILE, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception:
        return []

    # Prune entries whose files no longer exist on disk
    cleaned = []
    for entry in manifest:
        image_path = Path(entry.get("image_path", ""))
        if not image_path.exists():
            continue  # image is gone, drop the entry

        # Only require final_json if status is "completed"
        if entry.get("status") == "completed":
            final_json = Path(entry.get("final_json_path", ""))
            if not final_json.exists():
                continue

        cleaned.append(entry)
        # else: skip stale entry

    # If anything was pruned, persist the cleaned manifest
    if len(cleaned) != len(manifest):
        save_manifest(cleaned)

    return cleaned


def save_manifest(manifest: list):
    settings.MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(settings.MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def upsert_manifest_entry(entry: dict):
    manifest = load_manifest()
    existing_idx = next(
        (i for i, e in enumerate(manifest) if e.get("original_filename") == entry.get("original_filename")),
        None,
    )

    if existing_idx is not None:
        # Replace existing entry in place
        manifest[existing_idx] = entry
    else:
        manifest.append(entry)

    save_manifest(manifest)


# ---------- Endpoints ----------

@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "model": "zai-org/GLM-OCR",
        "model_loaded": True,
        "message": "OCR extraction service is running",
    }


@router.get("/progress/{upload_id}")
async def get_progress(upload_id: str):
    return {
        "upload_id": upload_id,
        "stage": PROGRESS.get(upload_id, "unknown"),
    }


@router.get("/uploads")
async def list_uploads():
    manifest = load_manifest()
    return {"uploads": manifest}


@router.get("/uploads/{upload_id}/image")
async def get_upload_image(upload_id: str):
    manifest = load_manifest()
    entry = next((e for e in manifest if e["id"] == upload_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Upload not found")
    image_path = Path(entry["image_path"])
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image file missing")
    return FileResponse(image_path)


@router.get("/uploads/{upload_id}/result")
async def get_upload_result(upload_id: str):
    manifest = load_manifest()
    entry = next((e for e in manifest if e["id"] == upload_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Upload not found")
    final_json_path = Path(entry.get("final_json_path") or entry.get("structured_json_path") or entry.get("raw_text_path") or "")
    raw_text_path = Path(entry.get("raw_text_path") or entry.get("postprocessed_text_path") or "")
    if not final_json_path.exists():
        raise HTTPException(status_code=404, detail="Final JSON file missing")
    with open(final_json_path, "r", encoding="utf-8") as f:
        structured_data = json.load(f)
    raw_text = raw_text_path.read_text(encoding="utf-8") if raw_text_path.exists() else None
    return {
        "id": upload_id,
        "original_filename": entry.get("original_filename"),
        "upload_timestamp": entry.get("upload_timestamp"),
        "structured_data": structured_data,
        "raw_text": raw_text,
    }


@router.put("/uploads/{upload_id}/result")
async def update_upload_result(upload_id: str, payload: dict = Body(...)):
    manifest = load_manifest()
    entry = next((e for e in manifest if e["id"] == upload_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Upload not found")
    final_json_path = Path(entry["final_json_path"])
    final_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(final_json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return {"status": "success", "message": "Saved successfully"}

@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    """Save the uploaded image and add it to the manifest immediately."""
    original_stem = Path(file.filename).stem
    image_ext = Path(file.filename).suffix or ".jpg"

    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    final_image_path = settings.UPLOAD_DIR / f"{original_stem}{image_ext}"
    contents = await file.read()
    final_image_path.write_bytes(contents)

    manifest_entry = {
        "id": original_stem,
        "original_filename": file.filename,
        "upload_timestamp": datetime.now().isoformat(),
        "image_path": str(final_image_path),
        "raw_text_path": str(settings.GLM_RAW_TEXT_DIR / f"{original_stem}.txt"),
        "postprocessed_text_path": str(settings.POSTPROCESSED_RAW_TEXT_DIR / f"{original_stem}.txt"),
        "final_json_path": str(settings.FINAL_JSON_DIR / f"{original_stem}.json"),
        "status": "uploaded",
    }
    upsert_manifest_entry(manifest_entry)

    return {"upload_id": original_stem, "status": "uploaded"}

@router.post("/extract/{upload_id}")
async def extract_from_image(upload_id: str, background_tasks: BackgroundTasks):
    """Start extraction for an already-uploaded image."""
    manifest = load_manifest()
    entry = next((e for e in manifest if e["id"] == upload_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Upload not found")

    image_path = entry["image_path"]
    if not Path(image_path).exists():
        raise HTTPException(status_code=404, detail="Image file missing")

    PROGRESS[upload_id] = "queued"

    def _run():
        try:
            def _progress_cb(stage: str):
                PROGRESS[upload_id] = stage

            result = process_image(
                        image_path,
                        use_preprocessing=False,
                        output_stem=upload_id,
                        progress_callback=_progress_cb,
                    )

            raw_text = result.get("cleaned_text") or result.get("raw_text") or ""
            postprocessed_json_path = result.get("postprocessed_json_path")

            try:
                if postprocessed_json_path and Path(postprocessed_json_path).exists():
                    doc = extract_fields_from_json(Path(postprocessed_json_path).read_text(encoding="utf-8"))
                else:
                    doc = extract_fields(raw_text)
            except Exception:
                doc = extract_fields(raw_text)

            settings.FINAL_JSON_DIR.mkdir(parents=True, exist_ok=True)
            final_json_path = settings.FINAL_JSON_DIR / f"{upload_id}.json"
            final_json_path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")

            # Update manifest status
            manifest = load_manifest()
            for e in manifest:
                if e["id"] == upload_id:
                    e["status"] = "completed"
                    e["final_json_path"] = str(final_json_path)
                    break
            save_manifest(manifest)

            PROGRESS[upload_id] = "completed"
        except Exception as e:
            logger.error(f"Extraction failed for {upload_id}: {e}")
            PROGRESS[upload_id] = "failed"

    background_tasks.add_task(_run)
    return {"upload_id": upload_id, "status": "processing"}

@router.delete("/uploads/{upload_id}")
async def delete_upload(upload_id: str):
    manifest = load_manifest()
    entry = next((e for e in manifest if e["id"] == upload_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Upload not found")

    # Delete all associated files
    for key in ["image_path", "raw_text_path", "postprocessed_text_path", "final_json_path"]:
        p = Path(entry.get(key, ""))
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
    # Also remove the other generated files
    stem = entry["id"]
    for extra in [
        settings.PREPROCESSED_DIR / f"{stem}.png",
        settings.GLM_RAW_JSON_DIR / f"{stem}.json",
        settings.POSTPROCESSED_JSON_DIR / f"{stem}.json",
        settings.POSTPROCESSED_MARKDOWN_DIR / f"{stem}.md",
    ]:
        if extra.exists():
            try:
                extra.unlink()
            except Exception:
                pass
    # Remove from manifest
    manifest = [e for e in manifest if e["id"] != upload_id]
    save_manifest(manifest)

    return {"status": "success", "message": "Upload deleted"}