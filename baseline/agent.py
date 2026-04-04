"""Baseline agent: drives env.step() via OpenAI-compatible HF router."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
load_dotenv()

import json
import re
from typing import Any

from models import Action, ActionType
from server.environment import RCAEnvironment
from server.grader import grade
from server.llm import call_llm, is_llm_configured


def extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError("No valid JSON found in response")


def _system_prompt(services: list[str]) -> str:
    return """You are an SRE bot. You MUST respond with ONLY a JSON object, nothing else.

AVAILABLE ACTION TYPES:
- query_dependencies: {"action_type":"query_dependencies","target_service":"api_gateway"}
- query_metrics: {"action_type":"query_metrics","target_service":"SERVICE_NAME"}
- query_logs: {"action_type":"query_logs","target_service":"SERVICE_NAME"}
- submit_rca: {"action_type":"submit_rca","rca_report":{"root_cause_service":"NAME","root_cause_type":"cpu_saturation","affected_services":["a","b"],"confidence":0.9,"summary":"text","suggested_fix":"text"}}

STEPS:
1. query_dependencies on api_gateway
2. query_metrics on each downstream service
3. query_logs on the broken service
4. submit_rca

OUTPUT ONLY RAW JSON. NO MARKDOWN. NO EXPLANATION."""


def _parse_action(content: str) -> Action:
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    data = extract_json(text)
    return Action.model_validate(data)


def _generate_action(messages: list[dict[str, str]], prompt: str) -> str:
    return call_llm(
        prompt,
        system="You are an expert SRE performing root cause analysis. Respond only with valid JSON.",
    )


def run_baseline(difficulty: str) -> dict[str, Any]:
    if not is_llm_configured():
        return {
            "difficulty": difficulty,
            "steps": 0,
            "history": [],
            "report": None,
            "scores": None,
            "error": "HF_TOKEN is not set",
        }

    env = RCAEnvironment(difficulty)
    st = env.reset()
    services = list(st.service_metrics.keys())

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _system_prompt(services)},
        {
            "role": "user",
            "content": f"Incident alert:\n{st.alert}\n\nBegin investigation. Output only JSON Action.",
        },
    ]

    history: list[dict[str, Any]] = []
    steps = 0
    last_report = None

    for _ in range(25):
        steps += 1
        prompt = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in messages])
        try:
            raw = _generate_action(messages, prompt)
        except Exception as exc:
            return {
                "difficulty": difficulty,
                "steps": steps,
                "history": history,
                "report": None,
                "scores": None,
                "error": f"LLM API error: {exc!s}",
            }

        if not raw.strip():
            return {
                "difficulty": difficulty,
                "steps": steps,
                "history": history,
                "report": None,
                "scores": None,
                "error": "LLM returned empty response",
            }

        try:
            action = _parse_action(raw)
        except Exception:
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": "Invalid JSON or schema. Reply again with ONLY one JSON object matching the Action schema.",
                },
            )
        else:
            messages.append({"role": "assistant", "content": raw})
            obs = env.step(action)
            history.append(
                {
                    "action": action.model_dump(mode="json"),
                    "observation": obs.model_dump(mode="json"),
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": f"Observation:\n{obs.model_dump_json()}",
                }
            )

            if action.action_type == ActionType.SUBMIT_RCA and action.rca_report is not None:
                last_report = action.rca_report
                break

    scores: dict[str, Any] | None = None
    if last_report is not None:
        scores = grade(last_report, env.state(), env.raw_scenario)

    return {
        "difficulty": difficulty,
        "steps": steps,
        "history": history,
        "report": last_report.model_dump(mode="json") if last_report else None,
        "scores": scores,
    }
