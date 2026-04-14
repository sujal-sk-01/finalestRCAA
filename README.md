---
title: RCAAgent-Env
emoji: 🔍
colorFrom: blue
colorTo: green
sdk: docker
app_file: server/app.py
pinned: false
---

<div align="center">

# 🔍 RCAAgent-Env

**A production-grade, OpenEnv-compatible simulation environment for training and evaluating AI agents on SRE incident Root Cause Analysis (RCA).**

[![Hugging Face Space](https://img.shields.io/badge/Hugging%20Face-Space-yellow?logo=huggingface)](https://huggingface.co/spaces/Sujalk123/rcaagent-env)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker)](https://www.docker.com/)
[![OpenEnv](https://img.shields.io/badge/OpenEnv-Compatible-22c55e)](https://github.com/meta-pytorch/OpenEnv)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

### 🌐 Live Space: [huggingface.co/spaces/Sujalk123/rcaagent-env](https://huggingface.co/spaces/Sujalk123/rcaagent-env)

</div>

---

## 📌 Table of Contents

- [Motivation](#-motivation)
- [Quick Start](#-quick-start)
- [Environment Description](#-environment-description)
- [Agent ↔ Environment Loop](#-agent--environment-loop)
- [Task Descriptions](#-task-descriptions)
- [Action Space](#-action-space)
- [Observation Space](#-observation-space)
- [Reward Function](#-reward-function)
- [Deterministic Grading](#-deterministic-grading)
- [API Endpoints](#-api-endpoints)
- [Inference Runner](#-inference-runner)
- [Baseline Scores](#-baseline-scores)
- [Environment Variables](#-required-environment-variables)
- [Project Structure](#-project-structure)
- [Custom Scenarios](#-custom-scenarios)
- [Deployment Notes](#-deployment-notes)
- [Citation](#-citation)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🎯 Motivation

Modern production incidents are rarely single-point failures. Symptoms appear across multiple services, and true causes hide behind cascades, retries, and noisy telemetry. This makes RCA an ideal benchmark for agentic reasoning because it demands:

- **Multi-hop investigation** across metrics, logs, traces, and service dependencies
- **Budget-aware decision making** under limited query constraints
- **Structured reporting** with causal chains and remediation steps
- **Reproducible evaluation** via deterministic, rule-based scoring

RCAAgent-Env provides a realistic, constrained environment where agents can be compared fairly on both investigation quality and efficiency — mirroring exactly what on-call SREs do every day at scale.

---

## ⚡ Quick Start

### 1. Run Locally (Python)

```bash
git clone https://github.com/sujal-sk-01/finalestRCAA
cd finalestRCAA
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set API_BASE_URL, MODEL_NAME, HF_TOKEN
uvicorn server.app:app --host 0.0.0.0 --port 7860 --reload
```

Open → http://127.0.0.1:7860

---

### 2. Run Baseline Inference (All 3 Tasks)

```bash
python inference.py
```

---

### 3. Run with Docker

```bash
docker build -t rcaagent-env .
docker run --rm -p 7860:7860 --env-file .env rcaagent-env
```

Open → http://127.0.0.1:7860

---

### 4. Deploy on Hugging Face Space

Deploy this repo as a **Docker Space** and add these repository secrets:

| Secret | Description |
|---|---|
| `API_BASE_URL` | OpenAI-compatible API base URL |
| `MODEL_NAME` | Model identifier for inference |
| `HF_TOKEN` | Hugging Face token / API key |

---

## 🌍 Environment Description

RCAAgent-Env exposes a full OpenEnv-style interaction loop over FastAPI:

| Feature | Detail |
|---|---|
| Backend | FastAPI with full `reset()` / `step()` / `state()` lifecycle |
| Scenarios | 5 incidents: `easy`, `medium`, `hard`, `ddos`, `data_breach` |
| Contracts | Typed Pydantic models: `Action`, `Observation`, `Reward`, `RCAReport`, `EnvironmentState` |
| Grader | Deterministic, reproducible `0.0–1.0` scoring |
| Rewards | Partial, non-binary, checkpoint-based progress signals |
| Logging | `inference.py` emits strict JSON: `START`, `STEP`, `END` |
| LLM Client | OpenAI-compatible, driven by environment variables |
| Runtime | Dockerized on port `7860` |
| Spec | Full OpenEnv specification in `openenv.yaml` |
| Dashboard | Single-page investigation UI at `server/ui.html` |

---

## 🔄 Agent ↔ Environment Loop

```
+--------------------------+        Action (JSON)         +-----------------------------+
|         AI Agent         | --------------------------> |      RCAAgent-Env API       |
| (LLM / policy / planner) |                              |  /reset  /step  /state      |
+--------------------------+                              +-----------------------------+
            ^                                                           |
            |            Observation + Reward (JSON)                    |
            +-----------------------------------------------------------+

                       +-----------------------------------+
                       | Deterministic Grader (0.0 - 1.0) |
                       | root cause · path · efficiency   |
                       | rule-based report quality         |
                       +-----------------------------------+
```

---

## 📋 Task Descriptions

| Difficulty | Scenario Type | What the Agent Must Handle |
|---|---|---|
| `easy` | Single dominant service fault | Short causal chain, clear root indicator |
| `medium` | Config cascade failure | Multi-hop propagation, selective relevance |
| `hard` | Diffuse network degradation | Broad symptoms with weak local signals |
| `ddos` | Volumetric ingress saturation | Edge overload and downstream service effects |
| `data_breach` | Security + reliability overlap | Auth/data anomalies with incident propagation |

---
## 📁 Download Scenarios

You can download scenario files here:

https://drive.google.com/drive/folders/1Aig_AIK0a-3YzYi4Aw9UXxvj9YX_xON_?usp=sharing
## 🎮 Action Space

Agents send one structured JSON action per step:

| Action Type | Description | Required Field |
|---|---|---|
| `query_metrics` | Fetch service metrics (latency, error rate, CPU, memory, status) | `target_service` |
| `query_logs` | Retrieve service log lines for anomaly clues | `target_service` |
| `pull_traces` | Inspect distributed tracing spans and statuses | `target_service` |
| `query_dependencies` | Inspect upstream/downstream service topology | `target_service` |
| `form_hypothesis` | Record intermediate reasoning — **no budget cost** | `hypothesis` |
| `submit_rca` | Submit final root cause analysis report | `rca_report` |

### Example — Query Action

```json
{
  "action_type": "query_metrics",
  "target_service": "api_gateway"
}
```

### Example — Submit RCA

```json
{
  "action_type": "submit_rca",
  "rca_report": {
    "root_cause_service": "cache",
    "root_cause_type": "misconfiguration",
    "affected_services": ["pricing_service", "order_service", "api_gateway"],
    "causal_chain": ["cache", "pricing_service", "order_service", "api_gateway"],
    "summary": "Cache misconfiguration triggered a miss storm and cascaded latency across pricing and order services.",
    "suggested_fix": "Restore cache TTL policy, warm critical keys, and monitor miss/error SLOs.",
    "confidence": 0.82
  }
}
```

---

## 👁️ Observation Space

Each step returns a structured observation:

| Field | Type | Description |
|---|---|---|
| `success` | `bool` | Whether the action executed successfully |
| `message` | `str` | Human-readable result summary |
| `data` | `object \| null` | Payload: metrics / logs / traces / dependencies |
| `anomaly_detected` | `bool` | Whether an anomaly signal was identified |
| `anomaly_type` | `str \| null` | Classified anomaly category |
| `queries_remaining` | `int` | Remaining investigation budget |
| `reward` | `Reward \| null` | Step reward and cumulative signal |

**Reward object fields:**

| Field | Type | Description |
|---|---|---|
| `step_reward` | `float` | Reward earned this step |
| `cumulative_reward` | `float` | Total reward accumulated in episode |
| `reward_components` | `dict` | Breakdown of reward sources |
| `done` | `bool` | Whether the episode has ended |

### Example Observation

```json
{
  "success": true,
  "message": "Metrics for api_gateway",
  "data": {
    "service": "api_gateway",
    "metrics": {
      "error_rate": 0.12,
      "latency_p99_ms": 1850.0,
      "requests_per_second": 828.0,
      "cpu_usage": 0.55,
      "memory_usage": 0.62,
      "status": "degraded"
    }
  },
  "anomaly_detected": true,
  "anomaly_type": "degraded",
  "queries_remaining": 21,
  "reward": {
    "step_reward": 0.3,
    "cumulative_reward": 0.4,
    "reward_components": {
      "affected_service_relevance": 0.3
    },
    "done": false
  }
}
```

---

## 🏆 Reward Function

RCAAgent-Env uses **incremental progress rewards** rather than binary pass/fail:

- ✅ Early investigative signals earn low-to-mid reward
- ✅ Root-cause-relevant evidence earns stronger reward
- ✅ Hypothesis and submission actions have explicit checkpoints
- ❌ Repeated or inefficient querying is penalized
- All step rewards are **bounded and clamped** to `[0.0, 1.0]`

This supports meaningful agent learning on both **investigation accuracy** and **query efficiency**.

---

## 🔬 Deterministic Grading

`server/grader.py` computes reproducible scores in `[0.0, 1.0]` using rule-based logic only:

| Component | What Is Evaluated |
|---|---|
| Root-cause correctness | Exact match on service and fault type |
| Causal chain quality | Path ordering and completeness vs. ground truth |
| Query efficiency | Actual budget used vs. optimal expected budget |
| Report quality | Rule-based checks on summary, fix, and confidence fields |

> **Reproducibility guarantee:** Optional LLM-based analysis, if configured, is **metadata-only** and does not affect the primary deterministic score.

---

## 🔌 API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | Single-page RCA investigation dashboard |
| `GET` | `/tasks` | List available tasks and full action schema |
| `POST` | `/reset/{difficulty}` | Initialize or reset a scenario session |
| `POST` | `/step/{difficulty}` | Execute one action, receive observation |
| `GET` | `/state/{difficulty}` | Retrieve current environment state |
| `POST` | `/grader` | Grade a submitted RCA report |
| `GET` | `/baseline` | Run baseline agent by difficulty |
| `POST` | `/baseline` | Run baseline agent with JSON body |
| `POST` | `/api/investigate/custom` | Run agent on a custom uploaded scenario |

---

## 🤖 Inference Runner

`inference.py` runs the full evaluation loop:

| Property | Value |
|---|---|
| Tasks | `easy`, `medium`, `hard` |
| Max steps per task | `12` |
| Per-task timeout | `360s` |
| Credentials | `os.getenv`: `API_BASE_URL`, `MODEL_NAME`, `HF_TOKEN` |
| LLM client | OpenAI-compatible |

**Structured JSON stdout logs:**

```json
{"type": "START", "task": "easy", "env": "RCAEnvironment", "model": "..."}
{"type": "STEP", "step": 1, "action": "query_metrics", "reward": 0.1, "done": false, "error": null}
{"type": "END", "success": true, "steps": 9, "score": 0.2775, "rewards": [...]}
```
## 📊 Baseline Scores

| Task | Score |
|------|-------|
| easy | 0.94 |
| medium | 0.77 |
| hard | 0.73 |
| ddos | 0.92 |

## 🔧 Required Environment Variables

| Variable | Purpose |
|---|---|
| `API_BASE_URL` | OpenAI-compatible API base URL |
| `MODEL_NAME` | Model identifier for inference |
| `HF_TOKEN` | API key used by the OpenAI-compatible client |

**`.env` file:**

```env
API_BASE_URL=https://router.huggingface.co/v1
MODEL_NAME=meta-llama/Llama-3.3-70B-Instruct
HF_TOKEN=your_token_here
```

---

## 📁 Project Structure

```
finalestRCAA/
├── baseline/
│   ├── __init__.py
│   └── agent.py                 # Baseline agent implementation
├── scenarios/
│   ├── easy.json                # Easy incident scenario
│   ├── medium.json              # Medium incident scenario
│   ├── hard.json                # Hard incident scenario
│   ├── ddos.json                # DDoS attack scenario
│   ├── data_breach.json         # Data breach scenario
│   └── custom_example.json      # Template for custom scenarios
├── server/
│   ├── app.py                   # FastAPI application entrypoint
│   ├── environment.py           # Core environment logic
│   ├── grader.py                # Deterministic scoring engine
│   ├── llm.py                   # OpenAI-compatible LLM client
│   └── ui.html                  # Single-page investigation dashboard
├── static/
│   └── neural-bg.js             # UI background asset
├── models.py                    # Pydantic data models
├── inference.py                 # Evaluation runner
├── openenv.yaml                 # OpenEnv specification
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## 🗂️ Custom Scenarios

Upload custom incident scenarios via `POST /api/investigate/custom`.

Use `scenarios/custom_example.json` as your template:

```json
{
  "scenario_id": "custom-001",
  "difficulty": "medium",
  "alert": "Elevated error rate detected on payment_service",
  "services": ["payment_service", "auth_service", "api_gateway"],
  "max_queries": 20,
  "service_metrics": { "...": "..." },
  "logs": { "...": "..." },
  "traces": { "...": "..." },
  "dependencies": { "...": "..." },
  "ground_truth": {
    "root_cause_service": "auth_service",
    "root_cause_type": "latency",
    "affected_services": ["payment_service", "api_gateway"]
  }
}
```

---

## 🚀 Deployment Notes

- Docker image exposes port `7860`
- Uvicorn entrypoint: `server.app:app` on `0.0.0.0:7860`
- `openenv.yaml` defines environment metadata, task contracts, action/observation spaces
- Hugging Face Space tagged as Docker SDK with health check on `/tasks`

---

## 📖 Citation

```bibtex
@misc{rcaagent-env-2025,
  title     = {RCAAgent-Env: An OpenEnv Environment for SRE Incident Root Cause Analysis},
  author    = {Sujal K},
  year      = {2025},
  publisher = {Hugging Face},
  url       = {https://huggingface.co/spaces/Sujalk123/rcaagent-env}
}
```

---

## 🤝 Contributing

Contributions are welcome!

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'Add my feature'`
4. Push to your branch: `git push origin feature/my-feature`
5. Open a Pull Request with a clear description

Issues and custom scenario contributions are especially encouraged.

---

## 📄 License

This project is licensed under the **MIT License** — see the [`LICENSE`](LICENSE) file for details.

---

<div align="center">

Made with ❤️ by [Sujal K](https://github.com/sujal-sk-01) &nbsp;·&nbsp; [Live Demo](https://huggingface.co/spaces/Sujalk123/rcaagent-env)

</div>
