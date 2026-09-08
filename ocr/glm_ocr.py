from pathlib import Path
 
from transformers import (
    AutoProcessor,
    GlmOcrForConditionalGeneration,
)
 
 
MODEL_ID = "zai-org/GLM-OCR"
 
OCR_PROMPT = "Transcribe all text and tables in this geotechnical boring log document accurately. Use Markdown tables (| Col 1 | Col 2 |) for tables and 'Key: Value' format for header fields."
 
 
print("Loading GLM-OCR...")
 
processor = AutoProcessor.from_pretrained(
    MODEL_ID
)
 
model = GlmOcrForConditionalGeneration.from_pretrained(
    MODEL_ID,
    device_map="cpu",
)
 
print("Model loaded successfully!")
 
 
def run_ocr(image_path: str) -> str:
    """
    Run GLM-OCR on one boring-log image.
 
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
                    "text": OCR_PROMPT,
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
 
    print(
        f"Running OCR on: {image_path.name}"
    )
 
    output = model.generate(
        **inputs,
        max_new_tokens=2048,
        do_sample=False,
    )
 
    generated_tokens = output[0][
        inputs["input_ids"].shape[-1]:
    ]
 
    result = processor.decode(
        generated_tokens,
        skip_special_tokens=True,
    )
 
    return result.strip()
 
 
if __name__ == "__main__":
 
    image_path = Path(
        "data/uploads/1-1037R-A.jpg"
    )
 
    result = run_ocr(
        str(image_path)
    )
 
    print(
        "\n========== GLM-OCR RESULT ==========\n"
    )
 
    print(result)