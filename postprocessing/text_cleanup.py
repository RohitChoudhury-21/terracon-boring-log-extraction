import json
import re
from pathlib import Path


def clean_text(raw_text: str) -> str:
    """
    Conservative cleanup of GLM-OCR output.

    No spelling correction.
    No number correction.
    No semantic interpretation.
    """

    if not raw_text:
        return ""

    lines = []

    for line in raw_text.splitlines():
        line = line.strip()

        if not line:
            continue

        # Remove accidental Markdown code fences from OCR output.
        if line in {
            "```",
            "```text",
            "```markdown",
            "```json",
        }:
            continue

        lines.append(line)

    return "\n".join(lines)


def is_sample_row(line: str) -> bool:
    """
    Detect a possible sample-data row.

    Example:
        1  0'  2'  SS
        2  2'  4'  SS

    This function is only used as a fallback to locate
    the beginning of the sample table.

    It does not parse or assign individual columns.
    """

    pattern = (
            r"^\s*"
            r"\d+"
            r"\s+"
            r"\d+(?:\.\d+)?['\"]?"
            r"\s+"
            r"\d+(?:\.\d+)?['\"]?"
        )

    return bool(
        re.search(
            pattern,
            line
        )
    )


def find_sample_table_start(
    lines: list[str]
) -> int | None:
    """
    Detect the beginning of the sample-data table.

    Detection uses common table-header terminology first,
    followed by a conservative numeric-row fallback.

    No form-specific schema is imposed.
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

    # Conservative fallback:
    # look for a line beginning with a sample number
    # followed by two depth-like numeric values.
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

    Supports multiple common descriptions so that
    different boring-log forms can be handled.

    No form-specific fields are created.
    """

    start_index = (
        sample_start + 1
        if sample_start is not None
        else 0
    )

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

    for i in range(
        start_index,
        len(lines)
    ):

        lower = lines[i].lower()

        for pattern in lithology_patterns:

            if pattern in lower:
                return i

    return None


def normalize_table_row(line: str) -> str:
    """
    Normalize clear table delimiters.

    Existing tabs are preserved.

    Multiple spaces are converted to a tab because
    they commonly represent column spacing in OCR output.

    Single spaces are NOT split because descriptions,
    project names, and handwritten text may contain spaces.
    """

    if "\t" in line:
        return line.strip()

    if re.search(r" {2,}", line):
        return re.sub(
            r" {2,}",
            "\t",
            line.strip()
        )

    return line.strip()


def normalize_table_rows(
    rows: list[str]
) -> list[str]:
    """
    Apply conservative table-row normalization.
    """

    return [
        normalize_table_row(row)
        for row in rows
    ]


def split_sections(cleaned_text: str) -> dict:
    """
    Split OCR output into generic document regions.

    The function does not define a form-specific schema.

    Table rows remain OCR content and are not parsed
    into individual business fields.
    """

    lines = cleaned_text.splitlines()

    sample_start = find_sample_table_start(
        lines
    )

    lithology_start = find_lithology_table_start(
        lines,
        sample_start
    )

    # --------------------------------------------------
    # Header
    # --------------------------------------------------

    if sample_start is not None:

        header = lines[:sample_start]

    else:

        header = lines

    # --------------------------------------------------
    # Sample Data Table
    # --------------------------------------------------

    if sample_start is not None:

        if lithology_start is not None:

            sample_data = lines[
                sample_start:lithology_start
            ]

        else:

            sample_data = lines[
                sample_start:
            ]

    else:

        sample_data = []

    sample_data = normalize_table_rows(
        sample_data
    )

    # --------------------------------------------------
    # Lithology Table
    # --------------------------------------------------

    next_section = None

    if lithology_start is not None:

        for i in range(
            lithology_start + 1,
            len(lines)
        ):

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

            if any(
                pattern in lower
                for pattern in known_section_patterns
            ):
                next_section = i
                break

        if next_section is not None:

            lithology = lines[
                lithology_start:next_section
            ]

        else:

            lithology = lines[
                lithology_start:
            ]

    else:

        lithology = []

    lithology = normalize_table_rows(
        lithology
    )

    # --------------------------------------------------
    # Remaining Sections
    # --------------------------------------------------

    boring_advancement = []
    surface_cover = []
    water_levels = []
    abandonment = []
    additional_remarks = []
    other_sections = []

    if next_section is not None:

        remaining_lines = lines[
            next_section:
        ]

        current_section = "other"
        current_content = []

        def save_section():
            """
            Save the currently collected section content.
            """

            if not current_content:
                return

            if current_section == "boring_advancement":

                boring_advancement.extend(
                    current_content
                )

            elif current_section == "surface_cover":

                surface_cover.extend(
                    current_content
                )

            elif current_section == "water_levels":

                water_levels.extend(
                    current_content
                )

            elif current_section == "abandonment":

                abandonment.extend(
                    current_content
                )

            elif current_section == "additional_remarks":

                additional_remarks.extend(
                    current_content
                )

            else:

                other_sections.append(
                    {
                        "name": current_section,
                        "content": current_content.copy()
                    }
                )

        for line in remaining_lines:

            lower = line.lower().strip()

            # ------------------------------------------
            # Boring Advancement
            # ------------------------------------------

            if (
                lower == "boring advancement"
                or "advancement and completion" in lower
            ):

                save_section()

                current_section = (
                    "boring_advancement"
                )

                current_content = []

                continue

            # ------------------------------------------
            # Surface Cover
            # ------------------------------------------

            if (
                lower == "surface cover & thickness"
                or "surface cover" in lower
            ):

                save_section()

                current_section = (
                    "surface_cover"
                )

                current_content = []

                continue

            # ------------------------------------------
            # Water Levels
            # ------------------------------------------

            if (
                lower == "water level observations"
                or lower == "water levels"
                or "water level" in lower
            ):

                save_section()

                current_section = (
                    "water_levels"
                )

                current_content = []

                continue

            # ------------------------------------------
            # Abandonment
            # ------------------------------------------

            if (
                lower == "boring abandonment"
                or "abandonment" in lower
            ):

                save_section()

                current_section = (
                    "abandonment"
                )

                current_content = []

                continue

            # ------------------------------------------
            # Additional Remarks
            # ------------------------------------------

            if (
                lower.startswith("additional remarks")
                or lower == "remarks"
                or lower.startswith("remarks:")
            ):

                save_section()

                current_section = (
                    "additional_remarks"
                )

                current_content = [line]

                continue

            # ------------------------------------------
            # Notes
            # ------------------------------------------

            if (
                lower == "notes:"
                or lower == "notes"
                or lower.startswith("notes:")
            ):

                save_section()

                current_section = "notes"

                current_content = [line]

                continue

            # ------------------------------------------
            # Other content
            # ------------------------------------------

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


def create_markdown(
    data: dict,
    document_name: str = "unknown"
) -> str:
    """
    Create Markdown with explicit section markers.

    Table rows are written directly under their section
    markers without Markdown code fences so that Person B's
    generic extractor can consume them directly.
    """

    md = []

    md.append(
        f"# Terracon Boring Log — {document_name}"
    )

    md.append("")

    md.append(
        "> OCR engine: GLM-OCR"
    )

    md.append("")

    md.append(
        "> OCR values are preserved without semantic correction."
    )

    md.append("")

    # --------------------------------------------------
    # Header
    # --------------------------------------------------

    md.append("## HEADER")
    md.append("")

    for line in data["header"]:
        md.append(line)

    md.append("")

    # --------------------------------------------------
    # Sample Data Table
    # --------------------------------------------------

    md.append("## SAMPLE_DATA_TABLE")
    md.append("")

    for line in data[
        "sample_data_table"
    ]["rows"]:

        md.append(line)

    md.append("")

    # --------------------------------------------------
    # Lithology Table
    # --------------------------------------------------

    md.append(
        "## LITHOLOGY_DATA_TABLE"
    )

    md.append("")

    for line in data[
        "lithology_data_table"
    ]["rows"]:

        md.append(line)

    md.append("")

    # --------------------------------------------------
    # Other Known Sections
    # --------------------------------------------------

    sections = [
        (
            "BORING_ADVANCEMENT",
            "boring_advancement"
        ),
        (
            "SURFACE_COVER_THICKNESS",
            "surface_cover_thickness"
        ),
        (
            "WATER_LEVEL_OBSERVATIONS",
            "water_level_observations"
        ),
        (
            "BORING_ABANDONMENT",
            "boring_abandonment"
        ),
        (
            "ADDITIONAL_REMARKS",
            "additional_remarks"
        ),
    ]

    for title, key in sections:

        if not data[key]:
            continue

        md.append(
            f"## {title}"
        )

        md.append("")

        for line in data[key]:
            md.append(line)

        md.append("")

    # --------------------------------------------------
    # Unknown / Additional Sections
    # --------------------------------------------------

    for section in data.get(
        "other_sections",
        []
    ):

        md.append(
            f"## {section['name']}"
        )

        md.append("")

        for line in section["content"]:
            md.append(line)

        md.append("")

    return "\n".join(md)


def save_outputs(
    raw_text: str,
    json_path: str,
    markdown_path: str,
    document_name: str = "unknown",
):
    """
    Save structured JSON and Markdown output.

    The document name is supplied dynamically by the pipeline.
    """

    cleaned_text = clean_text(
        raw_text
    )

    structured_data = split_sections(
        cleaned_text
    )

    output_json = {
        "document": document_name,
        "ocr_model": "GLM-OCR",
        "prompt": "Text Recognition:",
        "semantic_correction": False,
        "layout_preservation":
            "Best-effort section and table-region preservation",
        "sections": structured_data,
    }

    json_file = Path(
        json_path
    )

    markdown_file = Path(
        markdown_path
    )

    json_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    markdown_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------
    # Save JSON
    # --------------------------------------------------

    json_file.write_text(
        json.dumps(
            output_json,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    # --------------------------------------------------
    # Save Markdown
    # --------------------------------------------------

    markdown = create_markdown(
        structured_data,
        document_name
    )

    markdown_file.write_text(
        markdown,
        encoding="utf-8"
    )

    print(
        f"JSON saved: {json_file}"
    )

    print(
        f"Markdown saved: {markdown_file}"
    )

    return (
        str(json_file),
        str(markdown_file)
    )