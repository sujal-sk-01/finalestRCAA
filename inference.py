"""
inference.py — Hackathon submission entry point.

Runs the RCA baseline agent on all three difficulties (easy/medium/hard)
using the OpenAI-compatible client pointed at HuggingFace inference router.

Environment variables required:
  API_BASE_URL  — e.g. https://router.huggingface.co/v1
  MODEL_NAME    — e.g. meta-llama/Llama-3.3-70B-Instruct
  HF_TOKEN      — your HuggingFace API token

Runtime: < 20 minutes on 2 vCPU / 8 GB RAM
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve()
load_dotenv(_ROOT.parent / ".env")
load_dotenv()

required_vars = ["API_BASE_URL", "MODEL_NAME", "HF_TOKEN"]
missing = [v for v in required_vars if not os.environ.get(v)]
if missing:
    raise EnvironmentError(
        f"Missing required environment variables: {missing}\n"
        f"Set them in .env or export them before running."
    )

from openai import OpenAI

from models import Action, ActionType, RCAReport
from server.environment import RCAEnvironment
from server.grader import grade

client = OpenAI(
    base_url=os.environ["API_BASE_URL"],
    api_key=os.environ["HF_TOKEN"],
)
MODEL = os.environ["MODEL_NAME"]


def call_llm(prompt: str, system: str | None = None) -> str:
    """OpenAI-compatible LLM call."""
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=1000,
            temperature=0,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"  LLM error: {e}")
        return ""


def parse_action(text: str) -> Action:
    """Parse LLM output into a typed Action, with fallback."""
    try:
        clean = text.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(clean)
        if isinstance(data.get("rca_report"), dict):
            data["rca_report"] = RCAReport(**data["rca_report"])
        return Action.model_validate(data)
    except Exception:
        return Action(
            action_type=ActionType.FORM_HYPOTHESIS,
            hypothesis=f"Parse failed. Raw: {text[:200]}",
        )


def build_prompt(state, history: list) -> str:
    services = list(state.service_metrics.keys())
    metrics_summary = []
    for svc, m in state.service_metrics.items():
        metrics_summary.append(
            f"  {svc}: status={m.status}, error_rate={m.error_rate:.2%}, "
            f"latency_p99={m.latency_p99_ms}ms"
        )

    return f"""You are an expert SRE investigating a production incident.

ALERT: {state.alert}

SERVICES AND CURRENT STATUS:
{chr(10).join(metrics_summary)}

QUERIES REMAINING: {state.queries_remaining}/{state.max_queries}

INVESTIGATION HISTORY (last 8 steps):
{chr(10).join(history[-8:]) if history else "No investigation yet."}

INSTRUCTIONS:
- Investigate systematically: check metrics, logs, traces, dependencies
- Form hypotheses to record your reasoning (free, no budget cost)
- When confident, submit your RCA
- Be efficient: you have limited queries

RESPOND WITH VALID JSON ONLY. Choose one action:

Query a service:
{{"action_type": "query_metrics", "target_service": "<name>"}}
{{"action_type": "query_logs", "target_service": "<name>"}}
{{"action_type": "pull_traces", "target_service": "<name>"}}
{{"action_type": "query_dependencies", "target_service": "<name>"}}

Record reasoning (free):
{{"action_type": "form_hypothesis", "hypothesis": "<your reasoning>"}}

Submit final analysis:
{{"action_type": "submit_rca", "rca_report": {{
  "root_cause_service": "<service_name>",
  "root_cause_type": "<latency|error_rate|crash|memory_leak|network|dependency_failure>",
  "affected_services": ["<svc1>", "<svc2>"],
  "causal_chain": ["<event1>", "<event2>", "<event3>"],
  "summary": "<2-3 sentence summary>",
  "suggested_fix": "<concrete remediation steps>",
  "confidence": 0.85
}}}}

Available services: {services}
JSON only, no explanation:"""


def run_for_difficulty(difficulty: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  DIFFICULTY: {difficulty.upper()}")
    print(f"{'='*60}")

    env = RCAEnvironment(difficulty)
    state = env.reset()

    print(f"  Scenario: {state.scenario_id}")
    print(f"  Alert:    {state.alert}")
    print(f"  Budget:   {state.max_queries} queries")

    history = []
    last_report = None
    start_time = time.time()
    MAX_STEPS = 18

    for step_num in range(MAX_STEPS):
        elapsed = time.time() - start_time
        if elapsed > 360:
            print(f"  Time limit reached at step {step_num}")
            break

        prompt = build_prompt(state, history)
        raw = call_llm(
            prompt,
            system="You are an expert SRE. Respond only with valid JSON, no markdown, no explanation.",
        )

        if not raw:
            print(f"  Step {step_num+1}: LLM returned empty — skipping")
            continue

        action = parse_action(raw)
        observation = env.step(action)
        state = env.state()

        entry = f"[{step_num+1}] {action.action_type.value}"
        if action.target_service:
            entry += f"({action.target_service})"
        entry += f" -> {'OK' if observation.success else 'FAIL'} {observation.message[:120]}"
        if observation.reward:
            entry += f" [reward={observation.reward.step_reward:+.3f}]"
        history.append(entry)
        print(f"  {entry}")

        if action.action_type == ActionType.SUBMIT_RCA and observation.success:
            last_report = action.rca_report
            cum = observation.reward.cumulative_reward if observation.reward else "N/A"
            print(f"\n  RCA submitted. Cumulative reward: {cum}")
            break

        if state.queries_remaining is not None and state.queries_remaining <= 1:
            print(f"\n  Budget nearly exhausted — stopping loop")
            break

    if last_report is None:
        print("  No RCA submitted — using fallback report")
        last_report = RCAReport(
            root_cause_service="unknown",
            root_cause_type="unknown",
            affected_services=[],
            causal_chain=["Investigation did not complete within budget"],
            summary="Agent exhausted query budget without submitting RCA.",
            suggested_fix="Increase query budget or improve agent efficiency.",
            confidence=0.0,
        )

    final_state = env.state()
    scores = grade(last_report, final_state, env.raw_scenario)

    elapsed = time.time() - start_time
    print(f"\n  SCORES:")
    print(f"     final_score:        {scores.get('final_score', 0):.4f}")
    print(f"     root_cause_score:   {scores.get('root_cause_score', 0):.4f}")
    print(f"     causal_path_score:  {scores.get('causal_path_score', 0):.4f}")
    print(f"     efficiency_score:   {scores.get('efficiency_score', 0):.4f}")
    print(f"     report_quality:     {scores.get('report_quality_score', 0):.4f}")
    print(f"     time_elapsed:       {elapsed:.1f}s")

    return {
        "difficulty": difficulty,
        "scenario_id": state.scenario_id,
        "scores": scores,
        "steps_taken": len(history),
        "time_elapsed_seconds": round(elapsed, 1),
    }


def main() -> None:
    print("SRE RCA Environment — Inference Script")
    print(f"   API_BASE_URL : {os.environ.get('API_BASE_URL')}")
    print(f"   MODEL_NAME   : {os.environ.get('MODEL_NAME')}")
    print(f"   HF_TOKEN     : {'set' if os.environ.get('HF_TOKEN') else 'MISSING'}")

    start = time.time()
    results = []

    for difficulty in ["easy", "medium", "hard"]:
        try:
            result = run_for_difficulty(difficulty)
            results.append(result)
        except Exception as e:
            print(f"\nError on {difficulty}: {e}")
            import traceback

            traceback.print_exc()
            results.append(
                {
                    "difficulty": difficulty,
                    "error": str(e),
                    "scores": {"final_score": 0.0},
                }
            )

    total_elapsed = time.time() - start

    print(f"\n{'='*60}")
    print("  FINAL RESULTS SUMMARY")
    print(f"{'='*60}")
    for r in results:
        if "error" in r:
            print(f"  {r['difficulty']:8s} -> ERROR: {r['error']}")
        else:
            fs = r["scores"].get("final_score", 0)
            steps = r.get("steps_taken", "?")
            t = r.get("time_elapsed_seconds", "?")
            print(f"  {r['difficulty']:8s} -> final_score={fs:.4f}  steps={steps}  time={t}s")

    print(f"\n  Total runtime: {total_elapsed:.1f}s")
    assert total_elapsed < 1200, f"Runtime {total_elapsed:.0f}s exceeds 20 minute limit!"

    for r in results:
        fs = r["scores"].get("final_score", 0)
        assert 0.0 <= fs <= 1.0, f"Score {fs} out of range for {r['difficulty']}"
    print("  All scores in valid range [0.0, 1.0]")

    with open(_ROOT.parent / "inference_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print("  Results saved to inference_results.json")


if __name__ == "__main__":
    main()
