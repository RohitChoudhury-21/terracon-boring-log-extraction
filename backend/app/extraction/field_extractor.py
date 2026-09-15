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
                # Ignore colons in timestamps like 8:00 or 10:15
                if idx > 0 and idx + 1 < len(line) and line[idx-1].isdigit() and line[idx+1].isdigit():
                    continue
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
        "header": r"^##\s*HEADER\b",
        "boring_advancement": r"^##\s*BORING[_\s]+ADVANCEMENT\b",
        "boring_log_table": r"^##\s*(BORING_LOG_TABLE|BORING_TABLE|UNIFIED_TABLE|LOG_TABLE)\b",
        "sample_data_table": r"^##\s*SAMPLE[_\s]+DATA[_\s]+TABLE\b",
        "lithology_data_table": r"^##\s*LITHOLOGY[_\s]+(?:DATA[_\s]+)?TABLE\b",
        "surface_cover_thickness": r"^##\s*SURFACE[_\s]+COVER(?:[_\s]+(?:&|AND)[_\s]+THICKNESS)?\b",
        "water_level_observations": r"^##\s*WATER[_\s]+LEVEL(?:[_\s]+OBSERVATIONS)?\b",
        "boring_abandonment": r"^##\s*BORING[_\s]+ABANDONMENT\b",
        "additional_remarks": r"^(?:##\s*)?(?:terracon\s*)?additional\s*remarks\b",
        "sheet_info": r"^##\s*SHEET[_\s]+INFO\b",
    }

    sections = {}
    current_section = None
    current_lines = []

    for line in text.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue

        matched_section = None
        # 1. Try explicit markdown headers
        for sec, pattern in marker_patterns.items():
            if re.match(pattern, line_stripped, re.IGNORECASE):
                matched_section = sec
                break

        # 2. Try natural text headings (only if line is a header and not a key-value data row)
        if not matched_section:
            clean_lower = re.sub(r"^#+\s*", "", line_stripped.lower()).strip()
            if (clean_lower.startswith("depth") and "lithology" in clean_lower) or clean_lower.startswith("sample description and lithology") or re.match(r"^lithology\s*(?:data\s*table|description)?", clean_lower):
                matched_section = "lithology_data_table"
            elif re.search(r"\bsample\b", clean_lower) and re.search(r"\b(lithology|description)\b", clean_lower):
                matched_section = "boring_log_table"
            elif "\t" in line and re.search(r"\b(from\b.*?\bto|blow|blows|penetration|recovery)\b", clean_lower):
                if re.search(r"\b(lithology|description)\b", clean_lower):
                    matched_section = "boring_log_table"
                else:
                    matched_section = "sample_data_table"
            elif re.match(r"^sample\s*(?:data\s*table|record|no\.?|collection)", clean_lower) and not re.search(r"^\d+\s+\d+", clean_lower):
                matched_section = "sample_data_table"
            elif re.match(r"^boring\s*advancement\b", clean_lower):
                matched_section = "boring_advancement"
            elif re.match(r"^surface\s*cover\b", clean_lower):
                matched_section = "surface_cover_thickness"
            elif re.match(r"^water\s*level\b", clean_lower):
                matched_section = "water_level_observations"
            elif re.match(r"^boring\s*abandonment\b", clean_lower):
                matched_section = "boring_abandonment"
            elif re.match(r"^(?:terracon\s*)?additional\s*remarks\b", clean_lower):
                matched_section = "additional_remarks"
            elif re.match(r"^sheet\s*:\s*\d+\s+of\s+\d+", clean_lower) or re.match(r"^sheet\s+\d+\s+of\s+\d+", clean_lower):
                matched_section = "sheet_info"

        if matched_section:
            if current_section and current_lines:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = matched_section
            if matched_section in ("boring_log_table", "sample_data_table", "lithology_data_table"):
                current_lines = [line]
            elif matched_section == "additional_remarks":
                if ":" in line:
                    after_colon = line.split(":", 1)[1].strip().lstrip("-").strip()
                    current_lines = [after_colon] if after_colon else []
                else:
                    current_lines = []
            else:
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
    if "\t" in clean_lines[0]:
        header_parts = [p.strip() for p in clean_lines[0].split("\t")]
    else:
        header_parts = [p.strip() for p in re.split(r'\s{2,}', clean_lines[0].strip())]
    columns = [part for part in header_parts if part]
    if not columns:
        columns = [f"Column {j+1}" for j in range(5)]

    rows = []
    for line in clean_lines[1:]:
        if not line.strip():
            continue
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
        else:
            parts = [p.strip() for p in re.split(r'\s{2,}', line.strip())]
        row = {}
        for j, col in enumerate(columns):
            row[col] = parts[j] if j < len(parts) else ""
        rows.append(row)

    return columns, rows


def _parse_sample_table_single_space(lines: List[str]) -> Tuple[List[str], List[Dict[str, Optional[str]]]]:
    columns = ["No.", "From", "To", "Type", "Blow 1", "Blow 2", "Blow 3", "Blow 4", "Recovery", "Depth From", "Depth To", "Description"]
    rows = []
    for line in lines:
        line = line.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        if not line or line.startswith("#") or line.lower().startswith("sample") or line.lower().startswith("no.") or line.lower().startswith("penetration"):
            continue

        tokens = line.split()
        if len(tokens) < 3 or not tokens[0].isdigit():
            continue

        sample_no = tokens[0]
        from_depth = tokens[1]
        to_depth = tokens[2]
        rest_tokens = tokens[3:]

        blows = []
        recovery = ""
        sample_type = ""
        desc_tokens = []
        idx = 0
        while idx < len(rest_tokens):
            tok = rest_tokens[idx]
            clean_tok = tok.strip('.,()')
            if tok in {"-", "–", "--", "---", "_"}:
                idx += 1
                continue
            if sample_type == "" and clean_tok.isalpha() and len(clean_tok) <= 3:
                sample_type = clean_tok
            elif clean_tok.isdigit() and len(blows) < 4 and not desc_tokens:
                blows.append(clean_tok)
            elif '"' in tok and recovery == "":
                recovery = tok
            elif clean_tok.isdigit() and len(blows) == 4 and not recovery:
                recovery = clean_tok
            else:
                desc_tokens.append(tok)
            idx += 1

        while len(blows) < 4:
            blows.append("")

        desc = " ".join(desc_tokens).strip()
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
            "Depth From": from_depth,
            "Depth To": to_depth,
            "Description": desc,
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
        lower = line.lower()
        if (
            not line
            or line.startswith("#")
            or lower.startswith("sample description")
            or lower.startswith("lithology")
            or lower.startswith("soil description")
            or lower.startswith("from to")
            or (lower.startswith("depth") and any(w in lower for w in ["from", "to", "description", "lithology"]))
            or "sample description and lithology" in lower
        ):
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
            single_match = re.match(r"^(\d+(?:\.\d+)?['\"]?)\s+([A-Za-z].*)$", line)
            if single_match:
                depth_from = single_match.group(1)
                depth_to = ""
                description = single_match.group(2).strip()
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

    # Unified Boring Log Table (handles unified table from GLM-OCR)
    if "boring_log_table" in sections_map:
        table_text = sections_map["boring_log_table"]
        lines = table_text.splitlines()
        columns, rows = None, None
        if _is_table_section(lines):
            columns, rows = _parse_table(lines)
        if not columns or not rows:
            columns, rows = _parse_sample_table_single_space(lines)

        if rows:
            sample_rows = []
            lith_rows = []
            for r in rows:
                def get_col(*aliases):
                    for a in aliases:
                        for k, v in r.items():
                            if k and k.strip().lower() == a.lower() and v is not None:
                                return v.strip()
                    return ""

                s_no = get_col("Sample No", "No.", "No", "Sample")
                f_d = get_col("From", "From Depth")
                t_d = get_col("To", "To Depth")
                s_type = get_col("Type", "Sample Type")
                b1 = get_col("Blow 1", "Blow1", "B1")
                b2 = get_col("Blow 2", "Blow2", "B2")
                b3 = get_col("Blow 3", "Blow3", "B3")
                b4 = get_col("Blow 4", "Blow4", "B4")
                n_val = get_col("N-Val", "N-Value", "N Value", "N")
                rec = get_col("Recovery", "Rec", "Recovery (inches)", "Recovery (m³)", "Recovery (m3)", "Recovery(m³)")

                if s_no or f_d or t_d or b1 or b2 or b3 or b4 or rec or s_type:
                    sample_rows.append({
                        "No.": s_no,
                        "From": f_d,
                        "To": t_d,
                        "Type": s_type,
                        "Blow 1": b1,
                        "Blow 2": b2,
                        "Blow 3": b3,
                        "Blow 4": b4,
                        "Recovery": rec,
                    })

                d_from = get_col("Depth From", "Strata From", "D. From")
                d_to = get_col("Depth To", "Strata To", "D. To")
                desc = get_col("Lithology Description", "Description", "Lithology", "Sample Description and Lithology", "Sample Description")
                depth_val = get_col("Depth", "Depth (ft)", "Depth(ft)", "Depth From - To", "Depth Range")

                if depth_val:
                    m_depth = re.match(r"^(\d+(?:\.\d+)?['\"]?)\s*[-–\s]\s*(\d+(?:\.\d+)?['\"]?)\s*(.*)$", depth_val)
                    if m_depth:
                        if not d_from:
                            d_from = m_depth.group(1)
                        if not d_to:
                            d_to = m_depth.group(2)
                        rem = m_depth.group(3).strip()
                        if rem and not desc:
                            desc = rem
                    elif any(c.isalpha() for c in depth_val) and len(depth_val) > 3:
                        if not desc:
                            desc = depth_val

                if desc:
                    m_desc = re.match(r"^(\d+(?:\.\d+)?['\"]?)\s*[-–\s]\s*(\d+(?:\.\d+)?['\"]?)\s*(.*)$", desc)
                    if m_desc:
                        if not d_from:
                            d_from = m_desc.group(1)
                        if not d_to:
                            d_to = m_desc.group(2)
                        if m_desc.group(3).strip():
                            desc = m_desc.group(3).strip()

                # If Depth From was omitted on lithology side but sample had From/To, borrow it if desc exists
                if desc and not d_from and f_d:
                    d_from = f_d
                if desc and not d_to and t_d:
                    d_to = t_d

                if d_from or d_to or desc:
                    lith_rows.append({
                        "Depth From": d_from,
                        "Depth To": d_to,
                        "Description": desc,
                    })

            if sample_rows:
                doc_sections.append(Section(
                    name="Sample Data Table",
                    type="table",
                    columns=["No.", "From", "To", "Type", "Blow 1", "Blow 2", "Blow 3", "Blow 4", "Recovery"],
                    rows=sample_rows,
                    raw_text=table_text
                ))
            if lith_rows:
                doc_sections.append(Section(
                    name="Lithology / Sample Description Table",
                    type="table",
                    columns=["Depth From", "Depth To", "Description"],
                    rows=lith_rows,
                    raw_text=table_text
                ))

    # Sample Data Table (fallback if not already populated by unified table)
    if "sample_data_table" in sections_map and "boring_log_table" not in sections_map:
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

    # Lithology Data Table (fallback if not already populated by unified table)
    if "lithology_data_table" in sections_map and "boring_log_table" not in sections_map:
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

    # Boring Advancement
    if "boring_advancement" in sections_map:
        adv_text = sections_map["boring_advancement"]
        fields = extract_key_value_pairs(adv_text)
        if fields:
            doc_sections.append(Section(name="Boring Advancement", type="key_value", fields=fields, raw_text=adv_text))
        else:
            doc_sections.append(Section(name="Boring Advancement", type="raw_text", text=adv_text, raw_text=adv_text))

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