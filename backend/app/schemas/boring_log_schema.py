from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field

# ============================================================
# Generic Document Schema (New – template-agnostic)
# ============================================================

SectionType = Literal["key_value", "table", "raw_text"]

class Section(BaseModel):
    name: str
    type: SectionType
    # For key_value sections:
    fields: Optional[Dict[str, Optional[str]]] = None
    # For table sections:
    columns: Optional[List[str]] = None
    rows: Optional[List[Dict[str, Optional[str]]]] = None
    # For raw_text sections:
    text: Optional[str] = None
    # Preserve original OCR text for review
    raw_text: Optional[str] = None

class Document(BaseModel):
    sections: List[Section] = Field(default_factory=list)

    def get_section(self, name: str) -> Optional[Section]:
        """Return the first section with the given name (case-insensitive)."""
        for sec in self.sections:
            if sec.name.lower() == name.lower():
                return sec
        return None

# ============================================================
# Legacy Models (kept for backward compatibility with old saved JSON)
# ============================================================

class Header(BaseModel):
    Boring_No: Optional[str] = None
    Project_No: Optional[str] = None
    Project_Name: Optional[str] = None
    Latitude: Optional[str] = None
    Longitude: Optional[str] = None
    Surface_Elevation: Optional[str] = None
    Offset: Optional[str] = None
    Operator: Optional[str] = None
    Logger: Optional[str] = None
    Project_Manager: Optional[str] = None
    Rig_No: Optional[str] = None
    Rig_Type: Optional[str] = None
    Remarks: Optional[str] = None

class AdvancementRow(BaseModel):
    Depth: Optional[str] = None
    Method: Optional[str] = None

class BoringAdvancement(BaseModel):
    Start_Date: Optional[str] = None
    Start_Time: Optional[str] = None
    Finish_Date: Optional[str] = None
    Finish_Time: Optional[str] = None
    advancement_rows: List[AdvancementRow] = Field(default_factory=list)

class SampleDataRow(BaseModel):
    sample_no: Optional[str] = None
    from_depth: Optional[str] = None
    to_depth: Optional[str] = None
    type: Optional[str] = None
    collection_time: Optional[str] = None
    blow_1: Optional[str] = None
    blow_2: Optional[str] = None
    blow_3: Optional[str] = None
    blow_4: Optional[str] = None
    recovery: Optional[str] = None
    Unknown1: Optional[str] = None
    Unknown2: Optional[str] = None

class LithologyRow(BaseModel):
    depth_from: Optional[str] = None
    depth_to: Optional[str] = None
    description: Optional[str] = None

class SurfaceCoverThickness(BaseModel):
    Vegetation: Optional[str] = None
    Topsoil: Optional[str] = None
    Fill: Optional[str] = None
    Asphalt: Optional[str] = None
    Concrete: Optional[str] = None
    Aggregate: Optional[str] = None

class WaterLevelObservations(BaseModel):
    First_Encountered: Optional[str] = None
    At_Completion: Optional[str] = None
    feet_on_1: Optional[str] = None
    date_1: Optional[str] = None
    feet_on_2: Optional[str] = None
    date_2: Optional[str] = None
    feet_on_3: Optional[str] = None
    date_3: Optional[str] = None
    Water_Loss_From: Optional[str] = None
    Water_Loss_To: Optional[str] = None
    Water_Loss_Percent: Optional[str] = None
    Cave_In_checkbox: Optional[str] = None
    Cave_In_Depth: Optional[str] = None
    Artesian_checkbox: Optional[str] = None
    Height: Optional[str] = None

class BoringAbandonment(BaseModel):
    Cuttings: Optional[str] = None
    Cuttings_checkbox: Optional[str] = None
    Grout: Optional[str] = None
    Grout_checkbox: Optional[str] = None
    Well_Constructed_checkbox: Optional[str] = None
    Bentonite_Chips_checkbox: Optional[str] = None
    Sand: Optional[str] = None
    Sand_checkbox: Optional[str] = None
    Other: Optional[str] = None
    Other_checkbox: Optional[str] = None

class BoringLog(BaseModel):
    header: Optional[Header] = None
    boring_advancement: Optional[BoringAdvancement] = None
    sample_data_table: List[SampleDataRow] = Field(default_factory=list)
    lithology_data_table: List[LithologyRow] = Field(default_factory=list)
    surface_cover_thickness: Optional[SurfaceCoverThickness] = None
    water_level_observations: Optional[WaterLevelObservations] = None
    boring_abandonment: Optional[BoringAbandonment] = None
    additional_remarks: Optional[str] = None
    sheet: Optional[str] = None
    sheet_of: Optional[str] = None
    Grout: Optional[str] = None
    Grout_checkbox: Optional[str] = None
    Well_Constructed_checkbox: Optional[str] = None
    Bentonite_Chips_checkbox: Optional[str] = None
    Sand: Optional[str] = None
    Sand_checkbox: Optional[str] = None
    Other: Optional[str] = None
    Other_checkbox: Optional[str] = None