"""
Conservative post-processing for GLM-OCR raw output.

Only formatting cleanup is performed.
No spelling correction, rewriting, or field interpretation.
"""


def clean_text(raw_text: str) -> str:
    """
    Clean formatting noise from OCR output.

    The OCR content itself is not corrected or rewritten.
    """

    if not raw_text:
        return raw_text

    lines = raw_text.split("\n")

    cleaned_lines = [
        line.rstrip()
        for line in lines
        if line.strip() != ""
    ]

    return "\n".join(cleaned_lines)