"""Baseline agent: drives env.step() via OpenAI-compatible router."""
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


def _system_prompt() -> str:
    return """You are an SRE agent investigating a microservice incident. Reply with ONE JSON action only. No text, no markdown, no explanation.

INVESTIGATION STRATEGY:
1. Query dependencies on api_gateway first
2. Query metrics on services from the dependency list
3. Query logs on any service showing anomaly/degraded/down
4. Query dependencies on degraded services to find upstream cause
5. When you have enough evidence, submit_rca with the TRUE root cause

SUBMIT RCA FORMAT (all fields required):
{"action_type":"submit_rca","rca_report":{"root_cause_service":"ACTUAL_ROOT_SERVICE","root_cause_type":"TYPE","affected_services":["svc1","svc2"],"causal_chain":["root_svc","downstream_svc","api_gateway"],"confidence":0.9,"summary":"2-3 sentence description of what happened and why","suggested_fix":"Concrete steps to fix","fix_recommendation":"Concrete steps to fix"}}

root_cause_type must be one of: latency|error_rate|crash|memory_leak|network|dependency_failure|ddos

RULES:
- NEVER query the same service+action twice
- Prioritize services with Status=down or Error Rate > 50%
- The service with highest error rate or Status=down is likely root cause
- Raw JSON only, no markdown"""


def _make_rca(service: str, affected: list, chain: list) -> Action:
    data = {
        "action_type": "submit_rca",
        "rca_report": {
            "root_cause_service": service,
            "root_cause_type": "error_rate",
            "affected_services": affected if affected else [service, "api_gateway"],
            "causal_chain": chain if chain else [service, "api_gateway"],
            "confidence": 0.85,
            "summary": f"Service {service} is experiencing high error rates causing cascading failures across dependent services leading to degraded user experience.",
            "suggested_fix": f"1. Restart {service} pod/container. 2. Scale up {service} replicas. 3. Check {service} dependencies and database connections. 4. Monitor error rates after restart.",
            "fix_recommendation": f"1. Restart {service} pod/container. 2. Scale up {service} replicas. 3. Check {service} dependencies and database connections. 4. Monitor error rates after restart."
        }
    }
    return Action.model_validate(data)


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

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": f"Incident Alert: {st.alert}\n\nBegin investigation. Output only JSON."},
    ]

    history: list[dict[str, Any]] = []
    steps = 0
    last_report = None
    queried: set[str] = set()

    worst_service = "unknown"
    worst_error_rate = 0.0
    worst_cpu = 0.0
    affected_services: list[str] = []
    anomalous_services: list[str] = []

    max_steps = st.max_queries if hasattr(st, 'max_queries') else 25

    for _ in range(max_steps):
        steps += 1

        prompt = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in messages[-6:]])
        try:
            raw = call_llm(prompt, system=_system_prompt(), max_tokens=400)
        except Exception as exc:
            return {"difficulty": difficulty, "steps": steps, "history": history, "report": None, "scores": None, "error": str(exc)}

        if not raw.strip():
            action = _make_rca(worst_service, affected_services, anomalous_services)
        else:
            try:
                action = _parse_action(raw)
            except Exception:
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": "Invalid JSON. Reply with ONE JSON object only. No markdown."})
                continue

        # Block repeated actions
        key = f"{action.action_type}:{getattr(action, 'target_service', '')}"
        if key in queried and action.action_type != ActionType.SUBMIT_RCA:
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"You already did {key}. Choose a DIFFERENT service or action. Output JSON only."})
            continue
        queried.add(key)

        messages.append({"role": "assistant", "content": json.dumps(action.model_dump(mode="json"))})
        obs = env.step(action)

        # Track evidence from observations
        if hasattr(obs, 'metrics') and obs.metrics and action.target_service:
            m = obs.metrics
            err = getattr(m, 'error_rate', 0) or 0
            cpu = getattr(m, 'cpu_percent', 0) or 0
            status = getattr(m, 'status', 'healthy')

            if action.target_service not in affected_services:
                affected_services.append(action.target_service)

            if status in ('degraded', 'down') or err > 0.1:
                if action.target_service not in anomalous_services:
                    anomalous_services.append(action.target_service)

            if err > worst_error_rate or status == 'down':
                worst_error_rate = err
                worst_service = action.target_service

            if cpu > worst_cpu:
                worst_cpu = cpu

            # Auto-submit if critical service found
            if (status == 'down' or err >= 0.8) and action.target_service:
                worst_service = action.target_service
                chain = anomalous_services if anomalous_services else [worst_service, "api_gateway"]
                forced = _make_rca(worst_service, affected_services, chain)
                obs2 = env.step(forced)
                last_report = forced.rca_report
                history.append({
                    "action": action.model_dump(mode="json"),
                    "observation": obs.model_dump(mode="json"),
                })
                history.append({
                    "action": forced.model_dump(mode="json"),
                    "observation": obs2.model_dump(mode="json"),
                })
                break

        if hasattr(obs, 'anomaly_detected') and obs.anomaly_detected and action.target_service:
            if action.target_service not in anomalous_services:
                anomalous_services.append(action.target_service)
            worst_service = action.target_service

        history.append({
            "action": action.model_dump(mode="json"),
            "observation": obs.model_dump(mode="json"),
        })
        messages.append({"role": "user", "content": f"Observation: {obs.model_dump_json()}\n\nAnomalous services found so far: {anomalous_services}. Continue investigation or submit_rca if you have enough evidence."})

        if action.action_type == ActionType.SUBMIT_RCA and action.rca_report is not None:
            last_report = action.rca_report
            break

    # If agent never submitted, force it
    if last_report is None:
        chain = anomalous_services if anomalous_services else [worst_service, "api_gateway"]
        forced = _make_rca(worst_service, affected_services, chain)
        obs = env.step(forced)
        last_report = forced.rca_report
        history.append({
            "action": forced.model_dump(mode="json"),
            "observation": obs.model_dump(mode="json"),
        })

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