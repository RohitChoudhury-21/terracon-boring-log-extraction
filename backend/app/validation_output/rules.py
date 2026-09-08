import re
from typing import Tuple, Optional


# ---------- Confidence levels ----------
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"


# ---------- Generic helpers ----------

def strip_and_clean(value: Optional[str]) -> Optional[str]:
    """Remove surrounding whitespace and normalize common OCR noise."""
    if value is None:
        return None
    value = value.strip()
    # Remove multiple spaces
    value = re.sub(r'\s+', ' ', value)
    # Replace unicode quotes with plain ones
    value = value.replace('“', '"').replace('”', '"')
    return value if value else None


def is_blank_or_unclear(value: Optional[str]) -> bool:
    """Return True if value is None, empty, or indicates illegibility."""
    if value is None:
        return True
    cleaned = value.strip().lower()
    if not cleaned:
        return True
    if cleaned in {"?", "??", "???", "illegible", "unclear", "not detected", "n/a", "-"}:
        return True
    return False


def assign_confidence(original: Optional[str], cleaned: Optional[str]) -> str:
    """Assign confidence based on whether the value was modified or looks uncertain."""
    if is_blank_or_unclear(original):
        return CONFIDENCE_LOW
    # If original had '?' or '~' or 'approx' indicate uncertainty
    if original and re.search(r'[?~*]|approx|~', original, re.IGNORECASE):
        return CONFIDENCE_MEDIUM
    # If cleaned was unchanged and not empty, high confidence
    if original == cleaned:
        return CONFIDENCE_HIGH
    # If cleaned differed slightly (e.g., stripped whitespace), still high
    if cleaned and original and cleaned in original:
        return CONFIDENCE_HIGH
    return CONFIDENCE_MEDIUM


# ---------- Depth validation (feet) ----------

def validate_depth(value: Optional[str]) -> Tuple[Optional[str], str]:
    """
    Validate a depth measurement (in feet).
    Expected format: number followed by ' or ft, e.g., "20'", "6.1 ft".
    Returns (cleaned_value, confidence).
    If value is blank/unclear, returns (None, low).
    If format is invalid, attempts correction if possible else returns (None, low).
    """
    if is_blank_or_unclear(value):
        return None, CONFIDENCE_LOW

    cleaned = strip_and_clean(value)

    # Reject if unit mark is inches (") because depth must be in feet
    if cleaned.endswith('"'):
        return None, CONFIDENCE_LOW

    # Accept formats like: 20', 20ft, 20 ft, 6.1', 6.1 ft
    match = re.match(r"^(\d+(?:\.\d+)?)\s*(?:ft|feet|'|’)?$", cleaned, re.IGNORECASE)
    if match:
        num = match.group(1)
        # Preserve original format if it had a quote or ft
        if "'" in cleaned or "ft" in cleaned.lower() or "feet" in cleaned.lower() or "’" in cleaned:
            return cleaned, assign_confidence(value, cleaned)
        # Otherwise append '
        return f"{num}'", assign_confidence(value, f"{num}'")
    else:
        # Maybe it's just a number without unit, assume feet
        if re.match(r'^\d+(\.\d+)?$', cleaned):
            return cleaned, CONFIDENCE_LOW
        else:
            # Invalid depth format; set to None
            return None, CONFIDENCE_LOW


# ---------- Recovery validation (inches) ----------

def validate_recovery(value: Optional[str]) -> Tuple[Optional[str], str]:
    """
    Validate recovery measurement (in inches).
    Expected format: number followed by " (double quote), e.g., '12"'.
    If value > 24 or clearly invalid, treat as low confidence or blank.
    """
    if is_blank_or_unclear(value):
        return None, CONFIDENCE_LOW

    cleaned = strip_and_clean(value)

    # Reject if unit mark is feet (') because recovery must be in inches
    if cleaned.endswith("'"):
        return None, CONFIDENCE_LOW

    # Accept number + double quote, e.g., 12"
    match = re.match(r'^(\d+(?:\.\d+)?)\s*(?:inches|inch|")?$', cleaned, re.IGNORECASE)
    if match:
        num = float(match.group(1))
        if num > 24:  # unreasonable for recovery; maybe misread
            return cleaned, CONFIDENCE_LOW
        if '"' in cleaned or "inch" in cleaned.lower():
            return cleaned, assign_confidence(value, cleaned)
        return cleaned, CONFIDENCE_LOW
    else:
        return cleaned, CONFIDENCE_LOW


# ---------- Blow count validation (integer, 0-100) ----------

def validate_blow_count(value: Optional[str]) -> Tuple[Optional[str], str]:
    """Validate a single blow count value (penetration record). Must be integer 0-100."""
    if is_blank_or_unclear(value):
        return None, CONFIDENCE_LOW

    cleaned = strip_and_clean(value)
    # Remove any non-numeric except maybe ' ' or '-'
    cleaned = re.sub(r'[^\d]', '', cleaned)
    if not cleaned:
        return None, CONFIDENCE_LOW
    num = int(cleaned)
    if 0 <= num <= 100:
        return str(num), assign_confidence(value, str(num))
    else:
        return None, CONFIDENCE_LOW


# ---------- Sample type validation (SS, ST, etc.) ----------

def validate_sample_type(value: Optional[str]) -> Tuple[Optional[str], str]:
    """Validate sample type, typically 'SS' (split spoon) or 'ST' (shelby tube)."""
    if is_blank_or_unclear(value):
        return None, CONFIDENCE_LOW

    cleaned = strip_and_clean(value).upper()
    # Remove any parentheses or circles that OCR might produce
    cleaned = re.sub(r'[()\[\]{}]', '', cleaned)
    # Common types: SS, ST, SW, SB, etc. We'll keep if it's 2-3 letters
    if re.fullmatch(r'[A-Z]{1,3}', cleaned):
        return cleaned, assign_confidence(value, cleaned)
    else:
        return cleaned, CONFIDENCE_LOW


# ---------- Checkbox parsing ----------

def validate_checkbox(value: Optional[str]) -> str:
    """
    Normalize checkbox state.
    Returns 'CHECKED', 'UNCHECKED', or 'UNKNOWN' (if blank/unclear).
    """
    if is_blank_or_unclear(value):
        return "UNKNOWN"
    cleaned = value.strip().lower()
    if cleaned in {"x", "checked", "yes", "true", "1", "[x]", "[✓]"}:
        return "CHECKED"
    elif cleaned in {"", "unchecked", "no", "false", "0", "[ ]"}:
        return "UNCHECKED"
    else:
        return "UNKNOWN"


# ---------- Date/time validation (simple) ----------

def validate_date(value: Optional[str]) -> Tuple[Optional[str], str]:
    """Validate date in formats like '8-6-24' or '08/06/2024'."""
    if is_blank_or_unclear(value):
        return None, CONFIDENCE_LOW
    cleaned = strip_and_clean(value)
    # Accept common formats
    if re.match(r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$', cleaned):
        return cleaned, assign_confidence(value, cleaned)
    else:
        return cleaned, CONFIDENCE_LOW


def validate_time(value: Optional[str]) -> Tuple[Optional[str], str]:
    """Validate time in formats like '9:20 AM' or '09:20'."""
    if is_blank_or_unclear(value):
        return None, CONFIDENCE_LOW
    cleaned = strip_and_clean(value)
    # Accept H:MM AM/PM or HH:MM
    if re.match(r'^\d{1,2}:\d{2}(?:\s?[APap]\.?[Mm]\.?)?$', cleaned):
        return cleaned, assign_confidence(value, cleaned)
    else:
        return cleaned, CONFIDENCE_LOW