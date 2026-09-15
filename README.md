# Terracon Boring Log Extraction

## Overview

This project is a Proof of Concept (POC) for extracting information
from Terracon handwritten boring-log images using GLM-OCR.

The pipeline focuses on:

- Image validation
- Lightweight image preprocessing
- OCR extraction
- Conservative post-processing
- JSON output
- Markdown output
- Best-effort preservation of document sections and table regions

---

## Pipeline

```text
Boring Log Image
       |
       v
Image Validation
       |
       v
Image Preprocessing
       |
       v
GLM-OCR
       |
       v
Post-Processing
       |
       +------------+
       |            |
       v            v
     JSON       Markdown