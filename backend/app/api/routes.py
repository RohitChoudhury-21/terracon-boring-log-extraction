import tempfile
import json
import shutil
import uuid
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Form, Body
from fastapi.responses import JSONResponse, FileResponse
from typing import Optional
from pipeline import process_image
from ..extraction.field_extractor import extract_fields, extract_fields_from_json
from ..schemas.boring_log_schema import Document
from ..core.logging import get_logger
from ocr.glm_ocr import model, processor, MODEL_ID
from ..core.config import settings

logger = get_logger(__name__)

# In-memory progress tracker: upload_id -> current stage
PROGRESS: dict = {}

def load_manifest() -> list:
    if not settings.MANIFEST_FILE.exists():
        return []
    try:
        with open(settings.MANIFEST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_manifest(manifest: list):
    settings.MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(settings.MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

def upsert_manifest_entry(entry: dict):
    manifest = load_manifest()
    existing_idx = next(
        (i for i, e in enumerate(manifest) if e.get("original_filename") == entry.get("original_filename")),
        None
    )

    if existing_idx is not None:
        old_entry = manifest[existing_idx]
        # Clean up old files on disk if their paths differ from the new ones
        for key in ["image_path", "raw_text_path", "structured_json_path"]:
            old_file = old_entry.get(key)
            new_file = entry.get(key)
            if old_file and old_file != new_file:
                try:
                    p = Path(old_file)
                    if p.exists():
                        p.unlink()
                except Exception as cleanup_err:
                    logger.warning(f"Could not remove old file {old_file}: {cleanup_err}")
        # Replace existing entry in place
        manifest[existing_idx] = entry
    else:
        manifest.append(entry)

    save_manifest(manifest)

router = APIRouter()

@router.get("/health")
async def health_check():
    model_loaded = model is not None and processor is not None
    return {
        "status": "healthy" if model_loaded else "unhealthy",
        "model": MODEL_ID,
        "model_loaded": model_loaded,
        "message": "OCR extraction service is running"
    }

@router.get("/progress/{upload_id}")
async def get_progress(upload_id: str):
    """Return the current processing stage for a given upload ID."""
    return {
        "upload_id": upload_id,
        "stage": PROGRESS.get(upload_id, "unknown"),
    }

@router.get("/uploads")
async def list_uploads():
    """Return manifest entries for all processed uploads."""
    manifest = load_manifest()
    return {"uploads": manifest}


@router.get("/uploads/{upload_id}/image")
async def get_upload_image(upload_id: str):
    """Serve the persisted image for a given upload ID."""
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
    """Return the saved structured JSON and raw text for a given upload."""
    manifest = load_manifest()
    entry = next((e for e in manifest if e["id"] == upload_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Upload not found")
    structured_path = Path(entry["structured_json_path"])
    raw_path = Path(entry["raw_text_path"])
    if not structured_path.exists():
        raise HTTPException(status_code=404, detail="Structured JSON file missing")
    with open(structured_path, "r", encoding="utf-8") as f:
        structured_data = json.load(f)
    raw_text = raw_path.read_text(encoding="utf-8") if raw_path.exists() else None
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
    structured_path = Path(entry["structured_json_path"])
    structured_path.parent.mkdir(parents=True, exist_ok=True)
    with open(structured_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return {"status": "success", "message": "Saved successfully"}


@router.post("/extract", response_model=Document)
async def extract_from_image(file: UploadFile = File(...), upload_id: Optional[str] = Form(None)):
    logger.info("Received extract request")
    logger.info(f"Received image upload: {file.filename}")

    # Generate or use provided upload_id
    if not upload_id:
        upload_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    PROGRESS[upload_id] = "uploading"
    logger.info(f"Received image upload: {file.filename} (ID: {upload_id})")

    # Generate a unique stem based on original filename + timestamp
    original_stem = Path(file.filename).stem
    unique_stem = f"{original_stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Save uploaded file to a temporary location for processing
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = Path(tmp.name)

    try:
        PROGRESS[upload_id] = "processing"
        logger.info("Calling process_image")
        # Step 1: Get raw text from image (Person A's OCR pipeline)
        raw_result = process_image(str(tmp_path))
        if isinstance(raw_result, dict):
            if "markdown" in raw_result and Path(raw_result["markdown"]).exists():
                raw_text = Path(raw_result["markdown"]).read_text(encoding="utf-8")
            elif "json" in raw_result and Path(raw_result["json"]).exists():
                raw_text = Path(raw_result["json"]).read_text(encoding="utf-8")
            else:
                raw_text = str(raw_result)
        else:
            raw_text = str(raw_result)
        logger.debug(f"Raw text length: {len(raw_text)} chars")

        # Step 2: Extract fields (try JSON first, then text)
        PROGRESS[upload_id] = "extracting"
        try:
            doc = extract_fields_from_json(raw_text)
            logger.info("Extraction successful (JSON direct parse)")
        except Exception as json_err:
            logger.warning(f"JSON parse failed, falling back to text parsing: {json_err}")
            doc = extract_fields(raw_text)
            logger.info("Extraction successful (text section parse)")

        # Step 3: Save artifacts using the same unique_stem
        PROGRESS[upload_id] = "finalizing"
        upload_dir = settings.UPLOAD_DIR
        raw_dir = settings.RAW_TEXT_DIR
        structured_dir = settings.STRUCTURED_DIR

        upload_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        structured_dir.mkdir(parents=True, exist_ok=True)

        # Save image (copy from temp to permanent)
        image_ext = Path(file.filename).suffix or ".jpg"
        final_image_path = upload_dir / f"{unique_stem}{image_ext}"
        shutil.copy2(tmp_path, final_image_path)

        # Save raw text (postprocessed)
        raw_path = raw_dir / f"{unique_stem}.txt"
        raw_path.write_text(raw_text, encoding="utf-8")

        # Save structured JSON
        structured_path = structured_dir / f"{unique_stem}.json"
        with open(structured_path, "w", encoding="utf-8") as f:
            json.dump(doc.model_dump(), f, indent=2, default=str)

        # Update manifest
        manifest_entry = {
            "id": unique_stem,
            "original_filename": file.filename,
            "upload_timestamp": datetime.now().isoformat(),
            "image_path": str(final_image_path),
            "raw_text_path": str(raw_path),
            "structured_json_path": str(structured_path),
            "status": "completed",
        }
        upsert_manifest_entry(manifest_entry)

        logger.info(f"Saved artifacts for {unique_stem}")
        PROGRESS[upload_id] = "completed"

        return doc

    except Exception as e:
        PROGRESS[upload_id] = "failed"
        logger.error(f"Extraction failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {str(e)}"
        )
    finally:
        # Clean up the temporary file if it still exists (we already copied)
        try:
            tmp_path.unlink(missing_ok=True)
        except PermissionError:
            logger.warning(f"Could not delete temp file {tmp_path}")