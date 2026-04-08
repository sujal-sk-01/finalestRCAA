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
    Reward,
    ServiceMetrics,
)


def _scenario_path(difficulty: str) -> Path:
    base = Path(__file__).resolve().parent.parent / "scenarios"
    name = {
        "easy": "easy.json",
        "medium": "medium.json",
        "hard": "hard.json",
        "data_breach": "data_breach.json",
        "ddos": "ddos.json",
    }.get(difficulty.lower())
    if not name:
        raise ValueError(f"Unknown difficulty: {difficulty}")
    return base / name


def _metrics_row_to_model(name: str, data: dict[str, Any]) -> ServiceMetrics:
    """Map scenario JSON service_metrics entry → ServiceMetrics (supports legacy + enriched fields)."""
    cpu_usage = data.get("cpu_usage")
    if cpu_usage is None:
        cpu_usage = float(data.get("cpu_percent", 0.0)) / 100.0
    mem_usage = data.get("memory_usage")
    if mem_usage is None:
        mem_usage = float(data.get("memory_percent", 0.0)) / 100.0
    lat = float(data.get("latency_p99_ms", data.get("latency_ms", 0.0)))
    rps = float(data.get("requests_per_second", 0.0))
    return ServiceMetrics(
        service_name=name,
        error_rate=float(data["error_rate"]),
        latency_p99_ms=lat,
        requests_per_second=rps,
        cpu_usage=float(cpu_usage),
        memory_usage=float(mem_usage),
        status=str(data["status"]),
    )


class RCAEnvironment:
    """OpenEnv-style environment for root-cause analysis on microservice incidents."""

    def __init__(self, difficulty: str) -> None:
        self._difficulty = difficulty.lower()
        self._raw_scenario: dict[str, Any] = {}
        self._hypotheses: list[str] = []
        self._queries_used: int = 0
        self._rca_submitted: bool = False
        self._submitted_report: RCAReport | None = None
        self._episode_reward: float = 0.0
        self._queried: set[str] = set()
        self._current_step: int = 0
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
            out[name] = _metrics_row_to_model(name, data)
        return out

    def _metrics_anomaly_hint(self, m: ServiceMetrics) -> tuple[bool, str | None]:
        if m.status == "down":
            return True, "service_down"
        if m.status == "degraded":
            return True, "degraded"
        if m.error_rate > 0.01 or m.latency_p99_ms > 500:
            return True, "elevated_slo"
        return False, None

    def _queries_remaining(self) -> int:
        return max(0, self._max_queries() - self._queries_used)

    def _compute_step_reward(
        self,
        action_type: str,
        observation_success: bool,
        target_service: str | None = None,
    ) -> Reward:
        """
        Dense reward: relevance, repeat penalty, hypothesis bonus, budget pressure.
        """
        progress = 0.0
        components: dict[str, float] = {}

        gt = self._raw_scenario.get("ground_truth", {})
        root_cause_service = gt.get("root_cause_service", "")
        affected_services = list(gt.get("affected_services", []))

        if action_type in (
            "query_metrics",
            "query_logs",
            "pull_traces",
            "query_dependencies",
        ):
            if not observation_success:
                progress += 0.05
                components["invalid_query"] = 0.05
            else:
                ts = target_service or ""
                if ts == root_cause_service:
                    progress += 0.6
                    components["root_cause_relevance"] = 0.6
                elif ts in affected_services:
                    progress += 0.3
                    components["affected_service_relevance"] = 0.3
                else:
                    progress += 0.1
                    components["valid_query"] = 0.1

                query_key = f"{action_type}:{target_service}"
                if query_key in self._queried:
                    progress = max(0.0, progress - 0.05)
                    components["repeat_penalty"] = -0.05
                else:
                    self._queried.add(query_key)

        elif action_type == "form_hypothesis":
            progress += 0.2
            components["hypothesis_bonus"] = 0.2

        elif action_type == "submit_rca":
            progress += 0.9
            components["submission_attempt"] = 0.9

        mq = max(self._raw_scenario.get("max_queries", 25), 1)
        queries_used_ratio = self._queries_used / mq
        if queries_used_ratio > 0.8:
            penalty = -0.05 * (queries_used_ratio - 0.8) * 10
            progress += penalty
            components["budget_pressure"] = round(penalty, 4)

        step_reward = round(min(1.0, max(0.0, progress)), 4)
        self._episode_reward += step_reward

        return Reward(
            step_reward=step_reward,
            cumulative_reward=round(self._episode_reward, 4),
            reward_components=components,
            done=False,
        )

    def _attach_reward(
        self,
        obs: Observation,
        action_type: str,
        target_service: str | None,
    ) -> Observation:
        rw = self._compute_step_reward(action_type, obs.success, target_service)
        return obs.model_copy(update={"reward": rw})

    def reset(self) -> EnvironmentState:
        self._load_scenario()
        self._hypotheses = []
        self._queries_used = 0
        self._rca_submitted = False
        self._submitted_report = None
        self._episode_reward = 0.0
        self._queried = set()
        self._current_step = 0
        return self.state()

    def state(self) -> EnvironmentState:
        return EnvironmentState(
            scenario_id=self._raw_scenario["scenario_id"],
            difficulty=self._raw_scenario["difficulty"],
            alert=self._raw_scenario["alert"],
            service_metrics=self._build_services_metrics(),
            queries_remaining=self._queries_remaining(),
            max_queries=self._max_queries(),
            hypotheses=list(self._hypotheses),
            rca_submitted=self._rca_submitted,
            submitted_report=self._submitted_report,
            current_step=self._current_step,
            episode_reward=round(self._episode_reward, 4),
        )

    def _is_investigative(self, action: Action) -> bool:
        return action.action_type in (
            ActionType.QUERY_METRICS,
            ActionType.QUERY_LOGS,
            ActionType.PULL_TRACES,
            ActionType.QUERY_DEPENDENCIES,
        )

    def step(self, action: Action) -> Observation:
        self._current_step += 1
        at = action.action_type.value

        if self._is_investigative(action):
            if self._queries_used >= self._max_queries():
                obs = Observation(
                    success=False,
                    message="Budget exhausted",
                    anomaly_detected=False,
                    queries_remaining=0,
                )
                return self._attach_reward(obs, at, action.target_service)

        if action.action_type == ActionType.QUERY_METRICS:
            o = self._handle_query_metrics(action.target_service)
            return self._attach_reward(self._finalize_query(o), at, action.target_service)
        if action.action_type == ActionType.QUERY_LOGS:
            o = self._handle_query_logs(action.target_service)
            return self._attach_reward(self._finalize_query(o), at, action.target_service)
        if action.action_type == ActionType.PULL_TRACES:
            o = self._handle_pull_traces(action.target_service)
            return self._attach_reward(self._finalize_query(o), at, action.target_service)
        if action.action_type == ActionType.QUERY_DEPENDENCIES:
            o = self._handle_query_dependencies(action.target_service)
            return self._attach_reward(self._finalize_query(o), at, action.target_service)
        if action.action_type == ActionType.FORM_HYPOTHESIS:
            o = self._handle_form_hypothesis(action.hypothesis)
            o = o.model_copy(update={"queries_remaining": self._queries_remaining()})
            return self._attach_reward(o, at, action.target_service)
        if action.action_type == ActionType.SUBMIT_RCA:
            o = self._handle_submit_rca(action.rca_report)
            o = o.model_copy(update={"queries_remaining": self._queries_remaining()})
            ro = self._attach_reward(o, at, action.target_service)
            if ro.success and ro.reward:
                ro = ro.model_copy(
                    update={
                        "reward": ro.reward.model_copy(
                            update={"done": True},
                        )
                    }
                )
            return ro

        obs = Observation(
            success=False,
            message="Unknown action",
            anomaly_detected=False,
            queries_remaining=self._queries_remaining(),
        )
        return self._attach_reward(obs, at, action.target_service)

    def _finalize_query(self, obs: Observation) -> Observation:
        self._queries_used += 1
        return obs.model_copy(update={"queries_remaining": self._queries_remaining()})

    def _handle_query_metrics(self, service: str | None) -> Observation:
        if not service:
            return Observation(
                success=False,
                message="target_service is required for query_metrics",
                anomaly_detected=False,
                queries_remaining=self._queries_remaining(),
            )
        smap = self._build_services_metrics()
        if service not in smap:
            return Observation(
                success=False,
                message=f"Unknown service: {service}",
                anomaly_detected=False,
                data={"service": service},
                queries_remaining=self._queries_remaining(),
            )
        m = smap[service]
        anom, hint = self._metrics_anomaly_hint(m)
        return Observation(
            success=True,
            message=f"Metrics for {service}",
            data={"service": service, "metrics": m.model_dump(mode="json")},
            anomaly_detected=anom,
            anomaly_type=hint,
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
                message=f"No logs for service: {service}",
                anomaly_detected=False,
                data={"service": service},
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
            message=f"Logs for {service} ({len(lines)} lines)",
            data={"service": service, "logs": lines},
            anomaly_detected=anom,
            anomaly_type="log_pattern" if anom else None,
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
                message=f"No traces for service: {service}",
                anomaly_detected=False,
                data={"service": service},
                queries_remaining=self._queries_remaining(),
            )
        traces = list(traces_map[service])
        anom = any(str(t.get("status", "")).lower() in ("error", "degraded") for t in traces)
        return Observation(
            success=True,
            message=f"Traces for {service} ({len(traces)} spans)",
            data={"service": service, "traces": traces},
            anomaly_detected=anom,
            anomaly_type="trace_status" if anom else None,
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
                message=f"No dependency graph for service: {service}",
                anomaly_detected=False,
                data={"service": service},
                queries_remaining=self._queries_remaining(),
            )
        d = dep[service]
        body = {"upstream": list(d.get("upstream", [])), "downstream": list(d.get("downstream", []))}
        return Observation(
            success=True,
            message=f"Dependencies for {service}",
            data={"service": service, "dependencies": body},
            anomaly_detected=False,
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
            data={"hypothesis": hypothesis.strip()},
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
            data={"rca_report": report.model_dump(mode="json")},
            anomaly_detected=False,
            queries_remaining=self._queries_remaining(),
        )


