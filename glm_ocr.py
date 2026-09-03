from pathlib import Path

from transformers import AutoProcessor, GlmOcrForConditionalGeneration


MODEL_ID = "zai-org/GLM-OCR"


print("Loading GLM-OCR...")

processor = AutoProcessor.from_pretrained(MODEL_ID)

model = GlmOcrForConditionalGeneration.from_pretrained(
    MODEL_ID,
    device_map="cpu",
)

print("Model loaded successfully!")


def run_ocr(image_path: str) -> str:
    """
    Run GLM-OCR on a single boring-log image.

    Args:
        image_path: Path to the input image.

    Returns:
        Extracted OCR text.
    """

    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "url": str(image_path),
                },
                {
                    "type": "text",
                    "text": "Text Recognition:",
                },
            ],
        }
    ]

    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    )

    print(f"Running OCR on: {image_path.name}")

    output = model.generate(
        **inputs,
        max_new_tokens=1024,
    )

    generated_tokens = output[0][inputs["input_ids"].shape[-1]:]

    result = processor.decode(
        generated_tokens,
        skip_special_tokens=True,
    )

    return result


if __name__ == "__main__":

    image_path = r"C:\Users\avula\OneDrive\Desktop\ocrtesting\images\1-1037R-A.jpg"

    result = run_ocr(image_path)

    output_file = Path("outputs") / "1-1037R-A_ocr.txt"
    output_file.write_text(result, encoding="utf-8")

    print("\n========== GLM-OCR RESULT ==========\n")
    print(result)

    print(f"\nSaved OCR output to: {output_file}")
    
    print("\n" + "=" * 70)
    print("All images processed successfully!")
    print("=" * 70)