from pathlib import Path

from PIL import Image


SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png"}


def validate_image(image_path: str) -> dict:
    """
    Validate a boring-log image before sending it to preprocessing/OCR.

    Returns a dictionary containing the validation result and image metadata.
    """

    path = Path(image_path)

    # 1. Check that the file exists
    if not path.exists():
        return {
            "valid": False,
            "reason": "Image file does not exist.",
        }

    # 2. Check that the file is actually a file
    if not path.is_file():
        return {
            "valid": False,
            "reason": "Path is not a file.",
        }

    # 3. Check supported image format
    if path.suffix.lower() not in SUPPORTED_FORMATS:
        return {
            "valid": False,
            "reason": f"Unsupported image format: {path.suffix}",
        }

    # 4. Try opening the image
    try:
        with Image.open(path) as image:
            image.verify()

        # Reopen after verify() so we can safely read metadata
        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format

    except Exception as exc:
        return {
            "valid": False,
            "reason": f"Image could not be opened: {exc}",
        }

    # 5. Check usable dimensions
    if width <= 0 or height <= 0:
        return {
            "valid": False,
            "reason": "Image has invalid dimensions.",
        }

    return {
        "valid": True,
        "path": str(path),
        "format": image_format,
        "width": width,
        "height": height,
    }


if __name__ == "__main__":

    test_image = (
        r"C:\Users\avula\OneDrive\Desktop"
        r"\ocrtesting\images\1-1037R-A.jpg"
    )

    result = validate_image(test_image)

    print("\n========== IMAGE VALIDATION ==========\n")

    for key, value in result.items():
        print(f"{key}: {value}")