"""Heuristic risk-scoring rules engine for AML/mule-account behavior.

Detects patterns that purely topological or statistical embeddings may under-represent:
1. Transaction Velocity Bursts (sudden spike in transfer rate)
2. Mule Pass-Through / Layering (inflow nearly equal to outflow within short window)
3. Geographic / IP Anomalous Shifts
4. Guilt-by-Association / High-Risk Neighbor Concentration
5. Structuring / Smurfing (repeated transfers just below KYC/reporting thresholds)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import numpy as np


@dataclass
class RuleViolation:
    rule_id: str
    rule_name: str
    severity: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    score_penalty: float
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HeuristicRiskResult:
    account_id: str
    heuristic_score: float  # [0.0, 1.0]
    violations: list[RuleViolation]
    rule_breakdown: dict[str, float]


class HeuristicEngine:
    """Configurable AML rule evaluation engine."""

    def __init__(
        self,
        velocity_window_hours: float = 24.0,
        velocity_threshold_tx: int = 15,
        passthrough_margin: float = 0.15,
        smurfing_threshold: float = 49000.0,
    ):
        self.velocity_window_hours = velocity_window_hours
        self.velocity_threshold_tx = velocity_threshold_tx
        self.passthrough_margin = passthrough_margin
        self.smurfing_threshold = smurfing_threshold

    def evaluate_account(
        self,
        account_id: str,
        in_degree: int,
        out_degree: int,
        inflow_amount: float,
        outflow_amount: float,
        neighbor_scores: list[float],
        timestamps: list[float] | None = None,
        tx_amounts: list[float] | None = None,
        geo_locations: list[str] | None = None,
    ) -> HeuristicRiskResult:
        violations: list[RuleViolation] = []
        breakdown: dict[str, float] = {}

        # Rule 1: Mule Pass-Through / Layering Detection
        # Inflow and outflow closely balanced with short retention
        total_flow = inflow_amount + outflow_amount
        if total_flow > 1000.0 and in_degree > 0 and out_degree > 0:
            ratio = min(inflow_amount, outflow_amount) / max(inflow_amount, outflow_amount)
            if ratio >= (1.0 - self.passthrough_margin):
                score_contrib = 0.35 * ratio
                violations.append(
                    RuleViolation(
                        rule_id="RULE-LAYER-01",
                        rule_name="Rapid Mule Pass-Through (Layering)",
                        severity="HIGH",
                        score_penalty=score_contrib,
                        reason=f"Inflow ({inflow_amount:,.2f}) balances Outflow ({outflow_amount:,.2f}) within {round((1-ratio)*100, 1)}% parity margin.",
                        metadata={"inflow": inflow_amount, "outflow": outflow_amount, "parity": ratio},
                    )
                )
                breakdown["pass_through"] = score_contrib

        # Rule 2: Transaction Velocity / High Fan-out Burst
        total_deg = in_degree + out_degree
        if total_deg >= self.velocity_threshold_tx:
            # Check timestamps span if available
            burst_penalty = min(0.30, 0.10 + 0.02 * (total_deg - self.velocity_threshold_tx))
            violations.append(
                RuleViolation(
                    rule_id="RULE-VEL-02",
                    rule_name="High-Frequency Velocity Fan-Out",
                    severity="HIGH" if total_deg > 30 else "MEDIUM",
                    score_penalty=burst_penalty,
                    reason=f"High degree connectivity: {total_deg} transactions ({in_degree} in, {out_degree} out).",
                    metadata={"degree": total_deg, "in": in_degree, "out": out_degree},
                )
            )
            breakdown["velocity_burst"] = burst_penalty

        # Rule 3: Guilt-by-Association (High-Risk Neighborhood Infection)
        if neighbor_scores:
            high_risk_nbrs = [s for s in neighbor_scores if s >= 0.70]
            fraction_high_risk = len(high_risk_nbrs) / len(neighbor_scores)
            if fraction_high_risk >= 0.40 and len(neighbor_scores) >= 2:
                penalty = 0.25 * fraction_high_risk
                violations.append(
                    RuleViolation(
                        rule_id="RULE-NEIGHBOR-03",
                        rule_name="High-Risk Neighborhood Clustering",
                        severity="CRITICAL" if fraction_high_risk >= 0.6 else "HIGH",
                        score_penalty=penalty,
                        reason=f"{round(fraction_high_risk * 100)}% of connected adjacent accounts exhibit high risk scores (>= 0.70).",
                        metadata={"high_risk_count": len(high_risk_nbrs), "total_neighbors": len(neighbor_scores)},
                    )
                )
                breakdown["neighbor_infection"] = penalty

        # Rule 4: Structuring / Smurfing Threshold Evasion
        if tx_amounts:
            structuring_hits = [
                amt for amt in tx_amounts
                if (0.85 * self.smurfing_threshold) <= amt < self.smurfing_threshold
            ]
            if len(structuring_hits) >= 2:
                penalty = min(0.25, 0.10 * len(structuring_hits))
                violations.append(
                    RuleViolation(
                        rule_id="RULE-STRUCT-04",
                        rule_name="Structuring / Smurfing Threshold Evasion",
                        severity="MEDIUM",
                        score_penalty=penalty,
                        reason=f"{len(structuring_hits)} transfers clustered just below regulatory reporting thresholds ({self.smurfing_threshold}).",
                        metadata={"hits": structuring_hits},
                    )
                )
                breakdown["structuring"] = penalty

        # Rule 5: Rapid Geo-Location Shift
        if geo_locations and len(set(geo_locations)) >= 3:
            violations.append(
                RuleViolation(
                    rule_id="RULE-GEO-05",
                    rule_name="Impossible Geo-Velocity Shift",
                    severity="HIGH",
                    score_penalty=0.20,
                    reason=f"Account accessed across {len(set(geo_locations))} disjoint geographic locales within rapid monitoring window.",
                    metadata={"distinct_locations": list(set(geo_locations))},
                )
            )
            breakdown["geo_velocity"] = 0.20

        total_score = min(1.0, sum(v.score_penalty for v in violations))
        return HeuristicRiskResult(
            account_id=account_id,
            heuristic_score=round(total_score, 4),
            violations=violations,
            rule_breakdown=breakdown,
        )
