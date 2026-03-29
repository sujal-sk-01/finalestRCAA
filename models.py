"""Pydantic models for RCAAgent-Env (OpenEnv)."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
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
