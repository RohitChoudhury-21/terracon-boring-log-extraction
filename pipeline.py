from pathlib import Path
 
from validation_input.validate_image import validate_image
from preprocessing.image_enhancement import preprocess_image
from ocr.glm_ocr import run_ocr
from postprocessing.text_cleanup import save_outputs
 
 
DATA_DIR = Path("data")
 
UPLOADS_DIR = DATA_DIR / "uploads"
PREPROCESSED_DIR = DATA_DIR / "preprocessed"
 
JSON_OUTPUT_DIR = DATA_DIR / "outputs" / "json"
MARKDOWN_OUTPUT_DIR = DATA_DIR / "outputs" / "markdown"
 
 
def process_image(image_path: str):
    """
    Complete Terracon boring-log extraction pipeline.
 
    Flow:
 
        Image
          ↓
        Validation
          ↓
        Preprocessing
          ↓
        GLM-OCR
          ↓
        Post-processing
          ↓
        JSON + Markdown
    """
 
    image_path = Path(image_path)
 
    print("\n========================================")
    print(" TERRACON BORING LOG OCR PIPELINE")
    print("========================================\n")
 
    # --------------------------------------------------
    # 1. IMAGE VALIDATION
    # --------------------------------------------------
 
    validation_result = validate_image(
        str(image_path)
    )
 
    if not validation_result["valid"]:
        raise ValueError(
            f"Invalid input image: "
            f"{validation_result['reason']}"
        )
 
    print("[1/4] Image validation passed.")
 
    # --------------------------------------------------
    # 2. PREPROCESSING
    # --------------------------------------------------
 
    preprocessed_path = preprocess_image(
        str(image_path),
        output_dir=str(PREPROCESSED_DIR)
    )
 
    print(
        f"[2/4] Image preprocessing completed."
    )
 
    print(
        f"      Preprocessed image: "
        f"{preprocessed_path}"
    )
 
    # --------------------------------------------------
    # 3. GLM-OCR
    # --------------------------------------------------
 
    raw_text = run_ocr(
        preprocessed_path
    )
 
    print(
        "[3/4] GLM-OCR extraction completed."
    )
 
    # --------------------------------------------------
    # 4. POST-PROCESSING
    # --------------------------------------------------
 
    json_path = (
        JSON_OUTPUT_DIR
        / f"{image_path.stem}.json"
    )
 
    markdown_path = (
        MARKDOWN_OUTPUT_DIR
        / f"{image_path.stem}.md"
    )
 
    json_output, _ = save_outputs(
        raw_text=raw_text,
        json_path=str(json_path),
        markdown_path=str(markdown_path),
    )

    print(
        "[4/4] Post-processing completed."
    )

    print("\n----------------------------------------")
    print("OUTPUT FILES")
    print("----------------------------------------")

    print(
        f"JSON     : {json_path}"
    )

    print(
        f"Markdown : {markdown_path}"
    )

    print("\nPipeline completed successfully!")

    # Return the JSON string directly so Person B can parse it immediately
    return json_output
 
 
if __name__ == "__main__":
 
    image_path = (
        UPLOADS_DIR
        / "1-1037R-A.jpg"
    )
 
    process_image(
        str(image_path)
    )