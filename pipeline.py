import json
from pathlib import Path

from validation.validate_image import validate_image
from preprocessing.image_enhancement import preprocess_image
from ocr.glm_ocr import run_ocr
from postprocessing.text_cleanup import (
    clean_text,
    split_sections,
)


# ------------------------------------------------------------
# DIRECTORIES
# ------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

UPLOADS_DIR = BASE_DIR / "data" / "uploads"

PREPROCESSED_DIR = (
    BASE_DIR / "data" / "preprocessed"
)

OUTPUTS_DIR = (
    BASE_DIR / "data" / "outputs"
)

OCR_OUTPUT_DIR = (
    OUTPUTS_DIR / "ocr"
)

POSTPROCESSED_OUTPUT_DIR = (
    OUTPUTS_DIR / "postprocessed"
)

FINAL_OUTPUT_DIR = (
    OUTPUTS_DIR / "final"
)


# ------------------------------------------------------------
# CREATE DIRECTORIES
# ------------------------------------------------------------

PREPROCESSED_DIR.mkdir(
    parents=True,
    exist_ok=True
)

OCR_OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

POSTPROCESSED_OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

FINAL_OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ------------------------------------------------------------
# UNIQUE RUN NAME
# ------------------------------------------------------------

def get_unique_run_stem(
    image_stem: str
) -> str:

    existing_stems = set()

    directories = [
        PREPROCESSED_DIR,
        OCR_OUTPUT_DIR,
        POSTPROCESSED_OUTPUT_DIR,
        FINAL_OUTPUT_DIR,
    ]

    for directory in directories:

        if not directory.exists():
            continue

        for path in directory.iterdir():

            stem = path.stem

            if stem.endswith("_preprocessed"):
                stem = stem[
                    :-len("_preprocessed")
                ]

            existing_stems.add(stem)

    if image_stem not in existing_stems:
        return image_stem

    counter = 1

    while True:

        candidate = (
            f"{counter}.{image_stem}"
        )

        if candidate not in existing_stems:
            return candidate

        counter += 1


# ------------------------------------------------------------
# PROCESS ONE IMAGE
# ------------------------------------------------------------

def process_image(
    image_path: str,
    use_preprocessing: bool = False
):

    print("\n========================================")
    print(
        f" Processing: "
        f"{Path(image_path).name}"
    )
    print("========================================")

    image_path = Path(image_path)

    run_stem = get_unique_run_stem(
        image_path.stem
    )

    print(
        f"Run name: {run_stem}"
    )

    # --------------------------------------------------------
    # 1. IMAGE VALIDATION
    # --------------------------------------------------------

    validation_result = validate_image(
        str(image_path)
    )

    if not validation_result["valid"]:

        print(
            f"[ERROR] "
            f"{validation_result['reason']}"
        )

        return

    print(
        "[1/5] Image validation passed."
    )

    # --------------------------------------------------------
    # 2. IMAGE PREPROCESSING
    # --------------------------------------------------------

    if use_preprocessing:

        preprocessed_path = preprocess_image(
            str(image_path),
            output_dir=str(
                PREPROCESSED_DIR
            )
        )

        generated_preprocessed_path = (
            Path(preprocessed_path)
        )

        unique_preprocessed_path = (
            PREPROCESSED_DIR
            / f"{run_stem}_preprocessed.png"
        )

        if (
            generated_preprocessed_path
            != unique_preprocessed_path
        ):

            generated_preprocessed_path.rename(
                unique_preprocessed_path
            )

        preprocessed_path = str(
            unique_preprocessed_path
        )

        print(
            "[2/5] Image preprocessing completed."
        )

        print(
            f"Preprocessed: "
            f"{preprocessed_path}"
        )

    else:

        preprocessed_path = str(
            image_path
        )

        print(
            "[2/5] Preprocessing skipped "
            "(use_preprocessing=False)."
        )

    # --------------------------------------------------------
    # 3. GLM-OCR
    # --------------------------------------------------------

    raw_text = run_ocr(
        preprocessed_path
    )

    print(
        "[3/5] GLM-OCR extraction completed."
    )

    # --------------------------------------------------------
    # SAVE RAW OCR OUTPUT
    # --------------------------------------------------------

    raw_ocr_path = (
        OCR_OUTPUT_DIR
        / f"{run_stem}.txt"
    )

    raw_ocr_path.write_text(
        raw_text,
        encoding="utf-8"
    )

    print(
        f"Raw OCR saved: "
        f"{raw_ocr_path}"
    )

    # --------------------------------------------------------
    # 4. POST-PROCESSING
    # --------------------------------------------------------

    cleaned_text = clean_text(
        raw_text
    )

    sections = split_sections(
        cleaned_text
    )

    print(
        "[4/5] Post-processing completed."
    )

    # --------------------------------------------------------
    # SAVE POST-PROCESSED TEXT
    # --------------------------------------------------------

    postprocessed_path = (
        POSTPROCESSED_OUTPUT_DIR
        / f"{run_stem}.txt"
    )

    postprocessed_path.write_text(
        cleaned_text,
        encoding="utf-8"
    )

    print(
        f"Post-processed text saved: "
        f"{postprocessed_path}"
    )

    # --------------------------------------------------------
    # 5. FINAL JSON
    # --------------------------------------------------------

    final_json_path = (
        FINAL_OUTPUT_DIR
        / f"{run_stem}.json"
    )

    final_data = {
        "document_name": image_path.name,
        "sections": sections,
    }

    final_json_path.write_text(
        json.dumps(
            final_data,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print(
        "[5/5] Final JSON created."
    )

    print(
        f"Final JSON saved: "
        f"{final_json_path}"
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print("\n----------------------------------------")
    print("PROCESS SUMMARY")
    print("----------------------------------------")

    print(
        f"Input image      : "
        f"{image_path}"
    )

    print(
        f"Preprocessing    : "
        f"{'ON' if use_preprocessing else 'OFF'}"
    )

    print(
        f"Raw OCR          : "
        f"{raw_ocr_path}"
    )

    print(
        f"Post-processed   : "
        f"{postprocessed_path}"
    )

    print(
        f"Final JSON       : "
        f"{final_json_path}"
    )

    print("----------------------------------------")


# ------------------------------------------------------------
# FIND INPUT IMAGES
# ------------------------------------------------------------

def find_input_images():

    supported_formats = {
        ".jpg",
        ".jpeg",
        ".png",
    }

    if not UPLOADS_DIR.exists():
        return []

    return sorted(
        [
            path
            for path in UPLOADS_DIR.iterdir()
            if (
                path.is_file()
                and path.suffix.lower()
                in supported_formats
            )
        ]
    )


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    image_name = "1-1189R.jpeg"

    image_path = (
        UPLOADS_DIR / image_name
    )

    if not image_path.exists():

        print(
            f"Image not found: "
            f"{image_path}"
        )

        return

    try:

        process_image(
            str(image_path),
            use_preprocessing=False
        )

    except Exception as exc:

        print(
            f"\n[ERROR] Failed to process "
            f"{image_path.name}: {exc}"
        )

    print("\n========================================")
    print(" PROCESSING COMPLETED")
    print("========================================")


if __name__ == "__main__":
    main()