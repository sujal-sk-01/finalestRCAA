from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from models import Action, ActionType, RCAReport
from server.environment import RCAEnvironment
from server.grader import grade

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")
load_dotenv()


def log_start(task: str, env: str, model: str):
    print(json.dumps({
        "type": "START",
        "task": task,
        "env": env,
        "model": model
    }), flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error):
    print(json.dumps({
        "type": "STEP",
        "step": step,
        "action": action,
        "reward": reward,
        "done": done,
        "error": error
    }), flush=True)


def log_end(success: bool, steps: int, score: float, rewards: list):
    print(json.dumps({
        "type": "END",
        "success": success,
        "steps": steps,
        "score": score,
        "rewards": rewards
    }), flush=True)


API_BASE_URL = os.getenv("API_BASE_URL", "")
MODEL_NAME = os.getenv("MODEL_NAME", "")
HF_TOKEN = os.getenv("HF_TOKEN", "")

MAX_STEPS = 12
TASKS = ("easy", "medium", "hard")


def _make_client() -> OpenAI | None:
    if not API_BASE_URL or not MODEL_NAME or not HF_TOKEN:
        return None
    return OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)


def _build_prompt(state, history: list[str]) -> str:
    metrics_summary = []
    for svc, m in state.service_metrics.items():
        metrics_summary.append(
            f"{svc}: status={m.status}, error_rate={m.error_rate:.2%}, latency_p99={m.latency_p99_ms}ms"
        )
    return (
        "You are an SRE investigating an incident.\n"
        f"ALERT: {state.alert}\n"
        f"QUERIES_REMAINING: {state.queries_remaining}/{state.max_queries}\n"
        "SERVICES:\n"
        + "\n".join(metrics_summary)
        + "\nHISTORY:\n"
        + ("\n".join(history[-8:]) if history else "none")
        + "\nReturn ONLY JSON Action with one of: query_metrics, query_logs, pull_traces, query_dependencies, form_hypothesis, submit_rca."
    )


def _parse_action(raw: str) -> Action:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else ""
    try:
        data = json.loads(text)
        if isinstance(data.get("rca_report"), dict):
            data["rca_report"] = RCAReport(**data["rca_report"])
        return Action.model_validate(data)
    except Exception:
        return Action(action_type=ActionType.FORM_HYPOTHESIS, hypothesis="Fallback hypothesis")


def _fallback_action(state) -> Action:
    if state.queries_remaining <= 1:
        return Action(
            action_type=ActionType.SUBMIT_RCA,
            rca_report=RCAReport(
                root_cause_service="unknown",
                root_cause_type="unknown",
                affected_services=[],
                causal_chain=["insufficient_signal"],
                summary="Fallback submission due to budget constraints.",
                suggested_fix="Increase observability and retry.",
                confidence=0.2,
            ),
        )
    service_names = list(state.service_metrics.keys())
    target = service_names[min(len(service_names) - 1, max(0, len(service_names) // 2))]
    return Action(action_type=ActionType.QUERY_METRICS, target_service=target)


def run_task(task: str, client: OpenAI | None) -> dict:
    env_name = "RCAEnvironment"
    log_start(task, env_name, MODEL_NAME or "unset")
    env = RCAEnvironment(task)
    state = env.reset()
    history: list[str] = []
    rewards: list[float] = []
    success = False
    final_score = 0.0
    steps = 0
    last_report: RCAReport | None = None
    start = time.time()
    max_runtime_per_task = 360

    try:
        for i in range(1, MAX_STEPS + 1):
            if time.time() - start > max_runtime_per_task:
                log_step(i, "timeout", 0.0, True, "task_timeout")
                break

            action = _fallback_action(state)
            error = None
            if client is not None:
                try:
                    prompt = _build_prompt(state, history)
                    resp = client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=[
                            {"role": "system", "content": "Output valid JSON action only."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0,
                        max_tokens=500,
                    )
                    raw = resp.choices[0].message.content or ""
                    action = _parse_action(raw)
                except Exception as e:
                    error = str(e)

            obs = env.step(action)
            state = env.state()
            steps = i
            step_reward = float(obs.reward.step_reward if obs.reward else 0.0)
            rewards.append(step_reward)
            done = bool(obs.reward.done) if obs.reward else False
            log_step(i, action.action_type.value, step_reward, done, error)
            history.append(f"{i}:{action.action_type.value}:{obs.message}")

            if action.action_type == ActionType.SUBMIT_RCA and obs.success:
                last_report = action.rca_report
                success = True
                break

            if state.queries_remaining <= 0:
                break

        if last_report is None:
            last_report = RCAReport(
                root_cause_service="unknown",
                root_cause_type="unknown",
                affected_services=[],
                causal_chain=["fallback_submission"],
                summary="No RCA submitted by agent.",
                suggested_fix="Increase query budget and re-run.",
                confidence=0.1,
            )
        scores = grade(last_report, env.state(), env.raw_scenario)
        final_score = float(scores.get("final_score", 0.0))
    finally:
        log_end(success, steps, final_score, rewards)

    return {
        "task": task,
        "success": success,
        "steps": steps,
        "score": final_score,
        "rewards": rewards,
    }


def main() -> None:
    client = _make_client()
    results = [run_task(task, client) for task in TASKS]
    with (_ROOT / "inference_results.json").open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
