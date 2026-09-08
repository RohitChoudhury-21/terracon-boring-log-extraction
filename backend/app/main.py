from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import router
from .core.config import settings
from .core.logging import setup_logging

# Setup logging
setup_logging()

# Create FastAPI app
app = FastAPI(
    title="Terracon Boring Log OCR Extraction",
    description="API for extracting structured data from boring log images",
    version="0.1.0",
)

settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.RAW_TEXT_DIR.mkdir(parents=True, exist_ok=True)
settings.STRUCTURED_DIR.mkdir(parents=True, exist_ok=True)
settings.MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)

# CORS middleware (adjust origins for frontend later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to specific origins in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api", tags=["extraction"])

# Root endpoint (optional)
@app.get("/")
async def root():
    return {
        "message": "Terracon Boring Log OCR Extraction API",
        "docs": "/docs",
        "health": "/api/health",
    }