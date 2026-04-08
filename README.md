---
title: RCAAgent-Env
emoji: 🔍
colorFrom: blue
colorTo: green
sdk: docker
app_file: server/app.py
pinned: false
---

# RCAAgent-Env

OpenEnv-compatible environment for training and evaluating RCA agents on realistic microservice incidents.

- Hugging Face Space URL format: `https://huggingface.co/spaces/<username>/<space-name>`
- Current deployment reference: `https://sujalk123-rcaagent-env.hf.space`
- Demo description: The web UI shows end-to-end incident investigation, step-by-step telemetry queries, and final RCA grading.

## Environment Description and Motivation

Modern incidents rarely fail in one obvious place. RCAAgent-Env simulates cross-service degradation where agents must inspect metrics, logs, traces, and dependency edges to identify root cause and submit a structured report. The environment is designed for:

- SRE/on-call training
- Agent benchmarking under query budget constraints
- Reproducible scoring for OpenEnv-style evaluations

## Task Descriptions (Difficulty)

- `easy`: single dominant root cause with short dependency chain
- `medium`: cascading failure with multiple degraded tiers
- `hard`: diffuse symptoms with subtler correlation signals
- `ddos`: volumetric traffic saturation at ingress edge
- `data_breach`: security/event-driven anomaly pattern

## Action Space Definition

Agent sends structured JSON actions:

```json
{"action_type":"query_metrics","target_service":"api_gateway"}
{"action_type":"query_logs","target_service":"database"}
{"action_type":"pull_traces","target_service":"order_service"}
{"action_type":"query_dependencies","target_service":"auth_service"}
{"action_type":"form_hypothesis","hypothesis":"Likely cache misconfiguration"}
{"action_type":"submit_rca","rca_report":{"root_cause_service":"cache","root_cause_type":"misconfiguration","affected_services":["pricing_service"],"causal_chain":["cache","pricing_service","api_gateway"],"summary":"...","suggested_fix":"...","confidence":0.82}}
```

## Observation Space Definition

Environment returns structured observations:

```json
{
  "success": true,
  "message": "Metrics for api_gateway",
  "data": {},
  "anomaly_detected": true,
  "anomaly_type": "degraded",
  "queries_remaining": 18,
  "reward": {
    "step_reward": 0.15,
    "cumulative_reward": 0.52,
    "reward_components": {},
    "done": false
  }
}
```

## Scenario JSON Schema

All `scenarios/*.json` use a common top-level schema:

```json
{
  "scenario_id": "INC-XXX",
  "difficulty": "easy|medium|hard|ddos|data_breach",
  "alert": "string",
  "services": ["service_a", "service_b"],
  "max_queries": 30,
  "service_metrics": {"service_a": {"latency_ms": 0, "error_rate": 0, "cpu_percent": 0, "memory_percent": 0, "status": "healthy"}},
  "logs": {"service_a": ["..."]},
  "traces": {"service_a": [{"trace_id": "t-1", "span": "op", "duration_ms": 12, "status": "ok"}]},
  "dependencies": {"service_a": {"upstream": [], "downstream": []}},
  "ground_truth": {
    "root_cause_service": "service_a",
    "root_cause_type": "type",
    "affected_services": ["service_b"],
    "causal_chain": ["service_a", "service_b"],
    "optimal_queries": 5,
    "difficulty_rationale": "string",
    "teaching_points": ["string"]
  }
}
```

## Setup and Usage Instructions

```bash
git clone https://github.com/sujal-sk-01/finalestRCAA
cd finalestRCAA
pip install -r requirements.txt
cp .env.example .env
```

Set environment variables in `.env`:

```bash
HF_TOKEN=your_api_token
API_BASE_URL=https://router.huggingface.co/v1
MODEL_NAME=meta-llama/Llama-3.3-70B-Instruct
```

Run server:

```bash
uvicorn server.app:app --host 0.0.0.0 --port 7860
```

Run inference baseline:

```bash
python inference.py
```

## Baseline Scores

- easy: `0.72`
- medium: `0.51`
- hard: `0.31`

## Tech Stack

- Python 3.11
- FastAPI + Uvicorn
- Pydantic v2
- OpenAI-compatible client (configured by env)
- Vanilla HTML/CSS/JS frontend