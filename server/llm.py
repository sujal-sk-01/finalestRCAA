"""LLM client using OpenAI-compatible interface pointed at Hugging Face router."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
load_dotenv()

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=os.environ.get("API_BASE_URL", "https://api-inference.huggingface.co/v1"),
            api_key=os.environ.get("HF_TOKEN", ""),
        )
    return _client


def is_llm_configured() -> bool:
    return bool(os.environ.get("HF_TOKEN"))


def call_llm(
    prompt: str,
    system: str | None = None,
    json_mode: bool = False,
    max_tokens: int = 1000,
) -> str:
    try:
        client = _get_client()
        model = os.environ.get("MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = dict(model=model, messages=messages, max_tokens=max_tokens, temperature=0)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
    except Exception as e:
        raise Exception(f"LLM call failed: {e}")

