# RCAAgent-Env 🔍

> **OpenEnv-compatible AI environment for training agents on microservice Root Cause Analysis**

[![HuggingFace Space](https://img.shields.io/badge/%20HuggingFace-Space-blue)](https://sujalk123-rcaagent-env.hf.space)
[![OpenEnv](https://img.shields.io/badge/OpenEnv-v1.0-green)](https://github.com/meta-pytorch/OpenEnv)
[![Model](https://img.shields.io/badge/Model-Qwen%2072B-orange)](https://huggingface.co/Qwen/Qwen2.5-72B-Instruct)

---

##  Live Demo

**[https://sujalk123-rcaagent-env.hf.space](https://sujalk123-rcaagent-env.hf.space)**

 **[Demo Video](https://youtube.com/placeholder)**

---

##  What is RCAAgent-Env?

RCAAgent-Env is a production-grade simulation environment where AI agents investigate realistic microservice incidents. Agents use metrics, logs, traces, and dependency graphs to identify root causes and submit structured postmortem reports — scored against ground truth.

**Real-world utility:**
- On-call engineer training
- Automated incident response
- LLM agent evaluation for DevOps tasks

---

##  Architecture
┌─────────────────────────────────────────────────────┐
│                    AI AGENT                          │
│              (Qwen 72B via Cerebras)                 │
└──────────────────────┬──────────────────────────────┘
│ Actions (JSON)
▼
┌─────────────────────────────────────────────────────┐
│                  FastAPI Server                      │
│                 /step  /reset  /grader               │
└──────────────────────┬──────────────────────────────┘
│
┌────────────┴────────────┐
▼                         ▼
┌──────────────────┐    ┌──────────────────────────┐
│   RCA Environment │    │      Deterministic        │
│   (5 Scenarios)   │    │      Grader v2.0          │
│  easy/medium/hard │    │  root_cause: 0.40         │
│  ddos/data_breach │    │  causal_path: 0.25        │
└──────────────────┘    │  efficiency: 0.20         │
│  report_quality: 0.15     │
└──────────────────────────┘

---

## Baseline Scores

| Scenario | Final Score | Root Cause | Causal Path | Efficiency | Report Quality |
|----------|-------------|------------|-------------|------------|----------------|
| EASY (Cache Failure) | 64% | 60% | 100% | 10% | 73% |
| MEDIUM (Config Cascade) | 64% | 60% | 100% | 10% | 73% |
| HARD (AZ Packet Loss) | 23% | 0% | 17% | 70% | 35% |
| DDOS (DDoS Attack) | 43% | 60% | 38% | 10% | 35% |
| **Average** | **48.5%** | **45%** | **63.75%** | **25%** | **54%** |

---

##  Scenarios

### INC-001 · Cache Failure (EASY) `P2`
Single service failure. Database goes down causing order service degradation.
- Optimal queries: 3 | Max queries: 25 | Services: 6

### INC-002 · Config Cascade (MEDIUM) `P1`
Cache stampede causes cascading failures across pricing and order services.
- Optimal queries: 6 | Max queries: 30 | Services: 8

### INC-003 · AZ Packet Loss (HARD) `P0`
Diffuse network degradation across 12 services. Complex dependency chain.
- Optimal queries: 10 | Max queries: 35 | Services: 12

### INC-004 · DDoS Attack (DDOS) `P0`
Volumetric attack overwhelming rate limiter and auth service.
- Optimal queries: 4 | Max queries: 30 | Services: 5

### INC-005 · Data Breach (DATA_BREACH) `P0`
Credential compromise causing unusual auth token generation and database exfiltration.
- Optimal queries: 5 | Max queries: 30 | Services: 5

---

##  Action Space
```json
{"action_type": "query_dependencies", "target_service": "api_gateway"}
{"action_type": "query_metrics", "target_service": "database"}
{"action_type": "query_logs", "target_service": "auth_service"}
{"action_type": "pull_traces", "target_service": "order_service"}
{"action_type": "form_hypothesis", "hypothesis": "Database OOM causing cascading failures"}
{"action_type": "submit_rca", "rca_report": {...}}
```

---

##  Observation Space
```json
{
  "success": true,
  "anomaly_detected": true,
  "anomaly_type": "service_down",
  "metrics": {"cpu_percent": 98, "error_rate": 0.95, "status": "down"},
  "queries_remaining": 22
}
```

---

##  Quick Start

### Run on HuggingFace Spaces
Visit: **[https://sujalk123-rcaagent-env.hf.space](https://sujalk123-rcaagent-env.hf.space)**

### Run Locally
```bash
git clone https://github.com/sujal-sk-01/finalestRCAA
cd finalestRCAA
pip install -r requirements.txt
cp .env.example .env
# Add your API credentials to .env
uvicorn server.app:app --reload
```

### Environment Variables
HF_TOKEN=your_cerebras_api_key
API_BASE_URL=https://api.cerebras.ai/v1
MODEL_NAME=qwen-3-235b-a22b-instruct-2507

---

##  OpenEnv Compliance

- ✅ `openenv.yaml` spec v1.0
- ✅ Structured action/observation space
- ✅ Deterministic grader with ground truth
- ✅ Dense reward signals
- ✅ Multiple difficulty levels
- ✅ RESTful API endpoints
- ✅ HuggingFace Spaces deployment

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI + Uvicorn |
| AI Model | Qwen 72B (Cerebras) |
| Deployment | HuggingFace Spaces |
| Grading | Deterministic + LLM Rubric |
| Spec | OpenEnv v1.0 |

---

## 📁 Project Structure
rcaagent-env/
├── baseline/
│   └── agent.py          # Baseline AI agent
├── scenarios/
│   ├── easy.json         # Cache failure scenario
│   ├── medium.json       # Config cascade scenario
│   ├── hard.json         # AZ packet loss scenario
│   ├── ddos.json         # DDoS attack scenario
│   └── data_breach.json  # Data breach scenario
├── server/
│   ├── app.py            # FastAPI application
│   ├── environment.py    # RCA environment
│   ├── grader.py         # Scoring system
│   ├── llm.py            # LLM client
│   └── ui.html           # Web interface
├── openenv.yaml          # OpenEnv spec
└── requirements.txt