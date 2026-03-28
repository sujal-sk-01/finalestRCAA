"""Single-flight Gemini client configuration and model handles (startup-friendly)."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv()

import os

import google.generativeai as genai

GEMINI_MODEL_ID = "gemini-2.0-flash"

_configured: bool = False
_baseline_model: genai.GenerativeModel | None = None
_grader_model: genai.GenerativeModel | None = None


def ensure_gemini_configured() -> bool:
    global _configured
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        return False
    if not _configured:
        genai.configure(api_key=key)
        _configured = True
    return True


def get_baseline_model() -> genai.GenerativeModel | None:
    global _baseline_model
    if not ensure_gemini_configured():
        return None
    if _baseline_model is None:
        _baseline_model = genai.GenerativeModel(GEMINI_MODEL_ID)
    return _baseline_model


def get_grader_model() -> genai.GenerativeModel | None:
    global _grader_model
    if not ensure_gemini_configured():
        return None
    if _grader_model is None:
        _grader_model = genai.GenerativeModel(GEMINI_MODEL_ID)
    return _grader_model
