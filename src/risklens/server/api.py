"""RiskLens Enterprise Risk Intelligence API.

Serves:
1. GNN + Heuristic hybrid inference with dynamic sensitivity tuning
2. Relational Supabase/PostgreSQL dynamic ingestion & persistence
3. Interactive investigator graph canvas & inspector payloads
4. Command-center metrics, top fraud rings, and compliance reporting
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from torch_geometric.data import Data

from risklens import __version__
from risklens.core.engine import HybridRiskEngine
from risklens.core.models import build_model
from risklens.database.adapter import DatabaseAdapter

from .schemas import (
    AccountRiskSummary,
    IngestTransactionRequest,
    RuleViolationItem,
    SensitivityConfig,
    SubgraphEdge,
    SubgraphNode,
    SubgraphResponse,
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def create_risklens_app(
    checkpoint_dir: Path,
    dataset_path: Path,
    db_adapter: DatabaseAdapter | None = None,
    frontend_dir: Path | None = None,
) -> FastAPI:
    if frontend_dir is None:
        frontend_dir = FRONTEND_DIR

    # Load model checkpoint
    candidates = sorted(p for p in checkpoint_dir.glob("*.pt") if p.stem != "graph")
    if not candidates:
        raise FileNotFoundError(f"No PyTorch model (*.pt) found in {checkpoint_dir}")
    checkpoint = candidates[0]
    args = json.loads((checkpoint_dir / f"{checkpoint.stem}_args.json").read_text())
    state = torch.load(checkpoint, map_location="cpu")

    # Load dataset
    data: Data = torch.load(dataset_path, map_location="cpu", weights_only=False)

    # Standardize and build GNN
    mean = torch.tensor(args["mean"], dtype=torch.float32)
    std = torch.tensor(args["std"], dtype=torch.float32)
    x = (data.x - mean) / torch.clamp(std, min=1e-6)

    model = build_model(
        args["model"],
        int(args["in_dim"]),
        int(args["hidden"]),
        num_layers=int(args.get("num_layers", 2)),
        jk=args.get("jk", "cat"),
        edge_attr_dim=args.get("edge_attr_dim"),
    )
    model.load_state_dict(state)
    model.eval()

    # Precompute GNN scores
    with torch.no_grad():
        raw_gnn_probs = model(x, data.edge_index).sigmoid().numpy().astype(float)

    # Database initialization & seeding
    if db_adapter is None:
        db_adapter = DatabaseAdapter()
    try:
        db_adapter.seed_from_graph(data)
    except Exception as e:
        print(f"[RiskLens DB] Auto-seed notice: {e}")

    # Initialize Hybrid Engine & sensitivity state
    hybrid_engine = HybridRiskEngine(
        default_alpha=0.65,
        low_threshold=0.35,
        medium_threshold=0.65,
        critical_threshold=0.85,
    )

    id_to_idx = {aid: i for i, aid in enumerate(data.node_ids)}
    idx_to_id = {i: aid for aid, i in id_to_idx.items()}
    src = data.edge_index[0].numpy()
    dst = data.edge_index[1].numpy()
    n_edges = len(src)
    n_nodes = data.num_nodes
    edge_amounts = data.edge_amounts.numpy() if hasattr(data, "edge_amounts") else np.ones(n_edges) * 1000.0

    in_degree = np.bincount(dst, minlength=n_nodes)
    out_degree = np.bincount(src, minlength=n_nodes)

    # Neighbor lookup cache
    adjacency: dict[int, list[int]] = {i: [] for i in range(n_nodes)}
    inflows = np.zeros(n_nodes, dtype=float)
    outflows = np.zeros(n_nodes, dtype=float)

    for i in range(n_edges):
        s_idx, d_idx, amt = int(src[i]), int(dst[i]), float(edge_amounts[i])
        adjacency[s_idx].append(d_idx)
        adjacency[d_idx].append(s_idx)
        outflows[s_idx] += amt
        inflows[d_idx] += amt

    # Precompute hybrid scores
    def compute_all_scores(alpha: float, low_t: float, med_t: float, crit_t: float):
        composite_arr = np.zeros(n_nodes, dtype=float)
        assessments = []
        for i in range(n_nodes):
            nbr_scores = [raw_gnn_probs[n] for n in adjacency[i]]
            res = hybrid_engine.evaluate(
                account_id=idx_to_id[i],
                gnn_score=float(raw_gnn_probs[i]),
                in_degree=int(in_degree[i]),
                out_degree=int(out_degree[i]),
                inflow=float(inflows[i]),
                outflow=float(outflows[i]),
                neighbor_scores=nbr_scores,
                alpha=alpha,
                low_threshold=low_t,
                medium_threshold=med_t,
                critical_threshold=crit_t,
            )
            composite_arr[i] = res.composite_score
            assessments.append(res)
        order = np.argsort(-composite_arr)
        rank_map = {int(node_idx): int(r) for r, node_idx in enumerate(order)}
        for i, res in enumerate(assessments):
            res.rank = rank_map[i] + 1
        return composite_arr, order, rank_map, assessments

    current_config = SensitivityConfig()
    composite_scores, current_order, rank_map, assessments_cache = compute_all_scores(
        current_config.alpha,
        current_config.low_threshold,
        current_config.medium_threshold,
        current_config.critical_threshold,
    )

    app = FastAPI(
        title="RiskLens Command Center API",
        version=__version__,
        description="Hybrid Graph Neural Network & Heuristic Fraud Intelligence Platform",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def healthz() -> dict:
        return {
            "status": "healthy",
            "platform": "RiskLens Fraud Intelligence",
            "version": __version__,
            "gnn_model": args["model"],
            "nodes": int(n_nodes),
            "edges": int(n_edges),
            "db_backend": "sqlite" if db_adapter.is_sqlite else "postgresql/supabase",
            "sensitivity": current_config.dict(),
        }

    @app.get("/api/summary")
    def summary() -> dict:
        y = data.y.numpy()
        ring_counts = {}
        for r in np.unique(data.ring_id.numpy()):
            ring_counts[int(r)] = int((data.ring_id.numpy() == r).sum())
        return {
            "platform_name": "RiskLens",
            "version": __version__,
            "n_accounts": int(n_nodes),
            "n_transactions": int(n_edges),
            "n_fraud": int(y.sum()),
            "fraud_rate": round(float(y.mean()), 5),
            "n_rings": int(data.num_rings),
            "model_architecture": f"GraphSAGE (JK=cat, layers={args.get('num_layers', 2)})",
            "hybrid_engine_active": True,
            "sensitivity": current_config.dict(),
            "ring_sizes": {k: v for k, v in sorted(ring_counts.items()) if k >= 0},
        }

    @app.get("/api/sensitivity", response_model=SensitivityConfig)
    def get_sensitivity() -> SensitivityConfig:
        return current_config

    @app.post("/api/sensitivity", response_model=SensitivityConfig)
    def update_sensitivity(cfg: SensitivityConfig) -> SensitivityConfig:
        nonlocal current_config, composite_scores, current_order, rank_map, assessments_cache
        current_config = cfg
        composite_scores, current_order, rank_map, assessments_cache = compute_all_scores(
            cfg.alpha,
            cfg.low_threshold,
            cfg.medium_threshold,
            cfg.critical_threshold,
        )
        return current_config

    @app.get("/api/top", response_model=list[AccountRiskSummary])
    def top_accounts(k: int = Query(50, ge=5, le=500)) -> list[AccountRiskSummary]:
        results = []
        for idx in current_order[:k]:
            res = assessments_cache[idx]
            results.append(
                AccountRiskSummary(
                    account_id=res.account_id,
                    composite_score=res.composite_score,
                    gnn_score=res.gnn_score,
                    heuristic_score=res.heuristic_score,
                    risk_band=res.risk_band,
                    rank=res.rank,
                    decision=res.decision,
                    violations=[
                        RuleViolationItem(
                            rule_id=v.rule_id,
                            rule_name=v.rule_name,
                            severity=v.severity,
                            score_penalty=v.score_penalty,
                            reason=v.reason,
                            metadata=v.metadata,
                        )
                        for v in res.violations
                    ],
                    degree=int(in_degree[idx] + out_degree[idx]),
                    in_degree=int(in_degree[idx]),
                    out_degree=int(out_degree[idx]),
                    ring_id=int(data.ring_id[idx]),
                    true_label=int(data.y[idx]),
                )
            )
        return results

    @app.get("/api/account/{account_id}", response_model=AccountRiskSummary)
    def account_details(account_id: str) -> AccountRiskSummary:
        idx = id_to_idx.get(account_id)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found.")
        res = assessments_cache[idx]
        return AccountRiskSummary(
            account_id=res.account_id,
            composite_score=res.composite_score,
            gnn_score=res.gnn_score,
            heuristic_score=res.heuristic_score,
            risk_band=res.risk_band,
            rank=res.rank,
            decision=res.decision,
            violations=[
                RuleViolationItem(
                    rule_id=v.rule_id,
                    rule_name=v.rule_name,
                    severity=v.severity,
                    score_penalty=v.score_penalty,
                    reason=v.reason,
                    metadata=v.metadata,
                )
                for v in res.violations
            ],
            degree=int(in_degree[idx] + out_degree[idx]),
            in_degree=int(in_degree[idx]),
            out_degree=int(out_degree[idx]),
            ring_id=int(data.ring_id[idx]),
            true_label=int(data.y[idx]),
        )

    @app.get("/api/graph/subgraph/{account_id}", response_model=SubgraphResponse)
    def get_subgraph(account_id: str, hops: int = 1) -> SubgraphResponse:
        idx = id_to_idx.get(account_id)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found.")

        # Collect 1-hop or 2-hop neighborhood
        nodes_set = {idx}
        for nbr in adjacency[idx]:
            nodes_set.add(nbr)
            if hops > 1:
                for second_nbr in adjacency[nbr][:10]:
                    nodes_set.add(second_nbr)

        subgraph_nodes = []
        for n in nodes_set:
            res = assessments_cache[n]
            subgraph_nodes.append(
                SubgraphNode(
                    id=idx_to_id[n],
                    label=idx_to_id[n].replace("acc_", "A"),
                    risk_score=res.composite_score,
                    gnn_score=res.gnn_score,
                    heuristic_score=res.heuristic_score,
                    risk_band=res.risk_band,
                    ring_id=int(data.ring_id[n]),
                    true_label=int(data.y[n]),
                    degree=int(in_degree[n] + out_degree[n]),
                )
            )

        # Collect edges between nodes in subgraph
        subgraph_edges = []
        r_id = int(data.ring_id[idx])
        for i in range(n_edges):
            s_i, d_i = int(src[i]), int(dst[i])
            if s_i in nodes_set and d_i in nodes_set:
                is_int = bool(data.ring_id[s_i] == r_id and data.ring_id[d_i] == r_id and r_id >= 0)
                subgraph_edges.append(
                    SubgraphEdge(
                        src=idx_to_id[s_i],
                        dst=idx_to_id[d_i],
                        amount=round(float(edge_amounts[i]), 2),
                        risk_score=round(float(raw_gnn_probs[s_i] * 0.5 + raw_gnn_probs[d_i] * 0.5), 3),
                        is_internal_ring=is_int,
                    )
                )

        return SubgraphResponse(
            center_node=account_id,
            nodes=subgraph_nodes,
            edges=subgraph_edges,
            ring_id=r_id,
        )

    @app.post("/api/transactions/ingest")
    def ingest_transaction(req: IngestTransactionRequest) -> dict:
        """Dynamic relational ingestion endpoint for live streaming transaction graphs."""
        tx_id = db_adapter.insert_transaction(
            src=req.src_account_id,
            dst=req.dst_account_id,
            amount=req.amount,
            channel=req.channel,
            geo=req.geo_location,
        )
        return {
            "status": "success",
            "message": "Transaction ingested into relational schema & live queue",
            "tx_id": tx_id,
            "details": req.dict(),
        }

    @app.get("/api/distribution")
    def distribution(bins: int = 20) -> dict:
        hist, edges = np.histogram(composite_scores, bins=bins, range=(0.0, 1.0))
        return {
            "bins": [round(float(e), 3) for e in edges.tolist()],
            "counts": [int(c) for c in hist],
        }

    @app.get("/api/ring/{ring_id}")
    def ring_view(ring_id: int) -> dict:
        ring_id = int(ring_id)
        if ring_id < 0 or ring_id >= int(data.num_rings):
            raise HTTPException(status_code=404, detail=f"unknown ring {ring_id}")
        members = [i for i in range(data.num_nodes) if int(data.ring_id[i]) == ring_id]
        member_set = set(members)
        edges = []
        transactions = []
        for i in range(n_edges):
            a, b = int(src[i]), int(dst[i])
            if a in member_set and b in member_set:
                edges.append([members.index(a), members.index(b)])
                tx = {
                    "src": members.index(a),
                    "dst": members.index(b),
                    "amount": round(float(edge_amounts[i]), 2),
                    "risk_score": round(float(raw_gnn_probs[a] * 0.5 + raw_gnn_probs[b] * 0.5), 4),
                    "label": int(data.edge_label[i]) if hasattr(data, "edge_label") else 1,
                }
                transactions.append(tx)
        return {
            "ring_id": ring_id,
            "size": len(members),
            "nodes": [
                {
                    "index": j,
                    "account_id": idx_to_id[m],
                    "risk_score": round(float(composite_scores[m]), 4),
                    "gnn_score": round(float(raw_gnn_probs[m]), 4),
                    "risk_band": assessments_cache[m].risk_band,
                    "rank": int(rank_map[m]),
                    "true_label": int(data.y[m]),
                }
                for j, m in enumerate(members)
            ],
            "edges": edges,
            "transactions": transactions,
        }

    # Static mount for high-performance terminal UI
    if frontend_dir is not None and frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app
