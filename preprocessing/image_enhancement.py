from pathlib import Path
from PIL import Image, ImageEnhance


def preprocess_image(
    image_path: str,
    output_dir: str = "preprocessed",
) -> str:
    """
    Apply lightweight preprocessing before OCR.

    Steps:
    1. Convert to grayscale
    2. Apply slight contrast enhancement

    No resizing or heavy image processing is used.
    """

    image_path = Path(image_path)
    output_dir = Path(output_dir)

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as image:
        image = image.convert("L")
        image = ImageEnhance.Contrast(image).enhance(1.2)

        output_path = (
            output_dir / f"{image_path.stem}_preprocessed.png"
        )

        image.save(output_path)

    return str(output_path)