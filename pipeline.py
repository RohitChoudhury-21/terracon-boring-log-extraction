from pathlib import Path
import json

from backend.app.core.config import settings

from backend.app.validation_input.validation_image import validate_image
from backend.app.preprocessing.image_enhancement import preprocess_image
from backend.app.ocr.glm_ocr import run_ocr
from backend.app.postprocessing.text_cleanup import (
    clean_text,
    split_sections,
    save_outputs,
)


def _build_sectioned_text(structured: dict) -> str:
    """
    Build sectioned plain text from split_sections output.

    Each section is written using an explicit ## heading.
    Tables are preserved as tab-separated rows.
    """

    lines = []

    for key, content in structured.items():

        if key == "other_sections" and isinstance(content, list):

            for section in content:

                section_name = section.get(
                    "name",
                    "OTHER"
                )

                lines.append(
                    f"## {section_name.upper()}"
                )
                lines.append("")

                for item in section.get(
                    "content",
                    []
                ):
                    lines.append(str(item))

                lines.append("")

            continue

        lines.append(
            f"## {key.upper()}"
        )
        lines.append("")

        if (
            isinstance(content, dict)
            and "rows" in content
        ):
            for row in content["rows"]:
                lines.append(str(row))

        elif isinstance(content, list):

            for item in content:
                lines.append(str(item))

        elif isinstance(content, str):

            lines.append(content)

        lines.append("")

    return "\n".join(lines)


def process_image(
    image_path: str,
    use_preprocessing: bool = False,
    output_stem: str | None = None,
    progress_callback=None,
):
    """
    Process one Terracon boring-log image.

    Pipeline:

        Image
          ↓
        Validation
          ↓
        Optional preprocessing
          ↓
        GLM-OCR
          ↓
        Raw OCR output
          ↓
        Text cleaning
          ↓
        Section detection
          ↓
        JSON + Markdown
    """

    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(
            f"Input image not found: {image_path}"
        )

    stem = output_stem or image_path.stem

    print()
    print("========================================")
    print(" TERRACON BORING LOG OCR PIPELINE")
    print("========================================")
    print()

    # ---------------------------------------------------------
    # 1. IMAGE VALIDATION
    # ---------------------------------------------------------

    if progress_callback:
        progress_callback("validating")

    validation_result = validate_image(
        str(image_path)
    )

    if not validation_result["valid"]:
        raise ValueError(
            "Invalid input image: "
            f"{validation_result['reason']}"
        )

    print(
        "[1/4] Image validation passed."
    )

    # ---------------------------------------------------------
    # 2. OPTIONAL PREPROCESSING
    # ---------------------------------------------------------

    ocr_image_path = image_path

    if use_preprocessing:

        if progress_callback:
            progress_callback("preprocessing")

        preprocessed_path = preprocess_image(
            str(image_path),
            output_dir=str(
                settings.PREPROCESSED_DIR
            ),
        )

        ocr_image_path = Path(
            preprocessed_path
        )

        print(
            "[2/4] Image preprocessing completed:"
        )
        print(
            f"      {ocr_image_path}"
        )

    else:

        print(
            "[2/4] Preprocessing skipped."
        )
        print(
            "      Using original image for OCR."
        )

    # ---------------------------------------------------------
    # 3. GLM-OCR
    # ---------------------------------------------------------

    if progress_callback:
        progress_callback("ocr")

    raw_text = run_ocr(
        str(ocr_image_path)
    )

    # ---------------------------------------------------------
    # SAVE RAW OCR TEXT
    # ---------------------------------------------------------

    settings.GLM_RAW_TEXT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    raw_text_path = (
        settings.GLM_RAW_TEXT_DIR
        / f"{stem}.txt"
    )

    raw_text_path.write_text(
        raw_text,
        encoding="utf-8",
    )

    # ---------------------------------------------------------
    # SAVE RAW OCR JSON
    # ---------------------------------------------------------

    settings.GLM_RAW_JSON_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    raw_json_path = (
        settings.GLM_RAW_JSON_DIR
        / f"{stem}.json"
    )

    raw_json = {
        "document_name": image_path.name,
        "ocr_model": settings.MODEL_NAME,
        "raw_text": raw_text,
    }

    raw_json_path.write_text(
        json.dumps(
            raw_json,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        "[3/4] GLM-OCR extraction completed."
    )

    print(
        f"      Raw text: {raw_text_path}"
    )

    print(
        f"      Raw JSON: {raw_json_path}"
    )

    # ---------------------------------------------------------
    # 4. POST-PROCESSING
    # ---------------------------------------------------------

    if progress_callback:
        progress_callback("postprocessing")

    cleaned_text = clean_text(
        raw_text
    )

    structured_data = split_sections(
        cleaned_text
    )

    # ---------------------------------------------------------
    # SAVE POSTPROCESSED RAW TEXT
    # ---------------------------------------------------------

    settings.POSTPROCESSED_RAW_TEXT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    sectioned_text = _build_sectioned_text(
        structured_data
    )

    postprocessed_text_path = (
        settings.POSTPROCESSED_RAW_TEXT_DIR
        / f"{stem}.txt"
    )

    postprocessed_text_path.write_text(
        sectioned_text,
        encoding="utf-8",
    )

    # ---------------------------------------------------------
    # SAVE JSON + MARKDOWN
    # USING EXISTING save_outputs()
    # ---------------------------------------------------------

    postprocessed_json_path = (
        settings.POSTPROCESSED_JSON_DIR
        / f"{stem}.json"
    )

    postprocessed_markdown_path = (
        settings.POSTPROCESSED_MARKDOWN_DIR
        / f"{stem}.md"
    )

    save_outputs(
        raw_text=raw_text,
        json_path=str(
            postprocessed_json_path
        ),
        markdown_path=str(
            postprocessed_markdown_path
        ),
        document_name=stem,
    )

    # ---------------------------------------------------------
    # FINALIZATION
    # ---------------------------------------------------------

    if progress_callback:
        progress_callback("finalizing")

    print(
        "[4/4] Post-processing completed."
    )

    print()
    print("Output files:")
    print(
        f"  Raw OCR text       : {raw_text_path}"
    )
    print(
        f"  Raw OCR JSON       : {raw_json_path}"
    )
    print(
        f"  Postprocessed text : {postprocessed_text_path}"
    )
    print(
        f"  Postprocessed JSON : {postprocessed_json_path}"
    )
    print(
        f"  Markdown           : {postprocessed_markdown_path}"
    )
    print()

    return {
        "document_name": image_path.name,
        "raw_text": raw_text,
        "cleaned_text": cleaned_text,
        "sectioned_text": sectioned_text,
        "structured_data": structured_data,

        "raw_text_path": str(
            raw_text_path
        ),

        "raw_json_path": str(
            raw_json_path
        ),

        "postprocessed_text_path": str(
            postprocessed_text_path
        ),

        "postprocessed_json_path": str(
            postprocessed_json_path
        ),

        "postprocessed_markdown_path": str(
            postprocessed_markdown_path
        ),

        "preprocessing_used": use_preprocessing,

        "ocr_image_path": str(
            ocr_image_path
        ),
    }


if __name__ == "__main__":

    # One-image-at-a-time testing

    image_name = "1-1189R.jpeg"

    image_path = (
        settings.UPLOAD_DIR
        / image_name
    )

    try:

        result = process_image(
            image_path=str(image_path),
            use_preprocessing=False,
        )

        print(
            "Pipeline completed successfully."
        )

    except Exception as exc:

        print()
        print(
            "Pipeline failed:"
        )
        print(exc)