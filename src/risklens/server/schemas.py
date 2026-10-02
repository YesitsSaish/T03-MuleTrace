"""Pydantic V2 request & response schemas for RiskLens API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IngestTransactionRequest(BaseModel):
    src_account_id: str = Field(..., example="acc_00014")
    dst_account_id: str = Field(..., example="acc_00289")
    amount: float = Field(..., gt=0, example=48500.0)
    channel: str = Field("UPI", example="UPI")
    geo_location: str = Field("IN", example="MUM_IN")


class SensitivityConfig(BaseModel):
    alpha: float = Field(0.65, ge=0.0, le=1.0, description="Weight of GNN vs Heuristic rules")
    low_threshold: float = Field(0.35, ge=0.0, le=1.0)
    medium_threshold: float = Field(0.65, ge=0.0, le=1.0)
    critical_threshold: float = Field(0.85, ge=0.0, le=1.0)


class RuleViolationItem(BaseModel):
    rule_id: str
    rule_name: str
    severity: str
    score_penalty: float
    reason: str
    metadata: dict[str, Any] = {}


class AccountRiskSummary(BaseModel):
    account_id: str
    composite_score: float
    gnn_score: float
    heuristic_score: float
    risk_band: str
    rank: int
    decision: str
    violations: list[RuleViolationItem] = []
    degree: int = 0
    in_degree: int = 0
    out_degree: int = 0
    ring_id: int = -1
    true_label: int = 0


class BatchRiskRequest(BaseModel):
    account_ids: list[str]


class SubgraphNode(BaseModel):
    id: str
    label: str
    risk_score: float
    gnn_score: float
    heuristic_score: float
    risk_band: str
    ring_id: int
    true_label: int
    degree: int


class SubgraphEdge(BaseModel):
    src: str
    dst: str
    amount: float
    risk_score: float | None = None
    is_internal_ring: bool = False


class SubgraphResponse(BaseModel):
    center_node: str
    nodes: list[SubgraphNode]
    edges: list[SubgraphEdge]
    ring_id: int


class AskQueryRequest(BaseModel):
    question: str
