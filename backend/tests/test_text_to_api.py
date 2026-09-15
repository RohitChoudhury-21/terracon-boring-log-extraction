import pytest
from backend.app.extraction.field_extractor import extract_fields
from backend.app.schemas.boring_log_schema import Document


RAW_TEXT = """
## HEADER
Boring No.: 1-1185R-A
Project No.: 1A235046
Project Name: West Al Hwy
Offset(s): N/A
Operator: Challenge (Hilliard)
Logger: Connor Riley
Rig No.: 2
Rig Type: CME 45

## BORING_ADVANCEMENT
Start Date: 8-6-24
Start Time: 9:20 AM
Finish Date: 8-6-24
Finish Time: 10:15 AM
20' HSA

## SAMPLE_DATA_TABLE
1   0'   2'   SS   -   2   3   5   4   12"   -   -
2   2'   4'   SS   -   4   5   6   7   20"   -   -
3   4'   6'   ST   -   -   -   -   -   -   -   -
4   6'   8'   ST   -   -   -   -   -   -   -   -
5   8'   10'  SS   -   5   8   10  11  24"   -   -
6   13'  15'  SS   -   9   19  19  20  24"   -   -
7   18'  20'  SS   -   9   12  19  22  24"   -   -

## LITHOLOGY_DATA_TABLE
0'   2'   fat clay w/ sand (CH) dry-moist d.gray & d.tan
2'   4'   " becomes l.tan w/ gray
4'   6'   Shelby Rec=21"
6'   8'   Shelby Rec=0"
8'   20'  d.gray lean clay w/ sand (CL) dry - moist
Term at 20'

## SURFACE_COVER_THICKNESS
Topsoil: 3"

## WATER_LEVEL_OBSERVATIONS
First Encountered: -
At Completion: -
feet_on_1: 6.1'
date_1: 8-7
Cave In checkbox: CHECKED
Cave In Depth: 13.5'
Artesian checkbox: UNCHECKED

## BORING_ABANDONMENT
Cuttings checkbox: CHECKED
Other: 24 hr GW

## ADDITIONAL_REMARKS
- attempted 2 tubes from 6'-8', no recovery either time

## SHEET_INFO
Sheet: 1 of 1
"""


def test_sample_table_extraction():
    doc = extract_fields(RAW_TEXT)
    assert isinstance(doc, Document)

    sample_section = doc.get_section("Sample Data Table")
    assert sample_section is not None
    assert sample_section.type == "table"
    rows = sample_section.rows
    assert len(rows) == 7

    # Columns may be generic or derived from header; we'll access by index
    row1 = rows[0]
    # Since columns are dynamic, we use key names if known, else fallback.
    # For this test, we can assume standard column names if parser inferred them.
    # If not, adapt accordingly.
    # Check that row is a dict and contains some expected values
    assert any(str(value) == "1" for value in row1.values())
    assert any(str(value) == "SS" for value in row1.values())
    assert any(str(value) == "12\"" for value in row1.values())

    # For row3 (ST), should have no blow counts
    row3 = rows[2]
    assert any(str(value) == "3" for value in row3.values())
    assert any(str(value) == "ST" for value in row3.values())


def test_lithology_extraction():
    doc = extract_fields(RAW_TEXT)
    lith_section = doc.get_section("Lithology / Sample Description Table")
    assert lith_section is not None
    assert lith_section.type == "table"
    rows = lith_section.rows
    assert len(rows) >= 5
    # Check first row has "fat clay" somewhere
    first_row = rows[0]
    assert any("fat clay" in str(value).lower() for value in first_row.values())


def test_header_extraction():
    doc = extract_fields(RAW_TEXT)
    header_section = doc.get_section("Header")
    assert header_section is not None
    assert header_section.type == "key_value"
    fields = header_section.fields
    assert fields["Boring No."] == "1-1185R-A"
    assert fields["Project No."] == "1A235046"
    assert fields["Operator"] == "Challenge (Hilliard)"