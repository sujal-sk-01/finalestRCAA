<<<<<<< HEAD
"""Baseline agent: drives env.step() via OpenAI-compatible HF router."""
=======
"""Google Gemini baseline agent: drives env.step() in a reproducible loop."""
>>>>>>> 1e0c61bd756a3c13d37981bdfb8d422f6cc010d6

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

<<<<<<< HEAD
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
=======
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv()

import json
import os
import re
from typing import Any

import google.generativeai as genai

from models import Action, ActionType
from server.environment import RCAEnvironment
from server.grader import grade
from server.llm import get_baseline_model
>>>>>>> 1e0c61bd756a3c13d37981bdfb8d422f6cc010d6


def extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError("No valid JSON found in response")


def _system_prompt(services: list[str]) -> str:
<<<<<<< HEAD
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
=======
    svc = ", ".join(services)
    return f"""You are an on-call SRE debugging a production incident in a microservice system.

Available services: {svc}

You may take ONE action per turn. Respond with a single JSON object (no markdown) matching this schema:
{{
  "action_type": one of [
    "query_metrics",
    "query_logs",
    "pull_traces",
    "query_dependencies",
    "form_hypothesis",
    "submit_rca"
  ],
  "target_service": "<service name or null>",
  "hypothesis": "<string or null; required when action_type is form_hypothesis>",
  "rca_report": null OR {{
    "root_cause_service": "<string>",
    "root_cause_type": "<string>",
    "affected_services": ["<service>", "..."],
    "causal_chain": ["<root first, then downstream, ...>"],
    "summary": "<string>",
    "fix_recommendation": "<string>",
    "confidence": <float 0.0-1.0>
  }}
}}

Rules:
- For query_metrics, query_logs, pull_traces, query_dependencies: set target_service to a valid service name.
- Start by investigating api_gateway, then follow dependencies and anomalies.
- Be strategic: correlate metrics, logs, and traces before forming conclusions.
- Use form_hypothesis to record intermediate theories.
- Only use submit_rca when you are confident; rca_report must be complete.
- Your entire reply MUST be valid JSON parsable as an Action.
"""
>>>>>>> 1e0c61bd756a3c13d37981bdfb8d422f6cc010d6


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


<<<<<<< HEAD
def _generate_action(messages: list[dict[str, str]], prompt: str) -> str:
    return call_llm(
        prompt,
        system="You are an expert SRE performing root cause analysis. Respond only with valid JSON.",
    )


def run_baseline(difficulty: str) -> dict[str, Any]:
    if not is_llm_configured():
=======
def _generate_action(model: Any, messages: list[dict[str, str]], prompt: str) -> str:
    try:
        gc = genai.types.GenerationConfig(temperature=0)
        resp = model.generate_content(prompt, generation_config=gc)
    except Exception:
        resp = model.generate_content(prompt)
    return (resp.text or "").strip()


def run_baseline(difficulty: str) -> dict[str, Any]:
    if not os.getenv("GOOGLE_API_KEY"):
>>>>>>> 1e0c61bd756a3c13d37981bdfb8d422f6cc010d6
        return {
            "difficulty": difficulty,
            "steps": 0,
            "history": [],
            "report": None,
            "scores": None,
<<<<<<< HEAD
            "error": "HF_TOKEN is not set",
=======
            "error": "GOOGLE_API_KEY is not set",
        }

    model = get_baseline_model()
    if model is None:
        return {
            "difficulty": difficulty,
            "steps": 0,
            "history": [],
            "report": None,
            "scores": None,
            "error": "Gemini client not configured",
>>>>>>> 1e0c61bd756a3c13d37981bdfb8d422f6cc010d6
        }

    env = RCAEnvironment(difficulty)
    st = env.reset()
<<<<<<< HEAD
    services = list(st.service_metrics.keys())
=======
    services = list(st.services.keys())
>>>>>>> 1e0c61bd756a3c13d37981bdfb8d422f6cc010d6

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
<<<<<<< HEAD
            raw = _generate_action(messages, prompt)
=======
            raw = _generate_action(model, messages, prompt)
>>>>>>> 1e0c61bd756a3c13d37981bdfb8d422f6cc010d6
        except Exception as exc:
            return {
                "difficulty": difficulty,
                "steps": steps,
                "history": history,
                "report": None,
                "scores": None,
<<<<<<< HEAD
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
=======
                "error": f"Gemini API error: {exc!s}",
>>>>>>> 1e0c61bd756a3c13d37981bdfb8d422f6cc010d6
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
<<<<<<< HEAD
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
=======
            continue

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

        if action.action_type == ActionType.submit_rca and action.rca_report is not None:
            last_report = action.rca_report
            break
>>>>>>> 1e0c61bd756a3c13d37981bdfb8d422f6cc010d6

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
