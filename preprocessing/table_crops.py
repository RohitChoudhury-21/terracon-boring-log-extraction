from pathlib import Path
from PIL import Image


def crop_tables(image_path: str, output_dir: str = "table_crops") -> dict:
    """
    Crop the two important tables from a Terracon boring log.

    Returns paths to:
    - Sample Data Table
    - Lithology / Sample Description Table
    """

    image_path = Path(image_path)
    output_dir = Path(output_dir)

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as image:

        # Sample Data Table
        sample_data = image.crop(
            (15, 135, 425, 680)
        )

        # Sample Description and Lithology Table
        lithology = image.crop(
            (425, 135, 805, 680)
        )

        sample_path = output_dir / "sample_data_table.png"
        lithology_path = output_dir / "lithology_table.png"

        sample_data.save(sample_path)
        lithology.save(lithology_path)

    return {
        "sample_data": str(sample_path),
        "lithology": str(lithology_path),
    }


if __name__ == "__main__":

    test_image = (
        r"C:\Users\avula\OneDrive\Desktop"
        r"\ocrtesting\images\1-1037R-A.jpg"
    )

    result = crop_tables(test_image)

    print("\n========== TABLE CROPS ==========\n")
    print(f"Sample Data Table: {result['sample_data']}")
    print(f"Lithology Table:   {result['lithology']}")