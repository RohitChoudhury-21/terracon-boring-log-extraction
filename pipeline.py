from pathlib import Path

from validation_input.validate_image import validate_image
from preprocessing.image_enhancement import preprocess_image
from ocr.glm_ocr import run_ocr
from postprocessing.text_cleanup import clean_text


def process_image(image_path: str) -> str:
    """
    Process one Terracon boring-log image.

    Flow:
        Input validation
        -> Lightweight preprocessing
        -> GLM-OCR (one inference)
        -> Conservative post-processing
        -> Clean raw text

    Args:
        image_path: Path to the boring-log image.

    Returns:
        Clean raw OCR text for handoff to the extraction layer.
    """

    # 1. Validate input image
    validation_result = validate_image(image_path)

    if not validation_result["valid"]:
        raise ValueError(
            f"Invalid input image: {validation_result['reason']}"
        )

    print("\n[1/4] Input validation passed.")

    # 2. Lightweight preprocessing
    preprocessed_path = preprocess_image(image_path)

    print("[2/4] Image preprocessing completed.")

    # 3. Run GLM-OCR once
    raw_text = run_ocr(preprocessed_path)

    print("[3/4] GLM-OCR completed.")

    # 4. Conservative post-processing
    final_text = clean_text(raw_text)

    print("[4/4] Post-processing completed.")

    return final_text


if __name__ == "__main__":
    # Local testing only.
    # Change this filename when testing a different image.
    test_image = Path("images") / "1-1037R-A.jpg"

    result = process_image(str(test_image))

    print("\n========== CLEAN RAW TEXT ==========\n")
    print(result)

    # Save only for local testing.
    output_path = Path("outputs") / f"{test_image.stem}_raw.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        result,
        encoding="utf-8",
    )

    print(f"\nSaved output to: {output_path}")