import re
import html
import json
from typing import List, Optional, Dict, Any, Tuple
import difflib

from ..schemas.boring_log_schema import (
    Document, Section, Header, BoringAdvancement, AdvancementRow,
    SampleDataRow, LithologyRow, SurfaceCoverThickness,
    WaterLevelObservations, BoringAbandonment, BoringLog
)
from ..validation_output import rules
from ..core.logging import get_logger

logger = get_logger(__name__)


# ---------- JSON direct parsing ----------

def extract_fields_from_json(raw_json_text: str) -> Document:
    """
    Parse a JSON string into a Document.
    If old BoringLog schema is detected, convert it to Document.
    """
    cleaned = raw_json_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.lstrip("`").lstrip("json").strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    data = json.loads(cleaned)

    # If new Document schema
    if "sections" in data:
        return Document(**data)

    # Else assume legacy BoringLog; convert
    return legacy_boringlog_to_document(data)


def legacy_boringlog_to_document(data: dict) -> Document:
    """Convert old BoringLog dict to generic Document."""
    sections: List[Section] = []

    # Header
    if data.get("header"):
        fields = {k: v for k, v in data["header"].items() if v is not None}
        sections.append(Section(name="Header", type="key_value", fields=fields))

    # Boring Advancement
    if data.get("boring_advancement"):
        adv = data["boring_advancement"]
        fields = {
            "Start Date": adv.get("Start_Date"),
            "Start Time": adv.get("Start_Time"),
            "Finish Date": adv.get("Finish_Date"),
            "Finish Time": adv.get("Finish_Time"),
        }
        rows = []
        for row in adv.get("advancement_rows", []):
            rows.append({
                "Depth": row.get("Depth"),
                "Method": row.get("Method"),
            })
        if rows:
            sections.append(Section(name="Boring Advancement", type="table",
                                    columns=["Depth", "Method"], rows=rows))
        else:
            sections.append(Section(name="Boring Advancement", type="key_value", fields=fields))

    # Sample Data Table
    if data.get("sample_data_table"):
        rows = []
        for row in data["sample_data_table"]:
            rows.append({
                "No.": row.get("sample_no"),
                "From": row.get("from_depth"),
                "To": row.get("to_depth"),
                "Type": row.get("type"),
                "Time": row.get("collection_time"),
                "Blow 1": row.get("blow_1"),
                "Blow 2": row.get("blow_2"),
                "Blow 3": row.get("blow_3"),
                "Blow 4": row.get("blow_4"),
                "Recovery": row.get("recovery"),
            })
        columns = ["No.", "From", "To", "Type", "Time", "Blow 1", "Blow 2", "Blow 3", "Blow 4", "Recovery"]
        sections.append(Section(name="Sample Data Table", type="table",
                                columns=columns, rows=rows))

    # Lithology Data Table
    if data.get("lithology_data_table"):
        rows = []
        for row in data["lithology_data_table"]:
            rows.append({
                "Depth From": row.get("depth_from"),
                "Depth To": row.get("depth_to"),
                "Description": row.get("description"),
            })
        columns = ["Depth From", "Depth To", "Description"]
        sections.append(Section(name="Lithology / Sample Description Table", type="table",
                                columns=columns, rows=rows))

    # Surface Cover
    if data.get("surface_cover_thickness"):
        fields = {k: v for k, v in data["surface_cover_thickness"].items() if v is not None}
        sections.append(Section(name="Surface Cover & Thickness", type="key_value", fields=fields))

    # Water Level Observations
    if data.get("water_level_observations"):
        fields = {k: v for k, v in data["water_level_observations"].items() if v is not None}
        sections.append(Section(name="Water Level Observations", type="key_value", fields=fields))

    # Boring Abandonment
    if data.get("boring_abandonment"):
        fields = {k: v for k, v in data["boring_abandonment"].items() if v is not None}
        sections.append(Section(name="Boring Abandonment", type="key_value", fields=fields))

    # Additional Remarks
    if data.get("additional_remarks"):
        sections.append(Section(name="Additional Remarks", type="raw_text",
                                text=data["additional_remarks"]))

    # Sheet Info
    if data.get("sheet") or data.get("sheet_of"):
        fields = {"Sheet": data.get("sheet"), "of": data.get("sheet_of")}
        sections.append(Section(name="Sheet Info", type="key_value", fields=fields))

    return Document(sections=sections)


# ---------- Helpers to split raw text ----------

def clean_html_entities(text: str) -> str:
    """Unescape HTML entities and strip unwanted tags."""
    if not text:
        return ""
    text = html.unescape(text)
    if "<table" in text.lower() or "<tr" in text.lower() or "<td" in text.lower():
        text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
        lines = []
        for raw_line in text.splitlines():
            if "<td" in raw_line.lower() or "<th" in raw_line.lower():
                cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', raw_line, flags=re.DOTALL | re.IGNORECASE)
                if not cells:
                    clean_l = re.sub(r'<[^>]+>', ' ', raw_line).strip()
                    if clean_l:
                        lines.append(clean_l)
                elif len(cells) == 1:
                    clean_cell = re.sub(r'<[^>]+>', ' ', cells[0]).strip()
                    if clean_cell:
                        lines.append(clean_cell)
                else:
                    clean_cells = [re.sub(r'<[^>]+>', ' ', c).strip() for c in cells]
                    lines.append("\t".join(clean_cells))
            else:
                clean_l = re.sub(r'<[^>]+>', ' ', raw_line).strip()
                if clean_l:
                    lines.append(clean_l)
        text = "\n".join(lines)
    else:
        text = re.sub(r'<[^>]+>', ' ', text)
    return text


def extract_key_value_pairs(text_block: str) -> Dict[str, str]:
    """
    Extract key-value pairs accurately:
    1. Handles multiple Key: Value pairs on one line.
    2. Handles consecutive empty keys.
    3. Prevents colons inside parentheses from creating fake keys.
    """
    pairs = {}
    clean_block = clean_html_entities(text_block)

    for line in clean_block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        colon_indices = []
        paren_depth = 0
        for idx, ch in enumerate(line):
            if ch in '([{':
                paren_depth += 1
            elif ch in ')]}':
                paren_depth = max(0, paren_depth - 1)
            elif ch == ':' and paren_depth == 0:
                colon_indices.append(idx)

        if not colon_indices:
            continue

        keys_info = []
        last_col = -1
        for i, col_idx in enumerate(colon_indices):
            seg_start = last_col + 1 if last_col != -1 else 0
            seg = line[seg_start:col_idx]

            words = seg.split()
            if not words:
                key = ""
                k_start = col_idx
            else:
                key_words = []
                for w in reversed(words):
                    clean_w = w.strip('.,()/#-')
                    if key_words and (clean_w.isdigit() or re.match(r'^\d+[\'"]?$', clean_w) or re.match(r'^\d+[-/]\d+', clean_w)):
                        break
                    if len(key_words) >= 2 and w.lower() not in {"&", "and", "of", "level", "cover"}:
                        break
                    key_words.insert(0, w)
                    if len(words) > len(key_words) and (words[-len(key_words)-1].isdigit() or not words[-len(key_words)-1][0].isupper()):
                        break

                key = " ".join(key_words).strip()
                k_start = col_idx - len(seg) + seg.rfind(key) if key in seg else col_idx

            keys_info.append({'key': key, 'k_start': k_start, 'col_idx': col_idx})
            last_col = col_idx

        for i in range(len(keys_info)):
            k = keys_info[i]['key']
            val_start = keys_info[i]['col_idx'] + 1
            val_end = keys_info[i+1]['k_start'] if i + 1 < len(keys_info) else len(line)
            val = line[val_start:val_end].strip().strip('-').strip()
            if k and not (k.isdigit() and len(k) <= 2):
                pairs[k] = val

    return pairs


def normalize_key(key: str) -> str:
    key = key.strip().lower()
    key = re.sub(r'[\s.:]+', '_', key)
    key = key.strip('_')
    key = re.sub(r'_+', '_', key)
    return key


def split_sections(text: str) -> Dict[str, str]:
    text = clean_html_entities(text)
    marker_patterns = {
        "header": r"^##\s*HEADER\s*$",
        "boring_advancement": r"^##\s*BORING_ADVANCEMENT\s*$",
        "sample_data_table": r"^##\s*SAMPLE_DATA_TABLE\s*$",
        "lithology_data_table": r"^##\s*LITHOLOGY_DATA_TABLE\s*$",
        "surface_cover_thickness": r"^##\s*SURFACE_COVER_THICKNESS\s*$",
        "water_level_observations": r"^##\s*WATER_LEVEL_OBSERVATIONS\s*$",
        "boring_abandonment": r"^##\s*BORING_ABANDONMENT\s*$",
        "additional_remarks": r"^##\s*ADDITIONAL_REMARKS\s*$",
        "sheet_info": r"^##\s*SHEET_INFO\s*$",
    }

    sections = {}
    current_section = None
    current_lines = []
    marker_found = False

    for line in text.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue

        matched_section = None
        for sec, pattern in marker_patterns.items():
            if re.match(pattern, line_stripped, re.IGNORECASE):
                matched_section = sec
                marker_found = True
                break

        if not matched_section and not marker_found:
            keyword_patterns = {
                "boring_advancement": r"(boring\s*advancement|advancement|start\s*date|finish\s*date)",
                "sample_data_table": r"^\s*sample\b|penetration\s*record",
                "lithology_data_table": r"(sample\s*description\s*and\s*lithology|lithology)",
                "surface_cover_thickness": r"(surface\s*cover\s*&\s*thickness|surface\s*cover)",
                "water_level_observations": r"(water\s*level\s*observations|water\s*level)",
                "boring_abandonment": r"(boring\s*abandonment|abandonment)",
                "additional_remarks": r"(additional\s*remarks)",
                "sheet_info": r"(sheet\s*:\s*\d+\s+of\s+\d+)"
            }
            for sec, pattern in keyword_patterns.items():
                if re.search(pattern, line_stripped, re.IGNORECASE):
                    matched_section = sec
                    break

        if matched_section:
            if current_section and current_lines:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = matched_section
            current_lines = []
        else:
            if current_section:
                current_lines.append(line)
            else:
                current_section = "header"
                current_lines.append(line)

    if current_section and current_lines:
        sections[current_section] = "\n".join(current_lines).strip()

    return sections


# ---------- Generic Section Builders ----------

def _is_table_section(lines: List[str]) -> bool:
    """Heuristic: section is a table if it has consistent tabs or pipe delimiters."""
    if len(lines) < 2:
        return False
    tab_or_pipe = sum(1 for l in lines if "\t" in l or "|" in l)
    return tab_or_pipe >= max(1, len(lines) * 0.4)


def _parse_table(lines: List[str]) -> Tuple[List[str], List[Dict[str, Optional[str]]]]:
    """Parse Markdown or Tab-separated table lines into columns and rows."""
    if not lines:
        return [], []

    clean_lines = []
    for l in lines:
        l = l.strip()
        if l.startswith("```") or re.match(r'^\|?\s*[-:\s|]+\s*\|?$', l):
            continue
        if l.startswith("- "):
            l = l[2:].strip()
        clean_lines.append(l)

    if not clean_lines:
        return [], []

    # Check for markdown table format (| col1 | col2 |)
    if any("|" in l for l in clean_lines):
        header_parts = [c.strip() for c in clean_lines[0].strip('|').split('|') if c.strip()]
        columns = header_parts if header_parts else ["Col 1", "Col 2", "Col 3"]
        rows = []
        for line in clean_lines[1:]:
            parts = [c.strip() for c in line.strip('|').split('|')]
            row = {}
            for j, col in enumerate(columns):
                row[col] = parts[j] if j < len(parts) else ""
            rows.append(row)
        return columns, rows

    # Otherwise tab-separated
    header_idx = 0
    header_parts = re.split(r'\t+|\s{2,}', clean_lines[0].strip())
    columns = [part.strip() for part in header_parts if part.strip()]
    if not columns:
        columns = [f"Column {j+1}" for j in range(5)]

    rows = []
    for line in clean_lines[1:]:
        if not line.strip():
            continue
        parts = re.split(r'\t+|\s{2,}', line.strip())
        parts = [p.strip() for p in parts]
        row = {}
        for j, col in enumerate(columns):
            row[col] = parts[j] if j < len(parts) else ""
        rows.append(row)

    return columns, rows


def _parse_sample_table_single_space(lines: List[str]) -> Tuple[List[str], List[Dict[str, Optional[str]]]]:
    columns = ["No.", "From", "To", "Type", "Blow 1", "Blow 2", "Blow 3", "Blow 4", "Recovery"]
    rows = []
    for line in lines:
        line = line.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        if not line or line.lower().startswith("sample") or line.lower().startswith("no.") or line.lower().startswith("penetration"):
            continue

        # Check if line has tab or multi-space delimiters
        if "\t" in line or re.search(r'\s{2,}', line):
            parts = [p.strip() for p in re.split(r'\t+|\s{2,}', line) if p.strip()]
            if len(parts) >= 3:
                # Filter out single dash placeholders if needed, or map directly
                cleaned_parts = [p for p in parts if p != "-"]
                if len(cleaned_parts) >= 3:
                    s_no = cleaned_parts[0] if len(cleaned_parts) > 0 else ""
                    f_d = cleaned_parts[1] if len(cleaned_parts) > 1 else ""
                    t_d = cleaned_parts[2] if len(cleaned_parts) > 2 else ""
                    s_t = cleaned_parts[3] if len(cleaned_parts) > 3 and not cleaned_parts[3].isdigit() else ""
                    # find blow count numbers
                    num_idx = 4 if s_t else 3
                    nums = [p for p in cleaned_parts[num_idx:] if p.isdigit() or re.match(r'^\d+[\'"]?$', p)]
                    b1 = nums[0] if len(nums) > 0 else ""
                    b2 = nums[1] if len(nums) > 1 else ""
                    b3 = nums[2] if len(nums) > 2 else ""
                    b4 = nums[3] if len(nums) > 3 else ""
                    rec = nums[4] if len(nums) > 4 else (cleaned_parts[-1] if '"' in cleaned_parts[-1] else "")
                    rows.append({
                        "No.": s_no,
                        "From": f_d,
                        "To": t_d,
                        "Type": s_t,
                        "Blow 1": b1,
                        "Blow 2": b2,
                        "Blow 3": b3,
                        "Blow 4": b4,
                        "Recovery": rec,
                    })
                    continue

        match = re.match(r'^(\d+)\s+(\d+(?:\.\d+)?[\'"]?)\s+(\d+(?:\.\d+)?[\'"]?)\s*([A-Za-z]{1,3})?\s*(.*)$', line)
        if not match:
            continue
        sample_no = match.group(1)
        from_depth = match.group(2)
        to_depth = match.group(3)
        sample_type = match.group(4) or ""
        rest = match.group(5).strip()
        tokens = rest.split()
        blows = []
        recovery = ""
        for token in tokens:
            if token.isdigit() and len(blows) < 4:
                blows.append(token)
            elif '"' in token and not recovery:
                recovery = token

        while len(blows) < 4:
            blows.append("")
        row = {
            "No.": sample_no,
            "From": from_depth,
            "To": to_depth,
            "Type": sample_type,
            "Blow 1": blows[0],
            "Blow 2": blows[1],
            "Blow 3": blows[2],
            "Blow 4": blows[3],
            "Recovery": recovery,
        }
        rows.append(row)
    return columns, rows


def _parse_lithology_table_single_space(lines: List[str]) -> Tuple[List[str], List[Dict[str, Optional[str]]]]:
    columns = ["Depth From", "Depth To", "Description"]
    rows = []
    for line in lines:
        line = line.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        if not line or line.lower().startswith("sample description") or line.lower().startswith("lithology") or line.lower().startswith("from to"):
            continue

        if "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
            if len(parts) >= 2:
                rows.append({
                    "Depth From": parts[0] if len(parts) > 0 else "",
                    "Depth To": parts[1] if len(parts) > 1 else "",
                    "Description": parts[2] if len(parts) > 2 else (" ".join(parts[2:]) if len(parts) > 3 else ""),
                })
                continue

        match = re.match(r"^(\d+(?:\.\d+)?['\"]?)\s*[-–\s]\s*(\d+(?:\.\d+)?['\"]?)\s*(.*)$", line)
        if match:
            depth_from = match.group(1)
            depth_to = match.group(2)
            description = match.group(3).strip()
        else:
            depth_from = ""
            depth_to = ""
            description = line

        rows.append({
            "Depth From": depth_from,
            "Depth To": depth_to,
            "Description": description,
        })
    return columns, rows


def build_document_from_sections(raw_text: str) -> Document:
    """Build Document from raw text using generic section detection."""
    clean_raw = clean_html_entities(raw_text)
    sections_map = split_sections(clean_raw)
    doc_sections: List[Section] = []

    # Header
    if "header" in sections_map:
        header_text = sections_map["header"]
        fields = extract_key_value_pairs(header_text)
        if fields:
            doc_sections.append(Section(name="Header", type="key_value", fields=fields, raw_text=header_text))
        else:
            doc_sections.append(Section(name="Header", type="raw_text", text=header_text, raw_text=header_text))

    # Boring Advancement
    if "boring_advancement" in sections_map:
        adv_text = sections_map["boring_advancement"]
        fields = extract_key_value_pairs(adv_text)
        if fields:
            doc_sections.append(Section(name="Boring Advancement", type="key_value", fields=fields, raw_text=adv_text))
        else:
            doc_sections.append(Section(name="Boring Advancement", type="raw_text", text=adv_text, raw_text=adv_text))

    # Sample Data Table
    if "sample_data_table" in sections_map:
        sample_text = sections_map["sample_data_table"]
        lines = sample_text.splitlines()
        columns, rows = None, None
        if _is_table_section(lines):
            columns, rows = _parse_table(lines)
        if not columns or not rows:
            columns, rows = _parse_sample_table_single_space(lines)
        if columns and rows:
            doc_sections.append(Section(name="Sample Data Table", type="table",
                                        columns=columns, rows=rows, raw_text=sample_text))
        else:
            doc_sections.append(Section(name="Sample Data Table", type="raw_text", text=sample_text, raw_text=sample_text))

    # Lithology Data Table
    if "lithology_data_table" in sections_map:
        lith_text = sections_map["lithology_data_table"]
        lines = lith_text.splitlines()
        columns, rows = None, None
        if _is_table_section(lines):
            columns, rows = _parse_table(lines)
        if not columns or not rows:
            columns, rows = _parse_lithology_table_single_space(lines)
        if columns and rows:
            doc_sections.append(Section(name="Lithology / Sample Description Table", type="table",
                                        columns=columns, rows=rows, raw_text=lith_text))
        else:
            doc_sections.append(Section(name="Lithology / Sample Description Table", type="raw_text",
                                        text=lith_text, raw_text=lith_text))

    # Surface Cover & Thickness
    if "surface_cover_thickness" in sections_map:
        sc_text = sections_map["surface_cover_thickness"]
        fields = extract_key_value_pairs(sc_text)
        doc_sections.append(Section(name="Surface Cover & Thickness", type="key_value", fields=fields, raw_text=sc_text))

    # Water Level Observations
    if "water_level_observations" in sections_map:
        wl_text = sections_map["water_level_observations"]
        fields = extract_key_value_pairs(wl_text)
        doc_sections.append(Section(name="Water Level Observations", type="key_value", fields=fields, raw_text=wl_text))

    # Boring Abandonment
    if "boring_abandonment" in sections_map:
        ba_text = sections_map["boring_abandonment"]
        fields = extract_key_value_pairs(ba_text)
        doc_sections.append(Section(name="Boring Abandonment", type="key_value", fields=fields, raw_text=ba_text))

    # Additional Remarks
    if "additional_remarks" in sections_map:
        ar_text = sections_map["additional_remarks"]
        doc_sections.append(Section(name="Additional Remarks", type="raw_text", text=ar_text, raw_text=ar_text))

    # Sheet Info
    if "sheet_info" in sections_map:
        si_text = sections_map["sheet_info"]
        fields = extract_key_value_pairs(si_text)
        doc_sections.append(Section(name="Sheet Info", type="key_value", fields=fields, raw_text=si_text))

    return Document(sections=doc_sections)


# ---------- Main extraction function ----------

def extract_fields(raw_text: str) -> Document:
    """
    Parse cleaned raw text into a generic Document with sections.
    """
    logger.info("Starting field extraction from cleaned text")
    document = build_document_from_sections(raw_text)
    logger.info(f"Extraction completed with {len(document.sections)} sections")
    return document