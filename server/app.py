from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

"""FastAPI ASGI application: Hugging Face Spaces + OpenEnv HTTP API."""

from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv()

import json
import logging
import os

logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from models import Action, EnvironmentState, Observation, RCAReport, ServiceMetrics
from server.environment import RCAEnvironment, _metrics_row_to_model
from server.grader import grade
from server.llm import is_llm_configured

logger = logging.getLogger(__name__)

SCENARIOS: dict[str, dict] = {}
sessions: dict[str, RCAEnvironment] = {}


def _load_all_scenarios() -> None:
    global SCENARIOS
    SCENARIOS.clear()
    base = _PROJECT_ROOT / "scenarios"
    for key, name in (
        ("easy", "easy.json"),
        ("medium", "medium.json"),
        ("hard", "hard.json"),
        ("data_breach", "data_breach.json"),
        ("ddos", "ddos.json"),
    ):
        with (base / name).open(encoding="utf-8") as f:
            SCENARIOS[key] = json.load(f)


def _service_metrics_from_scenario(scenario: dict) -> dict[str, ServiceMetrics]:
    out: dict[str, ServiceMetrics] = {}
    for name, data in scenario.get("service_metrics", {}).items():
        out[name] = _metrics_row_to_model(name, data)
    return out


def _environment_state_for_grader(
    scenario: dict,
    report: RCAReport,
    queries_used: int,
) -> EnvironmentState:
    max_q = int(scenario.get("max_queries", 25))
    return EnvironmentState(
        scenario_id=scenario["scenario_id"],
        difficulty=scenario["difficulty"],
        alert=scenario["alert"],
        service_metrics=_service_metrics_from_scenario(scenario),
        queries_remaining=max(0, max_q - queries_used),
        max_queries=max_q,
        hypotheses=[],
        rca_submitted=True,
        submitted_report=report,
        current_step=0,
        episode_reward=0.0,
    )


app = FastAPI(title="RCAAgent-Env", version="2.0.0")

app.mount("/static", StaticFiles(directory=str(_PROJECT_ROOT / "static")), name="static")


@app.on_event("startup")
def startup_event() -> None:
    _load_all_scenarios()
    if not is_llm_configured():
        logger.warning(
            "LLM not configured: set HF_TOKEN (and API_BASE_URL / MODEL_NAME) for baseline, "
            "grader report_quality, and inference.py."
        )
    else:
        logger.info("LLM client configured (HF_TOKEN set).")
    logger.info("RCAAgent-Env ready (scenarios=%s)", list(SCENARIOS.keys()))


@app.get("/")
def root():
    from fastapi.responses import HTMLResponse
    html = open(_PROJECT_ROOT / "server" / "ui.html", encoding="utf-8").read()
    ui_html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RCAAgent-Env | SRE Intelligence Platform</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0a0a0f; color: #e2e8f0; font-family: 'Courier New', monospace; min-height: 100vh; }
  
  /* TOP NAV */
  .nav { background: #0d0d1a; border-bottom: 1px solid #1e293b; padding: 14px 40px; display: flex; align-items: center; justify-content: space-between; }
  .nav-logo { display: flex; align-items: center; gap: 12px; }
  .nav-logo .dot { width: 10px; height: 10px; border-radius: 50%; background: #3b82f6; box-shadow: 0 0 8px #3b82f6; }
  .nav-logo span { font-size: 15px; font-weight: 700; letter-spacing: 2px; color: #f1f5f9; text-transform: uppercase; }
  .nav-right { display: flex; gap: 24px; align-items: center; }
  .nav-right a { color: #64748b; font-size: 12px; text-decoration: none; letter-spacing: 1px; text-transform: uppercase; }
  .nav-right a:hover { color: #3b82f6; }
  .status-pill { background: #052e16; border: 1px solid #16a34a; color: #4ade80; padding: 4px 12px; border-radius: 20px; font-size: 11px; letter-spacing: 1px; }

  /* HERO */
  .hero { padding: 60px 40px 40px; border-bottom: 1px solid #1e293b; }
  .hero-label { color: #3b82f6; font-size: 11px; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 16px; }
  .hero h1 { font-size: 42px; font-weight: 800; color: #f8fafc; line-height: 1.1; margin-bottom: 16px; }
  .hero h1 span { color: #3b82f6; }
  .hero p { color: #64748b; font-size: 14px; max-width: 600px; line-height: 1.8; }

  /* METRICS BAR */
  .metrics-bar { display: flex; gap: 0; border-bottom: 1px solid #1e293b; }
  .metric { flex: 1; padding: 24px 40px; border-right: 1px solid #1e293b; }
  .metric:last-child { border-right: none; }
  .metric-label { color: #475569; font-size: 10px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 8px; }
  .metric-value { font-size: 28px; font-weight: 800; color: #f1f5f9; }
  .metric-value.blue { color: #3b82f6; }
  .metric-value.green { color: #4ade80; }
  .metric-value.yellow { color: #fbbf24; }

  /* MAIN GRID */
  .main { display: grid; grid-template-columns: 300px 1fr; min-height: calc(100vh - 280px); }
  
  /* SIDEBAR */
  .sidebar { background: #0d0d1a; border-right: 1px solid #1e293b; padding: 32px 24px; }
  .sidebar-title { color: #475569; font-size: 10px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 20px; }
  .scenario-btn { width: 100%; background: #111827; border: 1px solid #1e293b; color: #94a3b8; padding: 16px 20px; margin-bottom: 8px; border-radius: 4px; cursor: pointer; text-align: left; font-family: 'Courier New', monospace; font-size: 13px; transition: all 0.2s; }
  .scenario-btn:hover { border-color: #3b82f6; color: #f1f5f9; background: #0f172a; }
  .scenario-btn.active { border-color: #3b82f6; background: #0f172a; color: #3b82f6; }
  .scenario-btn .btn-title { font-weight: 700; margin-bottom: 4px; font-size: 13px; }
  .scenario-btn .btn-meta { font-size: 11px; color: #475569; }
  .scenario-btn.active .btn-meta { color: #1d4ed8; }
  .difficulty-badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 10px; font-weight: 700; letter-spacing: 1px; margin-bottom: 6px; }
  .badge-easy { background: #052e16; color: #4ade80; border: 1px solid #16a34a; }
  .badge-medium { background: #451a03; color: #fbbf24; border: 1px solid #d97706; }
  .badge-hard { background: #450a0a; color: #f87171; border: 1px solid #dc2626; }
  .badge-ddos { background: #2e1065; color: #c084fc; border: 1px solid #9333ea; }

  .run-btn { width: 100%; background: #1d4ed8; border: none; color: #fff; padding: 14px; border-radius: 4px; cursor: pointer; font-family: 'Courier New', monospace; font-size: 13px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; margin-top: 16px; transition: all 0.2s; }
  .run-btn:hover { background: #2563eb; }
  .run-btn:disabled { background: #1e293b; color: #475569; cursor: not-allowed; }

  /* TERMINAL */
  .terminal { padding: 32px; }
  .terminal-header { display: flex; align-items: center; gap: 8px; margin-bottom: 24px; }
  .terminal-dots { display: flex; gap: 6px; }
  .terminal-dots span { width: 12px; height: 12px; border-radius: 50%; }
  .dot-red { background: #ef4444; }
  .dot-yellow { background: #f59e0b; }
  .dot-green { background: #22c55e; }
  .terminal-title { color: #475569; font-size: 12px; margin-left: 8px; }

  .terminal-body { background: #050508; border: 1px solid #1e293b; border-radius: 6px; padding: 24px; min-height: 400px; max-height: 520px; overflow-y: auto; font-size: 13px; line-height: 1.8; }
  .terminal-body .placeholder { color: #1e293b; text-align: center; padding-top: 80px; font-size: 14px; }
  
  .log-line { margin-bottom: 4px; animation: fadeIn 0.3s ease; }
  @keyframes fadeIn { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: translateX(0); } }
  .log-time { color: #334155; margin-right: 8px; }
  .log-step { color: #3b82f6; font-weight: 700; margin-right: 8px; }
  .log-action { color: #22c55e; }
  .log-service { color: #fbbf24; }
  .log-info { color: #94a3b8; }
  .log-anomaly { color: #f87171; }
  .log-success { color: #4ade80; }
  .log-error { color: #ef4444; }

  /* SCORE CARD */
  .score-card { background: #050508; border: 1px solid #1e293b; border-radius: 6px; padding: 24px; margin-top: 16px; display: none; }
  .score-card.visible { display: block; }
  .score-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin-top: 16px; }
  .score-item { text-align: center; }
  .score-item-label { color: #475569; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 6px; }
  .score-item-value { font-size: 20px; font-weight: 800; }
  .score-main { font-size: 48px; font-weight: 900; text-align: center; margin: 16px 0; }
  .score-green { color: #4ade80; }
  .score-yellow { color: #fbbf24; }
  .score-red { color: #ef4444; }

  .spinner { display: inline-block; width: 12px; height: 12px; border: 2px solid #1e293b; border-top-color: #3b82f6; border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 8px; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<nav class="nav">
  <div class="nav-logo">
    <div class="dot"></div>
    <span>RCAAgent-Env</span>
  </div>
  <div class="nav-right">
    <a href="/docs">API Docs</a>
    <a href="/tasks">Tasks</a>
    <span class="status-pill">● LIVE</span>
  </div>
</nav>

<div class="hero">
  <div class="hero-label">OpenEnv · SRE Intelligence Platform</div>
  <h1>AI-Powered <span>Incident</span><br>Root Cause Analysis</h1>
  <p>Deploy AI agents into simulated production failures. Watch them investigate microservice dependencies, query metrics and traces, and deliver structured RCA reports — scored against ground truth.</p>
</div>

<div class="metrics-bar">
  <div class="metric">
    <div class="metric-label">Scenarios(Inbuilt + Custom)</div>
    <div class="metric-value blue">05</div>
  </div>
  <div class="metric">
    <div class="metric-label">Max Score</div>
    <div class="metric-value green">1.00</div>
  </div>
  <div class="metric">
    <div class="metric-label">Baseline Model</div>
    <div class="metric-value" style="font-size:16px;padding-top:6px">Qwen 72B + LLama 3.1</div>
  </div>
  <div class="metric">
    <div class="metric-label">Environment</div>
    <div class="metric-value yellow">v2.0</div>
  </div>
</div>

<div class="main">
  <div class="sidebar">
    <div class="sidebar-title">Select Scenario</div>

    <button class="scenario-btn" onclick="selectScenario('easy', this)">
      <div class="difficulty-badge badge-easy">EASY</div>
      <div class="btn-title">INC-001 · Cache Failure</div>
      <div class="btn-meta">Optimal: 3 queries · 1 service down</div>
    </button>

    <button class="scenario-btn" onclick="selectScenario('medium', this)">
      <div class="difficulty-badge badge-medium">MEDIUM</div>
      <div class="btn-title">INC-002 · Config Cascade</div>
      <div class="btn-meta">Optimal: 6 queries · 4 services</div>
    </button>

    <button class="scenario-btn" onclick="selectScenario('hard', this)">
      <div class="difficulty-badge badge-hard">HARD</div>
      <div class="btn-title">INC-003 · AZ Packet Loss</div>
      <div class="btn-meta">Optimal: 10 queries · 12 services</div>
    </button>

    <button class="scenario-btn" onclick="selectScenario('ddos', this)">
      <div class="difficulty-badge badge-ddos">DDOS</div>
      <div class="btn-title">INC-004 · DDoS Attack</div>
      <div class="btn-meta">Optimal: 4 queries · 5 services</div>
    </button>

    <button class="run-btn" id="runBtn" onclick="runBaseline()" disabled>
      ▶ RUN AGENT
    </button>
  </div>

  <div class="terminal">
    <div class="terminal-header">
      <div class="terminal-dots">
        <span class="dot-red"></span>
        <span class="dot-yellow"></span>
        <span class="dot-green"></span>
      </div>
      <span class="terminal-title">agent-investigation.log</span>
    </div>

    <div class="terminal-body" id="terminalBody">
      <div class="placeholder">← Select a scenario and click RUN AGENT</div>
    </div>

    <div class="score-card" id="scoreCard">
      <div style="color:#475569;font-size:11px;letter-spacing:2px;text-transform:uppercase;">Final Score</div>
      <div class="score-main" id="scoreMain">—</div>
      <div class="score-grid" id="scoreGrid"></div>
    </div>
  </div>
</div>

<script>
  let selectedDifficulty = null;

  function selectScenario(difficulty, btn) {
    selectedDifficulty = difficulty;
    document.querySelectorAll('.scenario-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('runBtn').disabled = false;
    document.getElementById('terminalBody').innerHTML = '<div class="placeholder">Click RUN AGENT to start investigation</div>';
    document.getElementById('scoreCard').classList.remove('visible');
  }

  function log(html) {
    const tb = document.getElementById('terminalBody');
    if (tb.querySelector('.placeholder')) tb.innerHTML = '';
    const div = document.createElement('div');
    div.className = 'log-line';
    div.innerHTML = html;
    tb.appendChild(div);
    tb.scrollTop = tb.scrollHeight;
  }

  function now() {
    return new Date().toLocaleTimeString('en-US', {hour12: false});
  }

  async function runBaseline() {
    if (!selectedDifficulty) return;
    const btn = document.getElementById('runBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>RUNNING...';
    document.getElementById('terminalBody').innerHTML = '';
    document.getElementById('scoreCard').classList.remove('visible');

    log('<span class="log-time">' + now() + '</span><span class="log-success">▶ Starting AI Agent Investigation</span>');
    log('<span class="log-time">' + now() + '</span><span class="log-info">Scenario: ' + selectedDifficulty.toUpperCase() + '</span>');
    log('<span class="log-time">' + now() + '</span><span class="log-info">─────────────────────────────────────</span>');

    try {
      const res = await fetch('/baseline', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({difficulty: selectedDifficulty})
      });
      const data = await res.json();

      if (data.error) {
        log('<span class="log-time">' + now() + '</span><span class="log-error">✗ Error: ' + data.error + '</span>');
      } else {
        const history = data.history || [];
        for (let i = 0; i < history.length; i++) {
          const h = history[i];
          const action = h.action;
          const obs = h.observation;
          const reward = obs.reward;

          let actionHtml = '<span class="log-step">STEP ' + (i+1) + '</span>';
          actionHtml += '<span class="log-action">' + action.action_type.toUpperCase() + '</span>';
          if (action.target_service) actionHtml += ' → <span class="log-service">' + action.target_service + '</span>';
          if (action.hypothesis) actionHtml += ' <span class="log-info">💭 ' + action.hypothesis.substring(0, 80) + '...</span>';
          log('<span class="log-time">' + now() + '</span>' + actionHtml);

          if (obs.anomaly_detected) {
            log('<span class="log-time">' + now() + '</span><span style="margin-left:60px" class="log-anomaly">⚠ Anomaly: ' + obs.anomaly_type + '</span>');
          }
          if (reward) {
            log('<span class="log-time">' + now() + '</span><span style="margin-left:60px" class="log-info">↳ reward: +' + reward.step_reward.toFixed(3) + ' | cumulative: ' + reward.cumulative_reward.toFixed(3) + '</span>');
          }
          await new Promise(r => setTimeout(r, 200));
        }

        log('<span class="log-time">' + now() + '</span><span class="log-info">─────────────────────────────────────</span>');

        if (data.report) {
          log('<span class="log-time">' + now() + '</span><span class="log-success">✓ Root Cause: <span class="log-service">' + data.report.root_cause_service + '</span> (' + data.report.root_cause_type + ')</span>');
          log('<span class="log-time">' + now() + '</span><span class="log-success">✓ Affected: ' + (data.report.affected_services || []).join(' → ') + '</span>');
        }

        if (data.scores) {
          const s = data.scores;
          const finalScore = s.final_score || 0;
          const scoreClass = finalScore >= 0.7 ? 'score-green' : finalScore >= 0.4 ? 'score-yellow' : 'score-red';

          document.getElementById('scoreMain').className = 'score-main ' + scoreClass;
          document.getElementById('scoreMain').textContent = (finalScore * 100).toFixed(1) + '%';

          const grid = document.getElementById('scoreGrid');
          grid.innerHTML = [
            ['Root Cause', s.root_cause_score],
            ['Causal Path', s.causal_path_score],
            ['Efficiency', s.efficiency_score],
            ['Report Quality', s.report_quality_score],
            ['Confidence', s.confidence_bonus]
          ].map(([label, val]) => {
            const v = val || 0;
            const c = v >= 0.7 ? 'score-green' : v >= 0.4 ? 'score-yellow' : 'score-red';
            return '<div class="score-item"><div class="score-item-label">' + label + '</div><div class="score-item-value ' + c + '">' + (v * 100).toFixed(0) + '%</div></div>';
          }).join('');

          document.getElementById('scoreCard').classList.add('visible');
          log('<span class="log-time">' + now() + '</span><span class="log-success">✓ Investigation complete · Score: ' + (finalScore * 100).toFixed(1) + '%</span>');
        }
      }
    } catch(e) {
      log('<span class="log-time">' + now() + '</span><span class="log-error">✗ Failed: ' + e.message + '</span>');
    }

    btn.disabled = false;
    btn.innerHTML = '▶ RUN AGENT';
  }
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


class TaskMeta(BaseModel):
    id: str
    name: str
    difficulty: str
    max_steps: int
    optimal_steps: int


class TasksResponse(BaseModel):
    tasks: list[TaskMeta]
    action_schema: dict


class GraderRequest(BaseModel):
    difficulty: str
    report: RCAReport
    queries_used: int | None = Field(default=None)


@app.get("/tasks", response_model=TasksResponse)
def list_tasks() -> TasksResponse:
    out: list[TaskMeta] = []
    for diff in ("easy", "medium", "hard", "data_breach", "ddos"):
        sc = SCENARIOS[diff]
        gt = sc.get("ground_truth", {})
        out.append(
            TaskMeta(
                id=sc["scenario_id"],
                name=f"RCA {sc['scenario_id']}",
                difficulty=sc["difficulty"],
                max_steps=int(sc.get("max_queries", 25)),
                optimal_steps=int(gt.get("optimal_queries", 0)),
            )
        )
    return TasksResponse(tasks=out, action_schema=Action.model_json_schema())


@app.post("/reset/{difficulty}", response_model=EnvironmentState)
def reset_session(difficulty: str) -> EnvironmentState:
    d = difficulty.lower()
    if d not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Unknown difficulty: {difficulty}")
    env = RCAEnvironment(d)
    sessions[d] = env
    return env.reset()


def _get_session(difficulty: str) -> RCAEnvironment:
    d = difficulty.lower()
    env = sessions.get(d)
    if env is None:
        raise HTTPException(
            status_code=404,
            detail=f"No session for {difficulty}; call POST /reset/{difficulty} first",
        )
    return env


@app.post("/step/{difficulty}", response_model=Observation)
def take_step(difficulty: str, body: Action) -> Observation:
    env = _get_session(difficulty)
    return env.step(body)


@app.get("/state/{difficulty}", response_model=EnvironmentState)
def get_state(difficulty: str) -> EnvironmentState:
    env = _get_session(difficulty)
    return env.state()


def _run_grade(body: GraderRequest) -> dict:
    d = body.difficulty.lower()
    if d not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Unknown difficulty: {body.difficulty}")
    scenario = SCENARIOS[d]
    qu = body.queries_used if body.queries_used is not None else 0
    state = _environment_state_for_grader(scenario, body.report, qu)
    return grade(body.report, state, scenario)


@app.post("/grader")
def post_grader(body: GraderRequest) -> dict:
    return _run_grade(body)


@app.get("/baseline")
async def get_baseline(
    difficulty: str = Query(..., description="Task difficulty: easy, medium, or hard"),
) -> dict:
    from baseline.agent import run_baseline

    d = difficulty.lower()
    if d not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Unknown difficulty: {difficulty}")
    return await asyncio.to_thread(run_baseline, d)


class BaselineBody(BaseModel):
    difficulty: str = Field(description="easy, medium, or hard")


class CustomScenarioRequest(BaseModel):
    data: dict = Field(description="Custom scenario JSON payload")


@app.post("/baseline")
async def post_baseline(body: BaselineBody) -> dict:
    from baseline.agent import run_baseline

    try:
        d = body.difficulty.lower()
        if d not in SCENARIOS:
            raise HTTPException(status_code=404, detail=f"Unknown difficulty: {body.difficulty}")
        return await asyncio.to_thread(run_baseline, d)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Baseline run failed")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/investigate/custom")
async def post_custom_investigation(body: CustomScenarioRequest) -> dict:
    from baseline.agent import run_baseline

    try:
        if not isinstance(body.data, dict) or not body.data:
            raise HTTPException(status_code=400, detail="Custom scenario data must be a non-empty JSON object")
        return await asyncio.to_thread(run_baseline, "custom", body.data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Custom investigation run failed")
        return JSONResponse(status_code=500, content={"error": str(e)})