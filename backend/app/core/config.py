from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Project paths
    PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]  # project root
    DATA_DIR: Path = PROJECT_ROOT / "data"
    IMAGES_DIR: Path = DATA_DIR / "images"
    GOLD_DIR: Path = DATA_DIR / "gold"
    OUTPUTS_DIR: Path = DATA_DIR / "outputs"
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    RAW_TEXT_DIR: Path = DATA_DIR / "outputs" / "postprocessed"
    STRUCTURED_DIR: Path = DATA_DIR / "outputs" / "structured"
    MANIFEST_FILE: Path = DATA_DIR / "outputs" / "manifest.json"

    # Model settings
    MODEL_NAME: str = "zai-org/GLM-OCR"
    DEVICE: str = "cpu"   # or "cuda" if you have GPU
    MAX_IMAGE_SIZE: int = 1600
    TILE_SIZE: int = 1024
    TILE_OVERLAP: int = 128

    # OCR thresholds
    CONFIDENCE_THRESHOLD: float = 0.6
    LOW_CONFIDENCE_THRESHOLD: float = 0.3

    # API settings
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8001

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()