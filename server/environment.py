"""RCA environment: reset, step, and state for simulated incidents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models import (
    Action,
    ActionType,
    EnvironmentState,
    Observation,
    RCAReport,
    ServiceMetrics,
)


def _scenario_path(difficulty: str) -> Path:
    base = Path(__file__).resolve().parent.parent / "scenarios"
    name = {"easy": "easy.json", "medium": "medium.json", "hard": "hard.json"}.get(
        difficulty.lower()
    )
    if not name:
        raise ValueError(f"Unknown difficulty: {difficulty}")
    return base / name


class RCAEnvironment:
    """OpenEnv-style environment for root-cause analysis on microservice incidents."""

    def __init__(self, difficulty: str) -> None:
        self._difficulty = difficulty.lower()
        self._raw_scenario: dict[str, Any] = {}
        self._hypotheses: list[str] = []
        self._queries_used: int = 0
        self._rca_submitted: bool = False
        self._submitted_report: RCAReport | None = None
        self._load_scenario()

    def _load_scenario(self) -> None:
        path = _scenario_path(self._difficulty)
        with path.open(encoding="utf-8") as f:
            self._raw_scenario = json.load(f)

    @property
    def raw_scenario(self) -> dict[str, Any]:
        return self._raw_scenario

    def _max_queries(self) -> int:
        return int(self._raw_scenario.get("max_queries", 25))

    def _build_services_metrics(self) -> dict[str, ServiceMetrics]:
        out: dict[str, ServiceMetrics] = {}
        sm = self._raw_scenario.get("service_metrics", {})
        for name, data in sm.items():
            out[name] = ServiceMetrics(
                latency_ms=float(data["latency_ms"]),
                error_rate=float(data["error_rate"]),
                cpu_percent=float(data["cpu_percent"]),
                memory_percent=float(data["memory_percent"]),
                status=data["status"],
            )
        return out

    def _metrics_anomaly_hint(self, m: ServiceMetrics) -> tuple[bool, str | None]:
        if m.status == "down":
            return True, "service_down"
        if m.status == "degraded":
            return True, "degraded"
        if m.error_rate > 0.01 or m.latency_ms > 500:
            return True, "elevated_slo"
        return False, None

    def _queries_remaining(self) -> int:
        return max(0, self._max_queries() - self._queries_used)

    def reset(self) -> EnvironmentState:
        self._load_scenario()
        self._hypotheses = []
        self._queries_used = 0
        self._rca_submitted = False
        self._submitted_report = None
        return self.state()

    def state(self) -> EnvironmentState:
        return EnvironmentState(
            scenario_id=self._raw_scenario["scenario_id"],
            difficulty=self._raw_scenario["difficulty"],
            alert=self._raw_scenario["alert"],
            services=self._build_services_metrics(),
            queries_used=self._queries_used,
            max_queries=self._max_queries(),
            hypotheses=list(self._hypotheses),
            rca_submitted=self._rca_submitted,
            submitted_report=self._submitted_report,
        )

    def step(self, action: Action) -> Observation:
        if action.action_type != ActionType.submit_rca:
            if self._queries_used >= self._max_queries():
                return Observation(
                    success=False,
                    message="Budget exhausted",
                    anomaly_detected=False,
                    queries_remaining=0,
                )

        if action.action_type == ActionType.query_metrics:
            return self._finalize_query(self._handle_query_metrics(action.target_service))
        if action.action_type == ActionType.query_logs:
            return self._finalize_query(self._handle_query_logs(action.target_service))
        if action.action_type == ActionType.pull_traces:
            return self._finalize_query(self._handle_pull_traces(action.target_service))
        if action.action_type == ActionType.query_dependencies:
            return self._finalize_query(self._handle_query_dependencies(action.target_service))
        if action.action_type == ActionType.form_hypothesis:
            return self._finalize_query(self._handle_form_hypothesis(action.hypothesis))
        if action.action_type == ActionType.submit_rca:
            return self._handle_submit_rca(action.rca_report)

        return Observation(
            success=False,
            message="Unknown action",
            anomaly_detected=False,
            queries_remaining=self._queries_remaining(),
        )

    def _finalize_query(self, obs: Observation) -> Observation:
        self._queries_used += 1
        return obs.model_copy(update={"queries_remaining": self._queries_remaining()})

    def _handle_query_metrics(self, service: str | None) -> Observation:
        if not service:
            return Observation(
                success=False,
                service=None,
                message="target_service is required for query_metrics",
                anomaly_detected=False,
                queries_remaining=self._queries_remaining(),
            )
        smap = self._build_services_metrics()
        if service not in smap:
            return Observation(
                success=False,
                service=service,
                message=f"Unknown service: {service}",
                anomaly_detected=False,
                queries_remaining=self._queries_remaining(),
            )
        m = smap[service]
        anom, hint = self._metrics_anomaly_hint(m)
        return Observation(
            success=True,
            service=service,
            metrics=m,
            anomaly_detected=anom,
            anomaly_type=hint,
            message=f"Metrics for {service}",
            queries_remaining=self._queries_remaining(),
        )

    def _handle_query_logs(self, service: str | None) -> Observation:
        if not service:
            return Observation(
                success=False,
                message="target_service is required for query_logs",
                anomaly_detected=False,
                queries_remaining=self._queries_remaining(),
            )
        logs_map = self._raw_scenario.get("logs", {})
        if service not in logs_map:
            return Observation(
                success=False,
                service=service,
                message=f"No logs for service: {service}",
                anomaly_detected=False,
                queries_remaining=self._queries_remaining(),
            )
        lines = list(logs_map[service])
        anom = any(
            k in " ".join(lines).lower()
            for k in (
                "error",
                "timeout",
                "slow",
                "retransmit",
                "stampede",
                "exception",
                "5xx",
                "503",
            )
        )
        return Observation(
            success=True,
            service=service,
            logs=lines,
            anomaly_detected=anom,
            anomaly_type="log_pattern" if anom else None,
            message=f"Logs for {service} ({len(lines)} lines)",
            queries_remaining=self._queries_remaining(),
        )

    def _handle_pull_traces(self, service: str | None) -> Observation:
        if not service:
            return Observation(
                success=False,
                message="target_service is required for pull_traces",
                anomaly_detected=False,
                queries_remaining=self._queries_remaining(),
            )
        traces_map = self._raw_scenario.get("traces", {})
        if service not in traces_map:
            return Observation(
                success=False,
                service=service,
                message=f"No traces for service: {service}",
                anomaly_detected=False,
                queries_remaining=self._queries_remaining(),
            )
        traces = list(traces_map[service])
        anom = any(
            str(t.get("status", "")).lower() in ("error", "degraded") for t in traces
        )
        return Observation(
            success=True,
            service=service,
            traces=traces,
            anomaly_detected=anom,
            anomaly_type="trace_status" if anom else None,
            message=f"Traces for {service} ({len(traces)} spans)",
            queries_remaining=self._queries_remaining(),
        )

    def _handle_query_dependencies(self, service: str | None) -> Observation:
        if not service:
            return Observation(
                success=False,
                message="target_service is required for query_dependencies",
                anomaly_detected=False,
                queries_remaining=self._queries_remaining(),
            )
        dep = self._raw_scenario.get("dependencies", {})
        if service not in dep:
            return Observation(
                success=False,
                service=service,
                message=f"No dependency graph for service: {service}",
                anomaly_detected=False,
                queries_remaining=self._queries_remaining(),
            )
        d = dep[service]
        body = {"upstream": list(d.get("upstream", [])), "downstream": list(d.get("downstream", []))}
        return Observation(
            success=True,
            service=service,
            dependencies=body,
            anomaly_detected=False,
            message=f"Dependencies for {service}",
            queries_remaining=self._queries_remaining(),
        )

    def _handle_form_hypothesis(self, hypothesis: str | None) -> Observation:
        if not hypothesis or not hypothesis.strip():
            return Observation(
                success=False,
                message="hypothesis is required for form_hypothesis",
                anomaly_detected=False,
                queries_remaining=self._queries_remaining(),
            )
        self._hypotheses.append(hypothesis.strip())
        return Observation(
            success=True,
            message="Hypothesis recorded",
            anomaly_detected=False,
            queries_remaining=self._queries_remaining(),
        )

    def _handle_submit_rca(self, report: RCAReport | None) -> Observation:
        if report is None:
            return Observation(
                success=False,
                message="rca_report is required for submit_rca",
                anomaly_detected=False,
                queries_remaining=self._queries_remaining(),
            )
        self._submitted_report = report
        self._rca_submitted = True
        return Observation(
            success=True,
            message="RCA submitted; call /grader to score",
            anomaly_detected=False,
            queries_remaining=self._queries_remaining(),
        )
