"""Web UI for TranslateGemma powered by FastAPI."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import SUPPORTED_LANGUAGES, get_config
from .detector import detect_language, get_language_name

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

# Lazily initialised translator – model loading is expensive
_translator = None


def _get_translator(backend: str):
    """Return a cached Translator, initialising it on first call."""
    global _translator
    if _translator is None:
        from .translator import get_translator  # noqa: PLC0415

        _translator = get_translator(backend=backend if backend != "auto" else None)
    return _translator


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: RUF029
    logger.info("TranslateGemma Web UI starting up")
    yield
    logger.info("TranslateGemma Web UI shut down")


app = FastAPI(
    title="TranslateGemma Web UI",
    description="Offline-capable web interface for local neural translation",
    version="0.1.0",
    lifespan=lifespan,
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class TranslateRequest(BaseModel):
    text: str
    source_lang: str = "auto"
    target_lang: str = "auto"
    mode: str = "direct"
    backend: str = "auto"


class TranslateResponse(BaseModel):
    translation: str
    detected_source: str
    detected_source_name: str
    target_lang: str
    target_lang_name: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_ui():
    """Serve the main web UI page."""
    index = STATIC_DIR / "index.html"
    if index.exists():
        return HTMLResponse(content=index.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>TranslateGemma Web UI</h1><p>Run with static files present.</p>"
    )


@app.get("/api/health")
async def health():
    """Health-check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/languages")
async def get_languages():
    """Return the map of language codes → names."""
    return {"languages": SUPPORTED_LANGUAGES}


@app.get("/api/config")
async def read_config():
    """Return current active configuration."""
    cfg = get_config()
    return {
        "model_size": cfg.model_size,
        "languages": list(cfg.languages),
        "output_mode": cfg.output_mode,
        "backend_type": cfg.backend_type,
    }


@app.post("/api/translate", response_model=TranslateResponse)
async def translate(req: TranslateRequest):
    """Translate text between languages."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty")

    cfg = get_config()
    lang_pair = cfg.languages

    # Resolve source language
    source = req.source_lang
    if source == "auto":
        source = detect_language(req.text, list(lang_pair))

    # Resolve target language
    target = req.target_lang
    if target == "auto":
        target = lang_pair[1] if source == lang_pair[0] else lang_pair[0]

    if source == target:
        raise HTTPException(status_code=400, detail="source and target languages are the same")

    try:
        translator = _get_translator(req.backend)
        result = translator.translate(
            req.text,
            source_lang=source,
            target_lang=target,
            mode=req.mode,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Translation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return TranslateResponse(
        translation=result,
        detected_source=source,
        detected_source_name=get_language_name(source),
        target_lang=target,
        target_lang_name=get_language_name(target),
    )


# ---------------------------------------------------------------------------
# Entry-point for `python -m translategemma_cli.web`
# ---------------------------------------------------------------------------


def main():
    import uvicorn  # noqa: PLC0415

    host = os.environ.get("TRANSLATEGEMMA_HOST", "0.0.0.0")
    port = int(os.environ.get("TRANSLATEGEMMA_PORT", "8080"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
