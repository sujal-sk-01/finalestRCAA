"""Deterministic grader plus LLM rubric for report quality."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import google.generativeai as genai

from models import EnvironmentState, RCAReport

from server.llm import get_grader_model


def _root_cause_component(report: RCAReport, gt: dict[str, Any]) -> float:
    svc_ok = 1.0 if report.root_cause_service == gt.get("root_cause_service") else 0.0
    type_ok = 1.0 if report.root_cause_type == gt.get("root_cause_type") else 0.0
    return 0.6 * svc_ok + 0.4 * type_ok


def _gt_order_preserved(rep_chain: list[str], gt_chain: list[str]) -> bool:
    idx = 0
    for item in gt_chain:
        while idx < len(rep_chain) and rep_chain[idx] != item:
            idx += 1
        if idx >= len(rep_chain):
            return False
        idx += 1
    return True


def _causal_path_score(report: RCAReport, gt: dict[str, Any]) -> float:
    gt_chain = list(gt.get("causal_chain", []))
    rep_chain = list(report.causal_chain)
    if not gt_chain:
        return 1.0
    gt_set = set(gt_chain)
    rep_set = set(rep_chain)
    inter = len(gt_set & rep_set)
    base = inter / len(gt_chain)
    order_mult = 1.0 if _gt_order_preserved(rep_chain, gt_chain) else 0.5
    return base * order_mult


def _efficiency_score(state: EnvironmentState, gt: dict[str, Any]) -> float:
    optimal = int(gt.get("optimal_queries", 1))
    used = int(state.queries_used)
    if used <= optimal:
        return 1.0
    if used <= int(optimal * 1.5):
        return 0.7
    if used <= optimal * 2:
        return 0.4
    return 0.1


def _report_quality_score(report: RCAReport, ground_truth: dict[str, Any]) -> float:
    if not os.getenv("GOOGLE_API_KEY"):
        return 0.5
    model = get_grader_model()
    if model is None:
        return 0.5
    rubric_prompt = (
        "You output only valid JSON with keys score (number) and reason (string).\n\n"
        "Score this RCA report from 0.0 to 1.0 based on:\n"
        " - Technical accuracy (0.4)\n"
        " - Clarity of explanation (0.3)\n"
        " - Actionability of fix recommendation (0.3)\n"
        f"Ground truth root cause: {json.dumps(ground_truth)}\n"
        f"Agent report: {report.model_dump_json()}\n"
        'Return ONLY a JSON: {"score": float, "reason": str}'
    )
    try:
        try:
            gc = genai.types.GenerationConfig(temperature=0)
            response = model.generate_content(rubric_prompt, generation_config=gc)
        except Exception:
            response = model.generate_content(rubric_prompt)
        raw = response.text or ""
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        result = json.loads(match.group()) if match else {"score": 0.5}
        score = float(result.get("score", 0.5))
        return max(0.0, min(1.0, score))
    except Exception:
        return 0.5


def grade(report: RCAReport, state: EnvironmentState, scenario: dict[str, Any]) -> dict[str, Any]:
    gt = scenario.get("ground_truth", {})
    root_cause_score = _root_cause_component(report, gt)
    causal_path_score = _causal_path_score(report, gt)
    efficiency_score = _efficiency_score(state, gt)
    report_quality_score = _report_quality_score(report, gt)
    final_score = (
        0.40 * root_cause_score
        + 0.25 * causal_path_score
        + 0.20 * efficiency_score
        + 0.15 * report_quality_score
    )
    return {
        "final_score": final_score,
        "root_cause_score": root_cause_score,
        "causal_path_score": causal_path_score,
        "efficiency_score": efficiency_score,
        "report_quality_score": report_quality_score,
        "weights": {
            "root_cause": 0.40,
            "causal_path": 0.25,
            "efficiency": 0.20,
            "report_quality": 0.15,
        },
    }
