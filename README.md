# MuleTrace – Project Documentation  

> **MuleTrace** (formerly *Mule‑Hunt*) is an open‑source, graph‑neural‑network (GNN) based fraud‑detection system for UPI‑style payment networks. It ships a full end‑to‑end pipeline: synthetic data generation, model training, evaluation, a FastAPI risk‑service with an interactive dashboard, and a native MCP (multi‑agent) investigation server for AI‑assisted queries.

---  

## 1. Project Overview  

- **Goal** – Detect coordinated fraud rings (“mules”) in payment graphs with a data‑driven GNN model and give analysts an intuitive UI to explore risk scores.  
- **Scope** – Whole pipeline from raw CSV transaction logs to a live REST service, plus a language‑model‑driven investigation assistant (MCP).  
- **Status** – Production‑ready prototype (Python 3.11+, supports CPU/GPU training). The repository has been renamed to **MuleTrace** while preserving all original functionality.  

---  

## 2. Setup & Installation Instructions  

| Step | Command (PowerShell) | What it does |
|------|----------------------|--------------|
| **1️⃣ Clone the repo** | `git clone https://github.com/YesitsSaish/SnackOverFlow-MuleTrace.git` | Creates `c:\Codes\Mule-Hunt-main` (your current working folder). |
| **2️⃣ Create a virtual environment** | `python -m venv .venv` | Isolates dependencies. |
| **3️⃣ Activate the env** | `.venv\Scripts\Activate.ps1` | Switches your shell to the env. |
| **4️⃣ Install the package (editable)** | `uv pip install -e .` | Installs `mule-hunt` as an editable package. |
| **5️⃣ Install dev tools** | `.venv\Scripts\pip install ruff pytest` | Linting (`ruff`) and testing (`pytest`). |
| **6️⃣ Verify install** | `.venv\Scripts\upifraud --help` | Should display the CLI help menu. |
| **7️⃣ Run a quick demo** | `make demo` | Generates a synthetic graph, trains a default GCN, and starts the FastAPI dashboard. |

> **Tip:** Keep the virtual environment active while running any further commands.

---  

## 3. Key Features  

- **Synthetic graph generator** – Burst‑style transaction graphs with configurable rings (`src/upifraud/generate.py`).  
- **Dataset builder** – Converts CSV logs into PyG `Data` objects with ring‑aware temporal splits.  
- **Rich feature extraction** – Structural, amount‑based, temporal, and cycle‑based node/edge attributes.  
- **Multiple GNN back‑ends** – GCN, GraphSAGE, GATv2 (with Jumping Knowledge, edge heads).  
- **Training loop with calibration** – Supports cold‑start fallback, edge‑level loss, early stopping.  
- **Evaluation suite** – AUC, AP, Brier score, ring‑recovery, F1 at operating point.  
- **CLI** – Unified entry point (`upifraud`) for generation, training, evaluation, and service orchestration.  
- **FastAPI risk service** – HTTP endpoints + static HTML/JS dashboard (`src/upifraud/api.py`).  
- **MCP investigation server** – Std‑IO based AI agent interface for natural‑language graph queries (`src/upifraud/mcp_server.py`).  
- **Extensible lint & test pipeline** – `ruff` (100‑char line limit) + `pytest`.  

---  

## 4. Technology Stack  

| Layer | Technology | Reason |
|-------|------------|--------|
| **Language** | Python ≥ 3.11 | Mature ML & web ecosystem. |
| **Graph Library** | PyTorch Geometric (PyG) | Efficient GNN primitives & data handling. |
| **Web Framework** | FastAPI | Async‑first, auto‑generated OpenAPI docs, high performance. |
| **CLI** | `argparse` (standard) | No extra deps; easy to extend. |
| **Packaging** | `uv` + `pyproject.toml` | Fast modern build system; editable install support. |
| **Testing** | `pytest` | Powerful fixture system. |
| **Linting** | `ruff` | Very fast, PEP‑8 + custom style enforcement. |
| **MCP** | Custom std‑io server | Enables Antigravity‑style AI agents to query the graph. |
| **Dashboard** | Vanilla HTML/JS (`frontend/`) | Zero‑framework, served directly by FastAPI. |
| **Deployment** | `uvicorn` | ASGI server for FastAPI. |

---  

## 5. Architecture / Workflow  

```mermaid
graph TD
    A[Data Source (CSV)] --> B[Dataset Builder<br/>src/upifraud/dataset.py]
    B --> C[Graph Generator<br/>src/upifraud/generate.py]
    C --> D[Feature Builder<br/>src/upifraud/features.py]
    D --> E[Model Trainer<br/>src/upifraud/train.py]
    E --> F[Evaluation<br/>src/upifraud/evaluate.py]
    E --> G[FastAPI Service<br/>src/upifraud/api.py]
    G --> H[Dashboard (frontend/)]
    G --> I[MCP Server<br/>src/upifraud/mcp_server.py]
    I --> J[Antigravity Agent]
    style A fill:#f9f9f9,stroke:#333,stroke-width:2px
    style H fill:#e0f7fa,stroke:#00796b,stroke-width:2px
```

**Typical pipeline**

1. **Ingest** – CSV → PyG `Data` (ring‑aware temporal splits).  
2. **Generate** – Optionally synthesize bursts for testing.  
3. **Extract** – Compute structural & temporal features.  
4. **Train** – Choose GNN architecture, calibrate, early‑stop.  
5. **Evaluate** – Metric suite prints & logs scores.  
6. **Deploy** – `uvicorn src/upifraud/api:app` serves REST endpoints & static dashboard.  
7. **Investigate** – Launch MCP server; AI agents (e.g., Antigravity) can query the graph and produce human‑readable reports.  

---  

## 6. Dataset / API Information  

### Dataset  

- **Format** – CSV with columns `src_id`, `dst_id`, `timestamp`, `amount` (optional).  
- **Loading** – `load_graph(data_dir: pathlib.Path) → Data`. The loader expects a `Path`; passing a plain string raises an error (see `AGENTS.md`).  
- **Splits** – Ring‑aware temporal splits simulate realistic burst patterns (train/val/test).  

### FastAPI Endpoints (excerpt)  

| Method | Path | Description |
|--------|------|-------------|
| `GET /risk/account/{account_id}` | Returns a `RiskResponse` (score, band, rank). |
| `GET /api/summary` | High‑level stats (accounts, transactions, fraud rate, ring sizes, model version). |
| `GET /api/top?k=50` | Top‑k risky accounts with risk band & degree. |
| `GET /api/ring/{ring_id}` | Detailed ring view (nodes, edges, external connections, top risky transactions). |
| `GET /api/distribution?bins=20` | Histogram of risk scores (bins & counts). |
| `GET /api/explain/{account_id}` | Model‑grounded explanation (local GNNExplainer or OpenAI‑generated). |
| `POST /api/ask` | Natural‑language query → AI‑generated answer. |
| `GET /api/counterfactual/{account_id}?k=3` | Sens# MuleTrace – Project Documentation  

> **MuleTrace** (formerly *Mule‑Hunt*) is an open‑source, graph‑neural‑network (GNN) based fraud‑detection system for UPI‑style payment networks. It ships a full end‑to‑end pipeline: synthetic data generation, model training, evaluation, a FastAPI risk‑service with an interactive dashboard, and a native MCP (multi‑agent) investigation server for AI‑assisted queries.

---  

## 1. Project Overview  

- **Goal** – Detect coordinated fraud rings (“mules”) in payment graphs with a data‑driven GNN model and give analysts an intuitive UI to explore risk scores.  
- **Scope** – Whole pipeline from raw CSV transaction logs to a live REST service, plus a language‑model‑driven investigation assistant (MCP).  
- **Status** – Production‑ready prototype (Python 3.11+, supports CPU/GPU training). The repository has been renamed to **MuleTrace** while preserving all original functionality.  

---  

## 2. Setup & Installation Instructions  

| Step | Command (PowerShell) | What it does |
|------|----------------------|--------------|
| **1️⃣ Clone the repo** | `git clone https://github.com/YesitsSaish/SnackOverFlow-MuleTrace.git` | Creates `c:\Codes\Mule-Hunt-main` (your current working folder). |
| **2️⃣ Create a virtual environment** | `python -m venv .venv` | Isolates dependencies. |
| **3️⃣ Activate the env** | `.venv\Scripts\Activate.ps1` | Switches your shell to the env. |
| **4️⃣ Install the package (editable)** | `uv pip install -e .` | Installs `mule-hunt` as an editable package. |
| **5️⃣ Install dev tools** | `.venv\Scripts\pip install ruff pytest` | Linting (`ruff`) and testing (`pytest`). |
| **6️⃣ Verify install** | `.venv\Scripts\upifraud --help` | Should display the CLI help menu. |
| **7️⃣ Run a quick demo** | `make demo` | Generates a synthetic graph, trains a default GCN, and starts the FastAPI dashboard. |

> **Tip:** Keep the virtual environment active while running any further commands.

---  

## 3. Key Features  

- **Synthetic graph generator** – Burst‑style transaction graphs with configurable rings (`src/upifraud/generate.py`).  
- **Dataset builder** – Converts CSV logs into PyG `Data` objects with ring‑aware temporal splits.  
- **Rich feature extraction** – Structural, amount‑based, temporal, and cycle‑based node/edge attributes.  
- **Multiple GNN back‑ends** – GCN, GraphSAGE, GATv2 (with Jumping Knowledge, edge heads).  
- **Training loop with calibration** – Supports cold‑start fallback, edge‑level loss, early stopping.  
- **Evaluation suite** – AUC, AP, Brier score, ring‑recovery, F1 at operating point.  
- **CLI** – Unified entry point (`upifraud`) for generation, training, evaluation, and service orchestration.  
- **FastAPI risk service** – HTTP endpoints + static HTML/JS dashboard (`src/upifraud/api.py`).  
- **MCP investigation server** – Std‑IO based AI agent interface for natural‑language graph queries (`src/upifraud/mcp_server.py`).  
- **Extensible lint & test pipeline** – `ruff` (100‑char line limit) + `pytest`.  

---  

## 4. Technology Stack  

| Layer | Technology | Reason |
|-------|------------|--------|
| **Language** | Python ≥ 3.11 | Mature ML & web ecosystem. |
| **Graph Library** | PyTorch Geometric (PyG) | Efficient GNN primitives & data handling. |
| **Web Framework** | FastAPI | Async‑first, auto‑generated OpenAPI docs, high performance. |
| **CLI** | `argparse` (standard) | No extra deps; easy to extend. |
| **Packaging** | `uv` + `pyproject.toml` | Fast modern build system; editable install support. |
| **Testing** | `pytest` | Powerful fixture system. |
| **Linting** | `ruff` | Very fast, PEP‑8 + custom style enforcement. |
| **MCP** | Custom std‑io server | Enables Antigravity‑style AI agents to query the graph. |
| **Dashboard** | Vanilla HTML/JS (`frontend/`) | Zero‑framework, served directly by FastAPI. |
| **Deployment** | `uvicorn` | ASGI server for FastAPI. |

---  

## 5. Architecture / Workflow  

```mermaid
graph TD
    A[Data Source (CSV)] --> B[Dataset Builder<br/>src/upifraud/dataset.py]
    B --> C[Graph Generator<br/>src/upifraud/generate.py]
    C --> D[Feature Builder<br/>src/upifraud/features.py]
    D --> E[Model Trainer<br/>src/upifraud/train.py]
    E --> F[Evaluation<br/>src/upifraud/evaluate.py]
    E --> G[FastAPI Service<br/>src/upifraud/api.py]
    G --> H[Dashboard (frontend/)]
    G --> I[MCP Server<br/>src/upifraud/mcp_server.py]
    I --> J[Antigravity Agent]
    style A fill:#f9f9f9,stroke:#333,stroke-width:2px
    style H fill:#e0f7fa,stroke:#00796b,stroke-width:2px
```

**Typical pipeline**

1. **Ingest** – CSV → PyG `Data` (ring‑aware temporal splits).  
2. **Generate** – Optionally synthesize bursts for testing.  
3. **Extract** – Compute structural & temporal features.  
4. **Train** – Choose GNN architecture, calibrate, early‑stop.  
5. **Evaluate** – Metric suite prints & logs scores.  
6. **Deploy** – `uvicorn src/upifraud/api:app` serves REST endpoints & static dashboard.  
7. **Investigate** – Launch MCP server; AI agents (e.g., Antigravity) can query the graph and produce human‑readable reports.  

---  

## 6. Dataset / API Information  

### Dataset  

- **Format** – CSV with columns `src_id`, `dst_id`, `timestamp`, `amount` (optional).  
- **Loading** – `load_graph(data_dir: pathlib.Path) → Data`. The loader expects a `Path`; passing a plain string raises an error (see `AGENTS.md`).  
- **Splits** – Ring‑aware temporal splits simulate realistic burst patterns (train/val/test).  

### FastAPI Endpoints (excerpt)  

| Method | Path | Description |
|--------|------|-------------|
| `GET /risk/account/{account_id}` | Returns a `RiskResponse` (score, band, rank). |
| `GET /api/summary` | High‑level stats (accounts, transactions, fraud rate, ring sizes, model version). |
| `GET /api/top?k=50` | Top‑k risky accounts with risk band & degree. |
| `GET /api/ring/{ring_id}` | Detailed ring view (nodes, edges, external connections, top risky transactions). |
| `GET /api/distribution?bins=20` | Histogram of risk scores (bins & counts). |
| `GET /api/explain/{account_id}` | Model‑grounded explanation (local GNNExplainer or OpenAI‑generated). |
| `POST /api/ask` | Natural‑language query → AI‑generated answer. |
| `GET /api/counterfactual/{account_id}?k=3` | Sensitivity analysis after dropping top‑k edges. |
| `GET /api/case/{account_id}` | Deterministic case file (markdown) for reporting. |
| `GET /` (static) | Serves the HTML/JS dashboard (`frontend/`). |
| `GET /docs` | Swagger UI (auto‑generated). |

All endpoints are documented automatically at `http://localhost:8000/docs`.

---  

## 7. Screenshots / Demo Information  

Because the repo cannot embed external images directly, you can generate a live demo with the built‑in `make demo` target:

```powershell
make demo
```

The demo will:

1. Spin up a synthetic graph.  
2. Train a default GCN model.  
3. Launch the FastAPI service on `http://localhost:8000`.  
4. Open the dashboard in your default browser, showing:  

   - **Node risk heatmap** (color‑coded circles).  
   - **Edge thickness** proportional to transaction amount.  
   - **Real‑time model performance charts** (AUC, Brier score).  

Take screenshots of the dashboard for documentation or presentations.  

---  

## 8. Limitations & Future Scope  

| Limitation | Current Impact | Potential Future Work |
|------------|----------------|-----------------------|
| **Static dataset format** | Only CSV ingestion; no streaming. | Add Parquet/JSONL support and real‑time ingestion pipelines (e.g., Pub/Sub). |
| **Single‑GPU training** | Training limited to one GPU/CPU. | Distributed training via `torch.distributed` or Ray. |
| **Vanilla HTML/JS dashboard** | Lacks advanced UI components (filters, export). | Migrate to a modern front‑end framework (React/Vite) for richer interactivity. |
| **Model catalog limited** | Only GCN, GraphSAGE, GATv2. | Incorporate newer GNN architectures (Graphormer, Transformer‑based GNNs). |
| **MCP server is stdio‑based** | Requires a terminal; no REST/GRPC integration. | Expose MCP via gRPC or HTTP for cloud‑based agents. |
| **No CI/CD pipeline** | Manual `make demo` & `pytest` runs. | Add GitHub Actions for lint, test, and auto‑publish to PyPI. |
| **No privacy safeguards** | Raw transaction data stored in plain CSV. | Implement differential privacy, encryption at rest, and secure data handling. |

---  

## 9. Team Members  

- **Saish Satose** – Project lead, architecture, core GNN pipelines.  
- **Hardik Dandekar** – FastAPI service, dashboard, MCP server.  
- **Shivraj Thorat** – Dataset generation, feature engineering, evaluation suite.  
- **Shubham Makwana** – CI/CD, documentation, testing infrastructure.  

---  



Feel free to copy‑paste any of the above sections into a new `README.md` or documentation site. Let me know if you need further customization (e.g., adding a CI workflow, Dockerfile, or more detailed API docs).
