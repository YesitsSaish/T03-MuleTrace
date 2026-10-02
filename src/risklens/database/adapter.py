"""Database adapter for PostgreSQL, Supabase, and SQLite fallback.

Provides:
1. Dynamic ingestion from relational tables into PyTorch Geometric graph data.
2. Direct insertion/updating of live streaming transactions.
3. Persistence of hybrid risk assessments and investigator notes.
4. Flexible connection to hosted Supabase / PostgreSQL instances or local storage.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sqlalchemy import create_engine, text
from torch_geometric.data import Data


class DatabaseAdapter:
    """Enterprise database adapter supporting Postgres, Supabase, and SQLite."""

    def __init__(self, connection_string: str | None = None):
        # Default to SQLite file if SUPABASE_DB_URL or DATABASE_URL not supplied
        if not connection_string:
            connection_string = os.environ.get("SUPABASE_DB_URL") or os.environ.get(
                "DATABASE_URL"
            )
        if not connection_string:
            # Fallback to local SQLite database in workspace
            local_db_path = Path("risklens.db").resolve()
            connection_string = f"sqlite:///{local_db_path}"

        self.connection_string = connection_string
        self.is_sqlite = connection_string.startswith("sqlite")
        self.engine = create_engine(connection_string, pool_pre_ping=True)
        self._init_schema()

    def _init_schema(self) -> None:
        """Applies relational schema if tables do not exist."""
        schema_file = Path(__file__).resolve().parent / "schema.sql"
        if schema_file.exists():
            ddl = schema_file.read_text(encoding="utf-8")
            # SQLite compatibility adjustments for types
            if self.is_sqlite:
                ddl = ddl.replace("TIMESTAMP WITH TIME ZONE", "DATETIME")
                ddl = ddl.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
            with self.engine.begin() as conn:
                for statement in ddl.split(";"):
                    stmt = statement.strip()
                    if stmt:
                        conn.execute(text(stmt))

    def seed_from_graph(self, data: Data) -> None:
        """Seed the database tables from an in-memory PyG Data graph if empty."""
        with self.engine.connect() as conn:
            cnt = conn.execute(text("SELECT COUNT(*) FROM accounts")).scalar()
            if cnt and cnt > 0:
                return  # already populated

        # Prepare accounts dataframe
        n_nodes = data.num_nodes
        node_ids = getattr(data, "node_ids", [f"acc_{i}" for i in range(n_nodes)])
        y = data.y.numpy() if getattr(data, "y", None) is not None else np.zeros(n_nodes)
        ring_ids = data.ring_id.numpy() if getattr(data, "ring_id", None) is not None else np.full(n_nodes, -1)

        accounts_data = []
        for i in range(n_nodes):
            accounts_data.append({
                "account_id": str(node_ids[i]),
                "customer_name": f"Account Entity {node_ids[i]}",
                "account_type": "BUSINESS" if int(ring_ids[i]) >= 0 else "INDIVIDUAL",
                "kyc_status": "VERIFIED" if int(y[i]) == 0 else "FLAGGED",
                "initial_balance": 15000.00,
                "is_seed_fraud": bool(y[i] == 1),
                "ring_id": int(ring_ids[i]),
            })
        df_accounts = pd.DataFrame(accounts_data)

        # Prepare transactions dataframe
        src = data.edge_index[0].numpy()
        dst = data.edge_index[1].numpy()
        n_edges = len(src)
        amounts = data.edge_amounts.numpy() if getattr(data, "edge_amounts", None) is not None else np.random.uniform(500, 25000, n_edges)
        edge_y = data.edge_label.numpy() if getattr(data, "edge_label", None) is not None else np.zeros(n_edges)

        tx_data = []
        for i in range(n_edges):
            tx_data.append({
                "tx_id": f"tx_{i:07d}",
                "src_account_id": str(node_ids[src[i]]),
                "dst_account_id": str(node_ids[dst[i]]),
                "amount": round(float(amounts[i]), 2),
                "currency": "INR",
                "channel": "UPI",
                "geo_location": "MUM_IN" if i % 2 == 0 else "DEL_IN",
                "is_flagged_fraud": bool(edge_y[i] == 1),
            })
        df_tx = pd.DataFrame(tx_data)

        # Bulk write
        with self.engine.begin() as conn:
            df_accounts.to_sql("accounts", conn, if_exists="append", index=False)
            df_tx.to_sql("transactions", conn, if_exists="append", index=False)

    def load_graph_from_db(self) -> tuple[Data, list[str]]:
        """Dynamically ingests accounts and transactions from DB into a PyG Data graph."""
        with self.engine.connect() as conn:
            df_accounts = pd.read_sql(text("SELECT * FROM accounts ORDER BY account_id ASC"), conn)
            df_tx = pd.read_sql(text("SELECT * FROM transactions"), conn)

        node_ids = list(df_accounts["account_id"].astype(str))
        id_to_idx = {aid: i for i, aid in enumerate(node_ids)}
        n_nodes = len(node_ids)

        # Map edges
        valid_edges = df_tx[df_tx["src_account_id"].isin(id_to_idx) & df_tx["dst_account_id"].isin(id_to_idx)]
        src_indices = [id_to_idx[s] for s in valid_edges["src_account_id"]]
        dst_indices = [id_to_idx[d] for d in valid_edges["dst_account_id"]]

        edge_index = torch.tensor([src_indices, dst_indices], dtype=torch.long)
        edge_amounts = torch.tensor(valid_edges["amount"].to_numpy(dtype=float), dtype=torch.float32)
        edge_labels = torch.tensor(valid_edges["is_flagged_fraud"].astype(int).to_numpy(), dtype=torch.long)

        # Labels & Rings
        y = torch.tensor(df_accounts["is_seed_fraud"].astype(int).to_numpy(), dtype=torch.long)
        ring_id = torch.tensor(df_accounts["ring_id"].to_numpy(dtype=int), dtype=torch.long)

        # Construct simple structural node features (degree, log amount, etc.)
        src_np = edge_index[0].numpy()
        dst_np = edge_index[1].numpy()
        in_deg = np.bincount(dst_np, minlength=n_nodes)
        out_deg = np.bincount(src_np, minlength=n_nodes)
        
        amounts_np = edge_amounts.numpy()
        in_flow = np.zeros(n_nodes, dtype=float)
        out_flow = np.zeros(n_nodes, dtype=float)
        for s, d, a in zip(src_np, dst_np, amounts_np):
            out_flow[s] += a
            in_flow[d] += a

        x = torch.tensor(
            np.stack([
                np.log1p(in_deg),
                np.log1p(out_deg),
                np.log1p(in_flow),
                np.log1p(out_flow),
                (in_deg / np.maximum(1, in_deg + out_deg)),
                (out_deg / np.maximum(1, in_deg + out_deg)),
            ], axis=1),
            dtype=torch.float32
        )

        data = Data(
            x=x,
            edge_index=edge_index,
            edge_amounts=edge_amounts,
            edge_label=edge_labels,
            y=y,
            ring_id=ring_id,
        )
        data.node_ids = node_ids
        data.num_nodes = n_nodes
        data.num_rings = int(max(0, ring_id.max().item() + 1))
        return data, node_ids

    def insert_transaction(self, src: str, dst: str, amount: float, channel: str = "UPI", geo: str = "IN") -> str:
        """Records a live real-time transaction into the database."""
        import uuid
        tx_id = f"tx_live_{uuid.uuid4().hex[:8]}"
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO transactions (tx_id, src_account_id, dst_account_id, amount, channel, geo_location)
                    VALUES (:tx_id, :src, :dst, :amount, :channel, :geo)
                    """
                ),
                {"tx_id": tx_id, "src": src, "dst": dst, "amount": amount, "channel": channel, "geo": geo}
            )
        return tx_id

    def save_risk_assessment(
        self,
        account_id: str,
        composite_score: float,
        gnn_score: float,
        heuristic_score: float,
        risk_band: str,
        decision: str,
        violations: list[dict],
        alpha: float,
    ) -> None:
        """Persists evaluated risk assessment log."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO risk_assessments 
                    (account_id, composite_risk_score, gnn_score, heuristic_score, risk_band, decision, violations_json, sensitivity_alpha)
                    VALUES (:aid, :comp, :gnn, :heur, :band, :dec, :viol, :alpha)
                    """
                ),
                {
                    "aid": account_id,
                    "comp": composite_score,
                    "gnn": gnn_score,
                    "heur": heuristic_score,
                    "band": risk_band,
                    "dec": decision,
                    "viol": json.dumps(violations),
                    "alpha": alpha,
                }
            )
