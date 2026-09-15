from pathlib import Path
import time

from transformers import (
    AutoProcessor,
    GlmOcrForConditionalGeneration,
)


MODEL_ID = "zai-org/GLM-OCR"

DEFAULT_OCR_PROMPT = "Text Recognition:"


print("Loading GLM-OCR...")

processor = AutoProcessor.from_pretrained(
    MODEL_ID
)

model = GlmOcrForConditionalGeneration.from_pretrained(
    MODEL_ID,
    device_map="cpu",
)

print("Model loaded successfully!")


def run_ocr(
    image_path: str,
    prompt: str = DEFAULT_OCR_PROMPT
) -> str:
    """
    Run GLM-OCR on one boring-log image.

    Args:
        image_path: Path to the image.
        prompt: OCR prompt.
                Defaults to "Text Recognition:".

    Returns:
        Raw OCR text.
    """

    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(
            f"Image not found: {image_path}"
        )

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
                    "text": prompt,
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
    print(f"Prompt: {prompt}")

    start_time = time.time()

    try:
        output = model.generate(
            **inputs,
            max_new_tokens=1024,
            do_sample=False,
        )

    except Exception as exc:
        raise RuntimeError(
            f"GLM-OCR generation failed "
            f"on {image_path.name}: {exc}"
        ) from exc

    elapsed = time.time() - start_time

    print(
        f"OCR latency: {elapsed:.2f} seconds"
    )

    generated_tokens = output[0][
        inputs["input_ids"].shape[-1]:
    ]

    result = processor.decode(
        generated_tokens,
        skip_special_tokens=True,
    )

    result = result.strip()

    print(
        f"OCR characters: {len(result)}"
    )

    return result