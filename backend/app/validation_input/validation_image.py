from pathlib import Path
from PIL import Image


SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png"}


def validate_image(image_path: str) -> dict:
    """
    Validate the input boring-log image.

    Checks:
    - File exists
    - Path is a file
    - Supported image format
    - Image can be opened
    - Valid dimensions
    """

    path = Path(image_path)

    if not path.exists():
        return {
            "valid": False,
            "reason": "Image file does not exist."
        }

    if not path.is_file():
        return {
            "valid": False,
            "reason": "Path is not a file."
        }

    if path.suffix.lower() not in SUPPORTED_FORMATS:
        return {
            "valid": False,
            "reason": f"Unsupported image format: {path.suffix}"
        }

    try:
        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format

    except Exception as exc:
        return {
            "valid": False,
            "reason": f"Image could not be opened: {exc}"
        }

    if width <= 0 or height <= 0:
        return {
            "valid": False,
            "reason": "Image has invalid dimensions."
        }

    return {
        "valid": True,
        "path": str(path),
        "format": image_format,
        "width": width,
        "height": height,
    }