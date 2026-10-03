"""Hybrid Risk Engine combining Graph Neural Networks with Heuristic AML Rules.

Computes a fused risk assessment with dynamically tunable sensitivity:
  CompositeScore = alpha * GNN_score + (1 - alpha) * Heuristic_score
Allows real-time tuning by investigators and hackathon evaluation panels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .heuristics import HeuristicEngine, RuleViolation


@dataclass
class HybridRiskAssessment:
    account_id: str
    composite_score: float
    gnn_score: float
    heuristic_score: float
    risk_band: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    rank: int
    sensitivity_alpha: float
    decision: str  # "ALLOW", "MANUAL_REVIEW", "BLOCK_SUSPEND"
    violations: list[RuleViolation]
    rule_breakdown: dict[str, float]
    graph_context: dict[str, Any]


class HybridRiskEngine:
    def __init__(
        self,
        heuristic_engine: HeuristicEngine | None = None,
        default_alpha: float = 0.65,
        low_threshold: float = 0.35,
        medium_threshold: float = 0.65,
        critical_threshold: float = 0.85,
    ):
        self.heuristic_engine = heuristic_engine or HeuristicEngine()
        self.default_alpha = default_alpha
        self.low_threshold = low_threshold
        self.medium_threshold = medium_threshold
        self.critical_threshold = critical_threshold

    def calculate_band(self, score: float, low_t: float | None = None, med_t: float | None = None, crit_t: float | None = None) -> str:
        low = low_t if low_t is not None else self.low_threshold
        med = med_t if med_t is not None else self.medium_threshold
        crit = crit_t if crit_t is not None else self.critical_threshold

        if score >= crit:
            return "critical"
        if score >= med:
            return "high"
        if score >= low:
            return "medium"
        return "low"

    def make_decision(self, band: str) -> str:
        if band in ("critical", "high"):
            return "BLOCK_SUSPEND"
        if band == "medium":
            return "MANUAL_REVIEW"
        return "ALLOW"

    def evaluate(
        self,
        account_id: str,
        gnn_score: float,
        in_degree: int,
        out_degree: int,
        inflow: float,
        outflow: float,
        neighbor_scores: list[float],
        rank: int = -1,
        alpha: float | None = None,
        low_threshold: float | None = None,
        medium_threshold: float | None = None,
        critical_threshold: float | None = None,
        timestamps: list[float] | None = None,
        tx_amounts: list[float] | None = None,
        geo_locations: list[str] | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> HybridRiskAssessment:
        eff_alpha = self.default_alpha if alpha is None else float(alpha)
        eff_alpha = max(0.0, min(1.0, eff_alpha))

        heuristic_res = self.heuristic_engine.evaluate_account(
            account_id=account_id,
            in_degree=in_degree,
            out_degree=out_degree,
            inflow_amount=inflow,
            outflow_amount=outflow,
            neighbor_scores=neighbor_scores,
            timestamps=timestamps,
            tx_amounts=tx_amounts,
            geo_locations=geo_locations,
        )

        composite = (eff_alpha * gnn_score) + ((1.0 - eff_alpha) * heuristic_res.heuristic_score)
        composite = round(float(np.clip(composite, 0.0, 1.0)), 4)

        band = self.calculate_band(
            composite,
            low_t=low_threshold,
            med_t=medium_threshold,
            crit_t=critical_threshold,
        )
        decision = self.make_decision(band)

        ctx = {
            "degree": in_degree + out_degree,
            "in_degree": in_degree,
            "out_degree": out_degree,
            "inflow": inflow,
            "outflow": outflow,
            "neighbor_count": len(neighbor_scores),
        }
        if extra_context:
            ctx.update(extra_context)

        return HybridRiskAssessment(
            account_id=account_id,
            composite_score=composite,
            gnn_score=round(float(gnn_score), 4),
            heuristic_score=heuristic_res.heuristic_score,
            risk_band=band,
            rank=rank,
            sensitivity_alpha=eff_alpha,
            decision=decision,
            violations=heuristic_res.violations,
            rule_breakdown=heuristic_res.rule_breakdown,
            graph_context=ctx,
        )
