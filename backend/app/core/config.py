from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # Project paths - Project root
    PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]

    DATA_DIR: Path = PROJECT_ROOT / "data"

    # Input
    UPLOAD_DIR: Path = DATA_DIR / "uploads"

    # Outputs
    OUTPUTS_DIR: Path = DATA_DIR / "outputs"

    PREPROCESSED_DIR: Path = OUTPUTS_DIR / "preprocessed"

    # GLM-OCR raw outputs
    GLM_RAW_TEXT_DIR: Path = (
        OUTPUTS_DIR / "glm_ocr" / "raw_text"
    )

    GLM_RAW_JSON_DIR: Path = (
        OUTPUTS_DIR / "glm_ocr" / "json"
    )

    # Postprocessed outputs
    POSTPROCESSED_RAW_TEXT_DIR: Path = (
        OUTPUTS_DIR / "postprocessed" / "raw_text"
    )

    POSTPROCESSED_JSON_DIR: Path = (
        OUTPUTS_DIR / "postprocessed" / "json"
    )

    POSTPROCESSED_MARKDOWN_DIR: Path = (
        OUTPUTS_DIR / "postprocessed" / "markdown"
    )

    # Final structured JSON
    FINAL_JSON_DIR: Path = (
        OUTPUTS_DIR / "final_json"
    )

    # Manifest
    MANIFEST_FILE: Path = (
        OUTPUTS_DIR / "manifest.json"
    )

    # Model settings
    MODEL_NAME: str = "zai-org/GLM-OCR"

    DEVICE: str = "cuda"

    MAX_IMAGE_SIZE: int = 1024

    TILE_SIZE: int = 1024

    TILE_OVERLAP: int = 128

    # OCR thresholds
    CONFIDENCE_THRESHOLD: float = 0.6

    LOW_CONFIDENCE_THRESHOLD: float = 0.3

    # API settings
    API_HOST: str = "0.0.0.0"

    API_PORT: int = 8001

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()