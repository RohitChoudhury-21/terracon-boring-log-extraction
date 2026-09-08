"""
Post-processing for GLM-OCR output on boring logs.

This module is form-independent. It does not assume a fixed
Terracon schema. It handles:

1. HTML entity decoding (&#x27; -> ', &quot; -> ", etc.) and HTML table parsing.
2. Cleaning OCR noise (blank lines, code fences, stray HTML tags).
3. Section detection (header, sample table, lithology table, etc.) using broad patterns.
4. Robust multi-key-value extraction (avoiding fake keys from colons inside parentheses).
5. Dynamic table row parsing and column assignment for Sample & Lithology tables.
6. Markdown output with explicit `## SECTION` markers.
"""

import html
import json
import re
from pathlib import Path


def clean_text(raw_text: str) -> str:
    """
    Sanitize OCR text, decoding HTML entities, parsing HTML table tags,
    and removing code fences.
    """
    if not raw_text:
        return ""

    # 1. Decode HTML entities (&#x27; -> ', &quot; -> ", &amp; -> &, etc.)
    text = html.unescape(raw_text)

    # 2. Check if text contains HTML table tags
    if "<table" in text.lower() or "<tr" in text.lower() or "<td" in text.lower():
        # Replace closing </tr> with newlines to preserve row boundaries
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

    # 3. Remove accidental Markdown code fences and blank lines
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line in {"```", "```text", "```markdown", "```json", "```html"}:
            continue
        lines.append(line)

    return "\n".join(lines)


def is_sample_row(line: str) -> bool:
    """
    Detect a possible sample-data row.
    """
    pattern = (
        r"^\s*"
        r"\d+"
        r"\s+"
        r"\d+(?:\.\d+)?['\"]?"
        r"\s+"
        r"\d+(?:\.\d+)?['\"]?"
    )
    return bool(re.search(pattern, line))


def find_sample_table_start(lines: list[str]) -> int | None:
    """
    Detect the beginning of the sample-data table.
    """
    for i, line in enumerate(lines):
        lower = line.lower().strip()
        if (
            lower == "sample"
            or "sample no." in lower
            or "sample collection time" in lower
            or "no. from to type" in lower
            or "penetration record" in lower
            or lower == "blows"
            or "blows" in lower
            or "recovery (inches)" in lower
            or "recovery" in lower
            or "n-value" in lower
        ):
            return i

    for i, line in enumerate(lines):
        if is_sample_row(line):
            return i

    return None


def find_lithology_table_start(
    lines: list[str],
    sample_start: int | None
) -> int | None:
    """
    Detect the beginning of a lithology / description table.
    """
    start_index = sample_start + 1 if sample_start is not None else 0

    lithology_patterns = [
        "sample description and lithology",
        "lithology description",
        "lithology description and observations",
        "lithology depth",
        "soil description",
        "soil description and observations",
        "lithologic description",
        "lithologic description and observations",
        "description and lithology",
    ]

    for i in range(start_index, len(lines)):
        lower = lines[i].lower()
        for pattern in lithology_patterns:
            if pattern in lower:
                return i

    return None


def normalize_table_row(line: str) -> str:
    """
    Normalize clear table delimiters.
    Preserves tabs. Converts 2+ spaces to tabs.
    """
    if "\t" in line:
        return line.strip()

    if re.search(r" {2,}", line):
        return re.sub(r" {2,}", "\t", line.strip())

    return line.strip()


def normalize_table_rows(rows: list[str]) -> list[str]:
    return [normalize_table_row(row) for row in rows]


def extract_key_value_pairs(text_block: str) -> dict:
    """
    Extract key-value pairs accurately:
    1. Handles multiple Key: Value pairs on one line.
    2. Handles consecutive empty keys (e.g., 'Latitude: Longitude: Surface Elevation:').
    3. Prevents colons inside parentheses from splitting into fake keys.
    """
    pairs = {}
    clean_lines = text_block.splitlines()

    for line in clean_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Find all colon positions not inside parentheses
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


def split_sections(cleaned_text: str) -> dict:
    """
    Split OCR output into generic document regions.
    """
    lines = cleaned_text.splitlines()

    sample_start = find_sample_table_start(lines)
    lithology_start = find_lithology_table_start(lines, sample_start)

    # Header
    if sample_start is not None:
        header = lines[:sample_start]
    else:
        header = lines

    # Sample Data Table
    if sample_start is not None:
        if lithology_start is not None:
            sample_data = lines[sample_start:lithology_start]
        else:
            sample_data = lines[sample_start:]
    else:
        sample_data = []

    sample_data = normalize_table_rows(sample_data)

    # Lithology Table
    next_section = None
    if lithology_start is not None:
        for i in range(lithology_start + 1, len(lines)):
            lower = lines[i].lower().strip()
            known_section_patterns = [
                "boring advancement",
                "advancement and completion",
                "advancement and completion data",
                "surface cover",
                "surface cover & thickness",
                "water level",
                "water levels",
                "water level observations",
                "boring abandonment",
                "abandonment",
                "additional remarks",
                "remarks",
                "notes",
                "gps",
                "abbreviations",
            ]
            if any(pattern in lower for pattern in known_section_patterns):
                next_section = i
                break

        if next_section is not None:
            lithology = lines[lithology_start:next_section]
        else:
            lithology = lines[lithology_start:]
    else:
        lithology = []

    lithology = normalize_table_rows(lithology)

    # Remaining Sections
    boring_advancement = []
    surface_cover = []
    water_levels = []
    abandonment = []
    additional_remarks = []
    other_sections = []

    if next_section is not None:
        remaining_lines = lines[next_section:]
        current_section = "other"
        current_content = []

        def save_section():
            if not current_content:
                return
            if current_section == "boring_advancement":
                boring_advancement.extend(current_content)
            elif current_section == "surface_cover":
                surface_cover.extend(current_content)
            elif current_section == "water_levels":
                water_levels.extend(current_content)
            elif current_section == "abandonment":
                abandonment.extend(current_content)
            elif current_section == "additional_remarks":
                additional_remarks.extend(current_content)
            else:
                other_sections.append({
                    "name": current_section,
                    "content": current_content.copy()
                })

        for line in remaining_lines:
            lower = line.lower().strip()

            if lower == "boring advancement" or "advancement and completion" in lower:
                save_section()
                current_section = "boring_advancement"
                current_content = []
                continue

            if lower == "surface cover & thickness" or "surface cover" in lower:
                save_section()
                current_section = "surface_cover"
                current_content = []
                continue

            if lower == "water level observations" or lower == "water levels" or "water level" in lower:
                save_section()
                current_section = "water_levels"
                current_content = []
                continue

            if lower == "boring abandonment" or "abandonment" in lower:
                save_section()
                current_section = "abandonment"
                current_content = []
                continue

            if lower.startswith("additional remarks") or lower == "remarks" or lower.startswith("remarks:"):
                save_section()
                current_section = "additional_remarks"
                current_content = []
                continue

            if lower == "notes:" or lower == "notes" or lower.startswith("notes:"):
                save_section()
                current_section = "notes"
                current_content = [line]
                continue

            current_content.append(line)

        save_section()

    return {
        "header": header,
        "sample_data_table": {
            "rows": sample_data,
            "preserved_as_ocr": True
        },
        "lithology_data_table": {
            "rows": lithology,
            "preserved_as_ocr": True
        },
        "boring_advancement": boring_advancement,
        "surface_cover_thickness": surface_cover,
        "water_level_observations": water_levels,
        "boring_abandonment": abandonment,
        "additional_remarks": additional_remarks,
        "other_sections": other_sections,
    }


def parse_sample_and_lithology_rows(sample_lines: list[str], lith_lines: list[str]):
    """
    Parse sample and lithology lines dynamically into structured table rows.
    """
    sample_columns = ["No.", "From", "To", "Type", "Blow 1", "Blow 2", "Blow 3", "Blow 4", "Recovery"]
    lith_columns = ["Depth From", "Depth To", "Description"]

    sample_rows = []
    lith_rows = []

    combined_lines = sample_lines + lith_lines

    for line in combined_lines:
        line = line.strip()
        if not line:
            continue

        lower = line.lower()
        if (lower.startswith("sample") or lower.startswith("no.") or 
            lower.startswith("penetration") or lower.startswith("depth") or 
            lower.startswith("from to") or lower.startswith("6\" 6\"") or
            lower.startswith("sample description")):
            continue

        # Tab-delimited row (from HTML or multi-space)
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
            if len(parts) >= 3:
                s_no = parts[0] if len(parts) > 0 else ""
                f_d = parts[1] if len(parts) > 1 else ""
                t_d = parts[2] if len(parts) > 2 else ""
                s_t = parts[3] if len(parts) > 3 else ""
                b1 = parts[4] if len(parts) > 4 else ""
                b2 = parts[5] if len(parts) > 5 else ""
                b3 = parts[6] if len(parts) > 6 else ""
                b4 = parts[7] if len(parts) > 7 else ""
                rec = parts[8] if len(parts) > 8 else ""

                extra_desc = " ".join(parts[9:]).strip() if len(parts) > 9 else ""
                desc = ""
                if len(parts) > 8 and any(c.isalpha() for c in parts[8]) and len(parts[8]) > 4:
                    desc = parts[8] + (" " + extra_desc if extra_desc else "")
                    rec = ""
                elif extra_desc:
                    desc = extra_desc

                sample_rows.append({
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
                if desc:
                    lith_rows.append({
                        "Depth From": f_d,
                        "Depth To": t_d,
                        "Description": desc
                    })
                continue

        # Sample row match (e.g. 1 0' 2' SS 2 3 4 5 19")
        sample_match = re.match(r'^(\d+)\s+(\d+(?:\.\d+)?[\'"]?)\s+(\d+(?:\.\d+)?[\'"]?)\s*([A-Za-z]{1,3})?\s*(.*)$', line)
        if sample_match:
            s_no = sample_match.group(1)
            f_d = sample_match.group(2)
            t_d = sample_match.group(3)
            s_t = sample_match.group(4) or ""
            rest = sample_match.group(5).strip()

            tokens = rest.split()
            blows = []
            rec = ""
            desc_tokens = []
            for tok in tokens:
                if tok.isdigit() and len(blows) < 4:
                    blows.append(tok)
                elif '"' in tok and not rec:
                    rec = tok
                else:
                    desc_tokens.append(tok)

            while len(blows) < 4:
                blows.append("")

            sample_rows.append({
                "No.": s_no,
                "From": f_d,
                "To": t_d,
                "Type": s_t,
                "Blow 1": blows[0],
                "Blow 2": blows[1],
                "Blow 3": blows[2],
                "Blow 4": blows[3],
                "Recovery": rec,
            })
            if desc_tokens:
                lith_rows.append({
                    "Depth From": f_d,
                    "Depth To": t_d,
                    "Description": " ".join(desc_tokens)
                })
            continue

        # Lithology depth range match (e.g. 4' 13' gray fat clay)
        lith_match = re.match(r'^(\d+(?:\.\d+)?[\'"]?)\s*[-–\s]\s*(\d+(?:\.\d+)?[\'"]?)\s*(.*)$', line)
        if lith_match:
            d_from = lith_match.group(1)
            d_to = lith_match.group(2)
            desc = lith_match.group(3).strip()
            lith_rows.append({
                "Depth From": d_from,
                "Depth To": d_to,
                "Description": desc
            })
            continue

        # Other descriptive lines
        if any(w in lower for w in ["clay", "sand", "silt", "gravel", "shelby", "rec", "moist", "fat", "lean", "tan", "gray", "red", "dittom", "ditto", "ch", "sc", "cl", "ml"]):
            lith_rows.append({
                "Depth From": "",
                "Depth To": "",
                "Description": line
            })

    return sample_columns, sample_rows, lith_columns, lith_rows


def build_document_json(structured_data: dict, document_name: str) -> dict:
    """
    Convert the structured_data dict into the Document schema expected by the frontend.
    """
    sections = []

    # Header
    if structured_data.get("header"):
        header_text = "\n".join(structured_data["header"])
        fields = extract_key_value_pairs(header_text)
        if fields:
            sections.append({
                "name": "Header",
                "type": "key_value",
                "fields": fields,
                "columns": None,
                "rows": None,
                "text": None,
                "raw_text": header_text
            })

    # Tables: Sample & Lithology
    sample_raw = structured_data.get("sample_data_table", {}).get("rows", [])
    lith_raw = structured_data.get("lithology_data_table", {}).get("rows", [])

    s_cols, s_rows, l_cols, l_rows = parse_sample_and_lithology_rows(sample_raw, lith_raw)

    if s_rows:
        sections.append({
            "name": "Sample Data Table",
            "type": "table",
            "fields": None,
            "columns": s_cols,
            "rows": s_rows,
            "text": None,
            "raw_text": "\n".join(sample_raw)
        })
    elif sample_raw:
        sections.append({
            "name": "Sample Data Table",
            "type": "raw_text",
            "fields": None,
            "columns": None,
            "rows": None,
            "text": "\n".join(sample_raw),
            "raw_text": "\n".join(sample_raw)
        })

    if l_rows:
        sections.append({
            "name": "Lithology / Sample Description Table",
            "type": "table",
            "fields": None,
            "columns": l_cols,
            "rows": l_rows,
            "text": None,
            "raw_text": "\n".join(lith_raw)
        })
    elif lith_raw:
        sections.append({
            "name": "Lithology / Sample Description Table",
            "type": "raw_text",
            "fields": None,
            "columns": None,
            "rows": None,
            "text": "\n".join(lith_raw),
            "raw_text": "\n".join(lith_raw)
        })

    # Other known sections
    known_sections = [
        ("Boring Advancement", "boring_advancement"),
        ("Surface Cover & Thickness", "surface_cover_thickness"),
        ("Water Level Observations", "water_level_observations"),
        ("Boring Abandonment", "boring_abandonment"),
        ("Additional Remarks", "additional_remarks"),
    ]
    for title, key in known_sections:
        content = structured_data.get(key, [])
        if content:
            raw_sec_text = "\n".join(content)
            fields = extract_key_value_pairs(raw_sec_text)
            if fields:
                sections.append({
                    "name": title,
                    "type": "key_value",
                    "fields": fields,
                    "columns": None,
                    "rows": None,
                    "text": None,
                    "raw_text": raw_sec_text
                })
            else:
                sections.append({
                    "name": title,
                    "type": "raw_text",
                    "fields": None,
                    "columns": None,
                    "rows": None,
                    "text": raw_sec_text,
                    "raw_text": raw_sec_text
                })

    # Unknown sections
    for other in structured_data.get("other_sections", []):
        raw_other = "\n".join(other["content"])
        sections.append({
            "name": other["name"],
            "type": "raw_text",
            "fields": None,
            "columns": None,
            "rows": None,
            "text": raw_other,
            "raw_text": raw_other
        })

    return {"sections": sections}


def create_markdown(data: dict, document_name: str = "unknown") -> str:
    """
    Create Markdown output with clean section headers and tables.
    """
    md = []
    md.append(f"# Terracon Boring Log — {document_name}")
    md.append("")
    md.append("> OCR engine: GLM-OCR")
    md.append("> OCR values are preserved and structured into dynamic sections.")
    md.append("")

    if data.get("header"):
        md.append("## HEADER")
        md.append("")
        for line in data["header"]:
            md.append(line.lstrip("- ").strip())
        md.append("")

    sample_raw = data.get("sample_data_table", {}).get("rows", [])
    lith_raw = data.get("lithology_data_table", {}).get("rows", [])
    s_cols, s_rows, l_cols, l_rows = parse_sample_and_lithology_rows(sample_raw, lith_raw)

    if s_rows:
        md.append("## SAMPLE DATA TABLE")
        md.append("")
        md.append("| " + " | ".join(s_cols) + " |")
        md.append("| " + " | ".join(["---"] * len(s_cols)) + " |")
        for row in s_rows:
            md.append("| " + " | ".join(row.get(col, "") for col in s_cols) + " |")
        md.append("")

    if l_rows:
        md.append("## LITHOLOGY / SAMPLE DESCRIPTION TABLE")
        md.append("")
        md.append("| " + " | ".join(l_cols) + " |")
        md.append("| " + " | ".join(["---"] * len(l_cols)) + " |")
        for row in l_rows:
            md.append("| " + " | ".join(row.get(col, "") for col in l_cols) + " |")
        md.append("")

    sections = [
        ("BORING_ADVANCEMENT", "boring_advancement"),
        ("SURFACE_COVER_THICKNESS", "surface_cover_thickness"),
        ("WATER_LEVEL_OBSERVATIONS", "water_level_observations"),
        ("BORING_ABANDONMENT", "boring_abandonment"),
        ("ADDITIONAL_REMARKS", "additional_remarks"),
    ]

    for title, key in sections:
        if not data.get(key):
            continue
        md.append(f"## {title}")
        md.append("")
        for line in data[key]:
            md.append(line.lstrip("- ").strip())
        md.append("")

    for section in data.get("other_sections", []):
        md.append(f"## {section['name']}")
        md.append("")
        for line in section["content"]:
            md.append(line.lstrip("- ").strip())
        md.append("")

    return "\n".join(md)


def save_outputs(
    raw_text: str,
    json_path: str,
    markdown_path: str,
    document_name: str = "unknown",
) -> tuple[str, str]:
    cleaned_text = clean_text(raw_text)
    structured_data = split_sections(cleaned_text)

    document_json = build_document_json(structured_data, document_name)

    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(
        json.dumps(document_json, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    markdown = create_markdown(structured_data, document_name)
    markdown_file = Path(markdown_path)
    markdown_file.parent.mkdir(parents=True, exist_ok=True)
    markdown_file.write_text(markdown, encoding="utf-8")

    print(f"JSON saved: {json_file}")
    print(f"Markdown saved: {markdown_file}")

    return json.dumps(document_json), str(markdown_file)