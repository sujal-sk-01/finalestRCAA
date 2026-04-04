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
    return """You are an expert SRE engineer investigating a production incident.

STRATEGY - follow this exact order:
1. First check dependencies of api_gateway to find downstream services
2. Check metrics of ALL downstream services immediately
3. Find the service with status=down or cpu_usage > 0.9 - that is your root cause
4. Query logs of ONLY that root cause service
5. Submit RCA immediately - do not investigate further

RULES:
- Maximum 5 queries total before submitting
- root_cause_type must be ONE of: cpu_saturation, memory_leak, network, error_rate, crash, dependency_failure
- Do not repeat queries on same service
- Be decisive - submit after 4-5 steps

Your goal is accuracy AND efficiency."""


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
