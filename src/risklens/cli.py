"""RiskLens Command Line Interface.

Unified entry point for:
- Database schema initialization & live seeding
- GNN inference & hybrid rule evaluations
- Interactive investigator dashboard server
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import uvicorn

from risklens import __version__
from risklens.server.api import create_risklens_app
from risklens.database.adapter import DatabaseAdapter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="risklens",
        description="RiskLens: Hybrid GNN & Heuristic Fraud Intelligence Platform",
    )
    parser.add_argument("--version", action="version", version=f"RiskLens {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # serve command
    p_serve = sub.add_parser("serve", help="Launch RiskLens API & Command Center Dashboard")
    p_serve.add_argument("--models-dir", default="models", help="Directory containing GNN checkpoint and graph.pt")
    p_serve.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    p_serve.add_argument("--port", type=int, default=8000, help="Port to bind")
    p_serve.add_argument("--db-url", default=None, help="Postgres/Supabase connection string or SQLite fallback")

    # init-db command
    p_db = sub.add_parser("init-db", help="Initialize relational database schema & seed initial accounts")
    p_db.add_argument("--models-dir", default="models", help="Directory containing graph.pt")
    p_db.add_argument("--db-url", default=None, help="Postgres/Supabase connection string or SQLite fallback")

    args = parser.parse_args(argv)

    if args.cmd == "init-db":
        import torch
        models_dir = Path(args.models_dir)
        graph_path = models_dir / "graph.pt"
        if not graph_path.exists():
            print(f"[Error] Graph file {graph_path} not found.")
            return 1
        data = torch.load(graph_path, map_location="cpu", weights_only=False)
        adapter = DatabaseAdapter(args.db_url)
        adapter.seed_from_graph(data)
        print(f"[Success] Relational database initialized and seeded with {data.num_nodes} accounts and {data.edge_index.size(1)} transactions.")
        return 0

    if args.cmd == "serve":
        models_dir = Path(args.models_dir)
        graph_path = models_dir / "graph.pt"
        if not graph_path.exists():
            print(f"[Error] Graph file {graph_path} not found.")
            return 1

        db = DatabaseAdapter(args.db_url)
        app = create_risklens_app(
            checkpoint_dir=models_dir,
            dataset_path=graph_path,
            db_adapter=db,
        )
        print(f"\n=======================================================")
        print(f" RiskLens Fraud Intelligence Platform v{__version__}  ")
        print(f" Terminal Dashboard: http://{args.host}:{args.port}/ ")
        print(f" Database Backend:   {'SQLite' if db.is_sqlite else 'PostgreSQL/Supabase'}")
        print(f"=======================================================\n")
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
