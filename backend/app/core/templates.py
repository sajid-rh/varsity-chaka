"""Jinja2 setup. Templates live in frontend/templates, which the frontend developer owns."""
from pathlib import Path

from fastapi.templating import Jinja2Templates

# backend/app/core/templates.py -> repo root is three levels above "core"
FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"

# Jinja2 escapes HTML in {{ values }} by default, which blocks stored XSS from user input
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))
