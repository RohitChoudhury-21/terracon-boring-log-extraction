from pathlib import Path
 
from PIL import Image, ImageEnhance
 
 
def preprocess_image(
    image_path: str,
    output_dir: str = "data/preprocessed",
) -> str:
    """
    Apply lightweight preprocessing before OCR.
 
    Steps:
        1. Convert image to grayscale
        2. Apply slight contrast enhancement
 
    The original image is not modified.
 
    Returns:
        Path to the preprocessed image.
    """
 
    image_path = Path(image_path)
    output_dir = Path(output_dir)
 
    if not image_path.exists():
        raise FileNotFoundError(
            f"Image not found: {image_path}"
        )
 
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
 
    with Image.open(image_path) as image:
 
        # Convert to grayscale
        image = image.convert("L")
 
        # Slight contrast enhancement
        image = ImageEnhance.Contrast(
            image
        ).enhance(1.2)
 
        output_path = (
            output_dir
            / f"{image_path.stem}_preprocessed.png"
        )
 
        image.save(output_path)
 
    return str(output_path)