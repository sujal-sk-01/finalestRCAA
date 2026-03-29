"""Minimal HTTP client for the RCAAgent-Env Space API (OpenEnv validation / local tests)."""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

DEFAULT_BASE = "http://127.0.0.1:8000"


class RCAAgentEnvClient:
    def __init__(self, base_url: Optional[str] = None, timeout: float = 600.0) -> None:
        self.base_url = (base_url or os.getenv("OPENENV_BASE_URL") or DEFAULT_BASE).rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def tasks(self) -> dict[str, Any]:
        r = self._client.get("/tasks")
        r.raise_for_status()
        return r.json()

    def reset(self, difficulty: str) -> dict[str, Any]:
        r = self._client.post(f"/reset/{difficulty}")
        r.raise_for_status()
        return r.json()

    def step(self, difficulty: str, action: dict[str, Any]) -> dict[str, Any]:
        r = self._client.post(f"/step/{difficulty}", json=action)
        r.raise_for_status()
        return r.json()

    def state(self, difficulty: str) -> dict[str, Any]:
        r = self._client.get(f"/state/{difficulty}")
        r.raise_for_status()
        return r.json()

    def grader(self, payload: dict[str, Any]) -> dict[str, Any]:
        r = self._client.post("/grader", json=payload)
        r.raise_for_status()
        return r.json()

    def baseline(self, difficulty: str) -> dict[str, Any]:
        r = self._client.get("/baseline", params={"difficulty": difficulty})
        r.raise_for_status()
        return r.json()
