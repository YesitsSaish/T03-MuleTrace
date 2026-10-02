"use strict";

/**
 * RiskLens Investigator Console
 * High-performance graph canvas & inspector logic.
 */

const state = {
  summary: null,
  topAccounts: [],
  selectedAccount: null,
  currentSubgraph: null,
  sensitivity: { alpha: 0.65, low: 0.35, med: 0.65, crit: 0.85 },
  highlightRings: false,
};

// Utilities
const $ = (id) => document.getElementById(id);
const fmtMoney = (n) => "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 });

async function apiFetch(endpoint, options = {}) {
  const res = await fetch(endpoint, options);
  if (!res.ok) throw new Error(`HTTP error ${res.status}: ${res.statusText}`);
  return res.json();
}

// Initialize Application
async function initDashboard() {
  try {
    await loadSummary();
    await loadTopQueue();
    setupEventListeners();
  } catch (err) {
    console.error("Dashboard init error:", err);
  }
}

async function loadSummary() {
  const data = await apiFetch("/api/summary");
  state.summary = data;
  $("ticker-nodes").textContent = data.n_accounts.toLocaleString();
  $("ticker-edges").textContent = data.n_transactions.toLocaleString();
  $("ticker-positives").textContent = data.n_fraud.toLocaleString();
  $("ticker-rings").textContent = data.n_rings;
  $("ticker-model").textContent = data.model_architecture;
}

async function loadTopQueue() {
  const accounts = await apiFetch("/api/top?k=50");
  state.topAccounts = accounts;
  const tbody = $("queue-tbody");
  tbody.innerHTML = "";

  accounts.forEach((acc, idx) => {
    const tr = document.createElement("tr");
    tr.dataset.aid = acc.account_id;
    if (idx === 0 && !state.selectedAccount) {
      tr.classList.add("selected");
      state.selectedAccount = acc.account_id;
      inspectAccount(acc.account_id);
    }

    const pillClass = `pill-${acc.risk_band.toLowerCase()}`;
    tr.innerHTML = `
      <td style="color:var(--text-dim);">${idx + 1}</td>
      <td style="font-weight:600;color:#fff;">${acc.account_id}</td>
      <td style="color:var(--accent-amber);">${acc.composite_score.toFixed(3)}</td>
      <td><span class="risk-pill ${pillClass}">${acc.risk_band}</span></td>
      <td style="color:var(--text-dim);">${acc.ring_id >= 0 ? 'R' + acc.ring_id : '—'}</td>
    `;

    tr.addEventListener("click", () => {
      document.querySelectorAll("#queue-tbody tr").forEach((el) => el.classList.remove("selected"));
      tr.classList.add("selected");
      state.selectedAccount = acc.account_id;
      inspectAccount(acc.account_id);
    });

    tbody.appendChild(tr);
  });
}

async function inspectAccount(accountId) {
  try {
    const [dossier, subgraph] = await Promise.all([
      apiFetch(`/api/account/${encodeURIComponent(accountId)}`),
      apiFetch(`/api/graph/subgraph/${encodeURIComponent(accountId)}?hops=1`),
    ]);

    renderDossier(dossier);
    state.currentSubgraph = subgraph;
    renderGraph(subgraph);
  } catch (err) {
    console.error("Inspect error:", err);
  }
}

function renderDossier(d) {
  $("insp-account").textContent = d.account_id;
  $("insp-sub").textContent = `Ego-Network Node // Degree: ${d.degree}`;

  const pillClass = `pill-${d.risk_band.toLowerCase()}`;
  $("insp-band-pill").className = `risk-pill ${pillClass}`;
  $("insp-band-pill").textContent = d.risk_band;

  $("inspector-decision").className = `risk-pill ${pillClass}`;
  $("inspector-decision").textContent = d.decision;

  // Scores
  $("score-comp").textContent = d.composite_score.toFixed(4);
  $("bar-comp").style.width = `${Math.min(100, Math.round(d.composite_score * 100))}%`;

  $("score-gnn").textContent = d.gnn_score.toFixed(4);
  $("bar-gnn").style.width = `${Math.min(100, Math.round(d.gnn_score * 100))}%`;

  $("score-heur").textContent = d.heuristic_score.toFixed(4);
  $("bar-heur").style.width = `${Math.min(100, Math.round(d.heuristic_score * 100))}%`;

  // Forensics
  $("stat-in-deg").textContent = d.in_degree;
  $("stat-out-deg").textContent = d.out_degree;
  $("stat-deg").textContent = d.degree;
  $("stat-ring").textContent = d.ring_id >= 0 ? `Ring ${d.ring_id}` : "None";
  $("stat-label").textContent = d.true_label === 1 ? "FRAUD (Planted Mule)" : "NORMAL (Clean)";
  $("stat-label").style.color = d.true_label === 1 ? "var(--accent-crimson)" : "var(--accent-emerald)";

  // Violations
  const vContainer = $("violations-container");
  vContainer.innerHTML = "";
  if (!d.violations || d.violations.length === 0) {
    vContainer.innerHTML = `<div style="color:var(--text-dim);font-family:var(--font-mono);font-size:11px;">No heuristic rule anomalies triggered. GNN topological score dominates.</div>`;
  } else {
    d.violations.forEach((v) => {
      const card = document.createElement("div");
      card.className = `violation-card ${v.severity}`;
      card.innerHTML = `
        <div class="violation-title">
          <span>${v.rule_name}</span>
          <span style="font-family:var(--font-mono);color:var(--accent-amber);">+${v.score_penalty.toFixed(2)}</span>
        </div>
        <div class="violation-desc">${v.reason}</div>
      `;
      vContainer.appendChild(card);
    });
  }
}

// High-Performance SVG Graph Rendering
function renderGraph(subgraph) {
  const svg = $("network-svg");
  const W = 800, H = 600;
  const cx = W / 2, cy = H / 2;

  const nodes = subgraph.nodes;
  const edges = subgraph.edges;
  const n = nodes.length;

  // Radial layout around center node
  const positions = {};
  const centerNode = nodes.find((n) => n.id === subgraph.center_node) || nodes[0];
  positions[centerNode.id] = { x: cx, y: cy };

  const otherNodes = nodes.filter((n) => n.id !== centerNode.id);
  const radius = Math.min(220, 110 + otherNodes.length * 9);

  otherNodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / (otherNodes.length || 1);
    positions[node.id] = {
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    };
  });

  let html = `
    <defs>
      <radialGradient id="ringGlow" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stop-color="#f59e0b" stop-opacity="0.2" />
        <stop offset="100%" stop-color="#f59e0b" stop-opacity="0.0" />
      </radialGradient>
      <marker id="arrow" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#3f3f46" />
      </marker>
    </defs>
  `;

  // Draw background ring boundary if ring exists
  if (subgraph.ring_id >= 0) {
    html += `<circle cx="${cx}" cy="${cy}" r="${radius + 24}" fill="url(#ringGlow)" stroke="#f59e0b" stroke-dasharray="4 4" stroke-opacity="0.3" />`;
  }

  // Draw Edges
  edges.forEach((edge) => {
    const p1 = positions[edge.src];
    const p2 = positions[edge.dst];
    if (!p1 || !p2) return;

    const isRing = edge.is_internal_ring || state.highlightRings;
    const strokeColor = isRing ? "#f59e0b" : "#27272a";
    const strokeWidth = isRing ? "2.2" : "1.2";

    html += `
      <line 
        x1="${p1.x}" y1="${p1.y}" 
        x2="${p2.x}" y2="${p2.y}" 
        stroke="${strokeColor}" 
        stroke-width="${strokeWidth}" 
        marker-end="url(#arrow)"
        data-src="${edge.src}" 
        data-dst="${edge.dst}"
        data-amt="${edge.amount}"
      />
    `;
  });

  // Draw Nodes
  nodes.forEach((node) => {
    const p = positions[node.id];
    if (!p) return;

    const isCenter = node.id === centerNode.id;
    const r = isCenter ? 14 : 9;

    let fillColor = "#10b981"; // Safe emerald
    if (node.risk_score >= 0.85) fillColor = "#ef4444"; // Crimson
    else if (node.risk_score >= 0.65) fillColor = "#f59e0b"; // Amber
    else if (node.risk_score >= 0.35) fillColor = "#eab308"; // Yellow

    const stroke = isCenter ? "#ffffff" : "#18181b";
    const strokeWidth = isCenter ? "3" : "1.5";

    html += `
      <g class="graph-node-group" data-id="${node.id}" style="cursor:pointer;">
        <circle 
          cx="${p.x}" cy="${p.y}" r="${r}" 
          fill="${fillColor}" 
          stroke="${stroke}" 
          stroke-width="${strokeWidth}" 
        />
        <text 
          x="${p.x}" y="${p.y + r + 13}" 
          fill="${isCenter ? '#ffffff' : '#a1a1aa'}" 
          font-family="JetBrains Mono, monospace" 
          font-size="${isCenter ? 11 : 9}" 
          font-weight="${isCenter ? 700 : 400}"
          text-anchor="middle"
        >
          ${node.label}
        </text>
      </g>
    `;
  });

  svg.innerHTML = html;

  // Add click & hover listeners
  svg.querySelectorAll(".graph-node-group").forEach((group) => {
    const aid = group.dataset.id;
    group.addEventListener("click", () => {
      state.selectedAccount = aid;
      inspectAccount(aid);
    });

    group.addEventListener("mouseenter", (e) => {
      const node = nodes.find((n) => n.id === aid);
      if (!node) return;
      const tt = $("graph-tooltip");
      tt.style.display = "block";
      tt.style.left = `${e.clientX + 10}px`;
      tt.style.top = `${e.clientY + 10}px`;
      tt.innerHTML = `
        <strong>${node.id}</strong><br/>
        Risk Score: ${node.risk_score.toFixed(3)}<br/>
        GNN Score: ${node.gnn_score.toFixed(3)}<br/>
        Degree: ${node.degree}<br/>
        Ring: ${node.ring_id >= 0 ? node.ring_id : 'None'}
      `;
    });

    group.addEventListener("mouseleave", () => {
      $("graph-tooltip").style.display = "none";
    });
  });
}

function setupEventListeners() {
  // Sensitivity slider
  const slider = $("sensitivity-slider");
  slider.addEventListener("input", (e) => {
    const val = Number(e.target.value) / 100;
    $("val-alpha").textContent = val.toFixed(2);
  });

  slider.addEventListener("change", async (e) => {
    const val = Number(e.target.value) / 100;
    state.sensitivity.alpha = val;
    await apiFetch("/api/sensitivity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.sensitivity),
    });
    // Refresh queue & selected inspector
    await loadTopQueue();
    if (state.selectedAccount) {
      inspectAccount(state.selectedAccount);
    }
  });

  // Modal controls
  $("btn-open-ingest").addEventListener("click", () => {
    $("ingest-modal").style.display = "flex";
  });
  $("btn-close-modal").addEventListener("click", () => {
    $("ingest-modal").style.display = "none";
  });
  $("btn-cancel-modal").addEventListener("click", () => {
    $("ingest-modal").style.display = "none";
  });

  // Form submission
  $("ingest-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      src_account_id: $("src-acc").value.trim(),
      dst_account_id: $("dst-acc").value.trim(),
      amount: parseFloat($("amt-acc").value),
      channel: $("chan-acc").value.trim(),
      geo_location: "MUM_IN",
    };
    try {
      await apiFetch("/api/transactions/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      alert(`Transaction logged into relational schema successfully!`);
      $("ingest-modal").style.display = "none";
      await loadSummary();
    } catch (err) {
      alert(`Ingestion error: ${err.message}`);
    }
  });

  // Toggle rings button
  $("btn-toggle-rings").addEventListener("click", () => {
    state.highlightRings = !state.highlightRings;
    if (state.currentSubgraph) renderGraph(state.currentSubgraph);
  });

  $("btn-reset-view").addEventListener("click", () => {
    if (state.selectedAccount) inspectAccount(state.selectedAccount);
  });

  $("btn-export-intel").addEventListener("click", () => {
    if (!state.selectedAccount) return;
    const jsonStr = JSON.stringify(state.currentSubgraph, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `RiskLens_${state.selectedAccount}_Dossier.json`;
    a.click();
    URL.revokeObjectURL(url);
  });
}

document.addEventListener("DOMContentLoaded", initDashboard);
