<<<<<<< HEAD
"""
models.py — Single source of truth for all OpenEnv typed models.
Implements full OpenEnv spec: Action, Observation, Reward, EnvironmentState.
"""
=======
"""Pydantic models for RCAAgent-Env (OpenEnv)."""
>>>>>>> 1e0c61bd756a3c13d37981bdfb8d422f6cc010d6

from __future__ import annotations

from enum import Enum
<<<<<<< HEAD
from typing import Any, Dict, List, Optional
=======
from typing import Literal, Optional
>>>>>>> 1e0c61bd756a3c13d37981bdfb8d422f6cc010d6

from pydantic import BaseModel, Field


class ActionType(str, Enum):
<<<<<<< HEAD
    QUERY_METRICS = "query_metrics"
    QUERY_LOGS = "query_logs"
    PULL_TRACES = "pull_traces"
    QUERY_DEPENDENCIES = "query_dependencies"
    FORM_HYPOTHESIS = "form_hypothesis"
    SUBMIT_RCA = "submit_rca"


class RCAReport(BaseModel):
    """Structured root cause analysis report submitted by the agent."""

    root_cause_service: str = Field(..., description="Name of the service that is the root cause")
    root_cause_type: str = Field(
        ...,
        description="Type of failure: latency|error_rate|crash|memory_leak|network|dependency_failure",
    )
    affected_services: List[str] = Field(..., description="All services impacted by this incident")
    causal_chain: List[str] = Field(
        ...,
        description="Ordered list of events from root cause to user impact",
    )
    summary: str = Field(..., description="2-3 sentence human-readable incident summary")
    suggested_fix: str = Field(..., description="Concrete remediation steps")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Agent confidence in this analysis")


class Action(BaseModel):
    """
    Agent action. One of:
    - query_metrics/query_logs/pull_traces/query_dependencies: investigative queries (costs 1 query budget)
    - form_hypothesis: record intermediate reasoning (no budget cost in this env)
    - submit_rca: final structured report submission
    """

    action_type: ActionType = Field(..., description="Type of action to take")
    target_service: Optional[str] = Field(None, description="Service to investigate (required for query actions)")
    hypothesis: Optional[str] = Field(None, description="Hypothesis text (for form_hypothesis)")
    rca_report: Optional[RCAReport] = Field(None, description="Final RCA report (for submit_rca)")


class ServiceMetrics(BaseModel):
    """Real-time metrics snapshot for a single service."""

    service_name: str
    error_rate: float = Field(..., ge=0.0, le=1.0, description="Error rate 0.0-1.0")
    latency_p99_ms: float = Field(..., ge=0.0, description="P99 latency in milliseconds")
    requests_per_second: float = Field(..., ge=0.0)
    cpu_usage: float = Field(..., ge=0.0, le=1.0)
    memory_usage: float = Field(..., ge=0.0, le=1.0)
    status: str = Field(..., description="healthy|degraded|down")


class Reward(BaseModel):
    """
    Per-step reward signal. Provides dense feedback throughout the episode,
    not just at submission time.
    """

    step_reward: float = Field(..., description="Immediate reward for this action (-1.0 to 1.0)")
    cumulative_reward: float = Field(..., description="Total reward accumulated this episode")
    reward_components: Dict[str, float] = Field(
        default_factory=dict,
        description="Breakdown: efficiency, relevance, hypothesis_quality",
    )
    done: bool = Field(False, description="True if episode is complete")


class Observation(BaseModel):
    """Structured observation returned after each action."""

    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    anomaly_detected: bool = False
    anomaly_type: Optional[str] = None
    queries_remaining: Optional[int] = None
    reward: Optional[Reward] = None


class EnvironmentState(BaseModel):
    """Full environment state snapshot."""

    scenario_id: str
    difficulty: str
    alert: str
    service_metrics: Dict[str, ServiceMetrics]
    queries_remaining: int
    max_queries: int
    hypotheses: List[str] = Field(default_factory=list)
    rca_submitted: bool = False
    submitted_report: Optional[RCAReport] = None
    current_step: int = 0
    episode_reward: float = 0.0
=======
    query_metrics = "query_metrics"
    query_logs = "query_logs"
    pull_traces = "pull_traces"
    query_dependencies = "query_dependencies"
    form_hypothesis = "form_hypothesis"
    submit_rca = "submit_rca"


class RCAReport(BaseModel):
    root_cause_service: str
    root_cause_type: str
    affected_services: list[str]
    causal_chain: list[str]
    summary: str
    fix_recommendation: str
    confidence: float = Field(ge=0.0, le=1.0)


class Action(BaseModel):
    action_type: ActionType
    target_service: Optional[str] = None
    hypothesis: Optional[str] = None
    rca_report: Optional[RCAReport] = None


class ServiceMetrics(BaseModel):
    latency_ms: float
    error_rate: float
    cpu_percent: float
    memory_percent: float
    status: Literal["healthy", "degraded", "down"]


class Observation(BaseModel):
    success: bool
    service: Optional[str] = None
    metrics: Optional[ServiceMetrics] = None
    logs: Optional[list[str]] = None
    traces: Optional[list[dict]] = None
    dependencies: Optional[dict] = None
    anomaly_detected: bool = False
    anomaly_type: Optional[str] = None
    queries_remaining: int = 0
    message: str = ""


class EnvironmentState(BaseModel):
    scenario_id: str
    difficulty: str
    alert: str
    services: dict[str, ServiceMetrics]
    queries_used: int
    max_queries: int
    hypotheses: list[str]
    rca_submitted: bool
    submitted_report: Optional[RCAReport] = None
>>>>>>> 1e0c61bd756a3c13d37981bdfb8d422f6cc010d6
