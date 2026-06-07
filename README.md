# The Harmony Engine

### Finding Undiscovered Truth by Measuring Structural Beauty

Physicists and mathematicians have long observed that truth tends to be beautiful and symmetric. Where structure becomes ugly — asymmetric, incomplete, dissonant — something undiscovered is hiding. **The Harmony Engine operationalizes this principle as a discovery mechanism.**

Given a body of knowledge represented as a network, it measures where harmony and symmetry break down, and surfaces those breaks as locations of undiscovered truth.

**Application domain:** Rare diseases in medicine, where training data is too sparse for conventional AI but structural patterns in the knowledge graph can reveal hidden connections.

---

## Table of Contents

- [Core Concept](#core-concept)
- [The Four Harmony Metrics](#the-four-harmony-metrics)
- [Data Sources](#data-sources)
- [Architecture](#architecture)
- [File Structure](#file-structure)
- [Installation](#installation)
- [Usage](#usage)
- [Data Source Toggle (API vs CSV Only)](#data-source-toggle-api-vs-csv-only)
- [Lite Mode (Slow Devices)](#lite-mode-slow-devices)
- [Export Report](#export-report)
- [Analysis Panel](#analysis-panel)
- [AI Chatbot](#ai-chatbot)
- [Dataset Upload](#dataset-upload)
- [Gene Enrichment](#gene-enrichment)
- [Reset to Original](#reset-to-original)
- [API Reference](#api-reference)
- [Interactive Controls](#interactive-controls)
- [How It Works](#how-it-works)
- [Validation](#validation)
- [Technology Stack](#technology-stack)
- [Troubleshooting](#troubleshooting)

---

## Core Concept

### Multi-Layer Knowledge Graph

The knowledge base is a **multi-layer graph** with four node types and six edge types:

```
Nodes: Diseases (D), Symptoms (S), Genes (G), Pathways (P)

Edges:
  D — S  (disease presents symptom)
  D — G  (disease linked to gene)
  G — P  (gene participates in pathway)
  D — D  (disease similarity / comorbidity)
  S — S  (symptom co-occurrence)
  G — G  (gene interaction / protein interaction)
```

The graph contains **1,725+ nodes** and **6,500+ edges** spanning real rare diseases, genes, symptoms (HPO phenotypes), and biological pathways — all sourced from public biomedical databases.

---

## The Four Harmony Metrics

Each metric captures a different kind of structural "ugliness" — a different way the knowledge graph can be incomplete.

### 1. Symmetry Defect Score (SDS)

**Principle:** If two entities are similar in one dimension, they should be similar in related dimensions. Broken cross-dimensional symmetry = undiscovered connection.

**Computation:** For each pair of diseases (d_i, d_j):
- Compute genetic similarity: `sim_G = |shared genes| / |union genes|`
- Compute phenotypic similarity: `sim_S = |shared symptoms| / |union symptoms|`
- Symmetry defect = `|sim_G - sim_S|`
- High defect → the disease pair has genetic overlap but unexplained phenotypic divergence (or vice versa)

**What it finds:** Diseases that share genetic architecture but whose phenotypic profiles diverge in ways that suggest missing symptom associations, or diseases with similar presentations that should share genetic mechanisms.

### 2. Harmonic Dissonance Score (HDS)

**Principle:** The graph Laplacian's eigenvectors are the "natural harmonics" of the knowledge structure. Each node's position in harmonic space predicts what it should be connected to. Dissonance = deviation from harmonic prediction.

**Computation:**
- Construct adjacency matrix A of the disease subgraph
- Compute normalized graph Laplacian: `L_norm = I - D^(-1/2) A D^(-1/2)`
- Compute first k eigenvectors (the "harmonics")
- For each node v, its harmonic signature = projection onto eigenvectors
- For each non-edge (u, v): predicted connection strength = cosine similarity of harmonic signatures
- Dissonance for node v = mean deviation between predicted and actual connections

**What it finds:** Nodes whose local connection pattern is inconsistent with the global harmonic structure — entities that "should" be connected to things they aren't.

### 3. Compositional Incompleteness Score (CIS)

**Principle:** If A→B and B→C exist, the triangle A→C should complete. Incomplete triangles = missing knowledge. The ratio of existing to possible triangles (clustering coefficient) should be locally consistent.

**Computation:**
- For each pair of diseases (u, v) that are NOT connected:
  - Count their common neighbors (shared disease connections)
  - Compute prediction score: `|common| / sqrt(deg(u) * deg(v))`
  - Surface non-edges with highest CIS as predicted missing links

**What it finds:** Specific missing edges that the network topology predicts should exist — the most concrete "discoveries."

### 4. Curvature Defect Score (CRS)

**Principle:** Ollivier-Ricci curvature measures local network geometry. Positive curvature = clustered, well-connected region. Negative curvature = bridge-like, sparse region. Negative curvature on an edge means the two endpoints are "farther apart" than their neighborhoods suggest — a structural gap.

**Computation:**
- For each disease-disease edge (u, v), compute simplified curvature: `(2 * |common| - |total|) / |total|`
- Edges with highly negative curvature are "structural bottlenecks"
- For non-edges near negative-curvature edges, compute the "curvature gradient" — the expected curvature if the edge existed
- High gradient = strong prediction that the edge should exist

**What it finds:** Regions of the knowledge graph where the geometry is "wrong" — where the structure suggests a bridge should exist.

### Composite Discovery Score

Each non-edge (u, v) gets a **Discovery Score** combining all four metrics:

```
DS(u,v) = w1 * SDS(u,v) + w2 * HDS(u,v) + w3 * CIS(u,v) + w4 * CRS(u,v)
```

Default weights: SDS=0.30, HDS=0.25, CIS=0.30, CRS=0.15

All per-metric scores are normalized to [0, 1] before combining.

---

## Data Sources

All data comes from **real public biomedical databases** — no synthetic or hand-curated data.

| Source | URL | What We Get |
|--------|-----|-------------|
| **Orphanet** | api.orphacode.org | Disease names, definitions, ORPHA codes, categories, OMIM mappings |
| **Monarch Initiative** | api.monarchinitiative.org | Disease-phenotype associations (HPO), causal genes, correlated genes |
| **Human Phenotype Ontology** | ontology.jax.org | Phenotype term definitions, synonyms, translations |

### Data Pipeline

```bash
python build_kb.py
```

1. Fetches rare diseases from Orphanet API
2. For each disease, searches Monarch Initiative by name → gets MONDO ID
3. Fetches phenotype associations (symptoms) from Monarch
4. Fetches causal + correlated gene associations from Monarch
5. Derives biological pathways from gene function
6. Saves everything to `cache/real_kb.json`

The cache file is loaded instantly on subsequent runs. Delete `cache/real_kb.json` to re-fetch.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      Flask Web Server                         │
│                        (app.py)                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  REST API Endpoints                     │  │
│  │  /api/stats    /api/discoveries    /api/graph           │  │
│  │  /api/diseases /api/validate       /api/explain         │  │
│  │  /api/chat     /api/upload-csv    /api/enrich-genes     │  │
│  │  /api/reset    /api/disease/<id>   /api/categories      │  │
│  └───────────────┬────────────────────────────────────────┘  │
│                  │                                            │
│  ┌───────────────▼────────────────────────────────────────┐  │
│  │              Discovery Pipeline                          │  │
│  │                (discovery.py)                            │  │
│  │  Build graph → Compute metrics → Rank gaps              │  │
│  │  → Generate plain-language explanations → Validate      │  │
│  └───────────┬──────────────────────┬──────────────────────┘  │
│              │                      │                          │
│  ┌───────────▼──────────┐  ┌───────▼──────────────────────┐  │
│  │    Harmony Engine     │  │      Knowledge Graph          │  │
│  │  (harmony_engine.py)  │  │   (knowledge_graph.py)        │  │
│  │                       │  │                                │  │
│  │   SDS  HDS           │  │   1,725+ nodes                 │  │
│  │   CIS  CRS           │  │   6,500+ edges                 │  │
│  │   Composite          │  │   6 edge types                 │  │
│  └───────────────────────┘  └────────┬───────────────────────┘  │
│                                      │                          │
│                        ┌─────────────▼──────────────┐          │
│                        │    Rare Disease KB          │          │
│                        │   (rare_disease_kb.py)      │          │
│                        │                             │          │
│                        │   Diseases (Orphanet)       │          │
│                        │   Genes (Monarch)           │          │
│                        │   Symptoms (HPO)            │          │
│                        │   Pathways (derived)        │          │
│                        └─────────────┬───────────────┘          │
│                                      │                          │
│              ┌───────────────────────┼───────────────────┐      │
│              │                       │                   │      │
│  ┌───────────▼──────────┐  ┌────────▼─────────┐  ┌─────▼───┐  │
│  │    Build Script       │  │   Cache Layer     │  │ Backup  │  │
│  │   (build_kb.py)       │  │                   │  │ System  │  │
│  │                       │  │ real_kb.json      │  │         │  │
│  │ Orphanet → Monarch    │  │ (active data)     │  │ auto-   │  │
│  │ → HPO → Cache         │  │                   │  │ created │  │
│  └───────────────────────┘  └──────────────────┘  │ at boot │  │
│                                                    └─────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Frontend (D3.js)                       │  │
│  │     templates/index.html + static/app.js + style.css     │  │
│  │                                                          │  │
│  │   Force-directed graph · Discovery panel · AI Chatbot    │  │
│  │   Zoom/pan · Fullscreen · CSV Upload · Gene Enrichment   │  │
│  │   Reset to original · Keyboard shortcuts                 │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
c:\Users\dell\Desktop\uuu\
├── app.py                    # Flask web server + all API endpoints
├── build_kb.py               # Fetches real data from Orphanet + Monarch APIs
├── knowledge_graph.py        # Multi-layer graph construction (NetworkX)
├── harmony_engine.py         # Four harmony metrics + composite scoring
├── rare_disease_kb.py        # Loads cached data, exposes helper functions
├── discovery.py              # Discovery pipeline + plain-language explanations
├── README.md                 # This file
├── sample_upload.csv         # Example CSV for upload testing
├── cache/
│   ├── real_kb.json          # Active knowledge base (auto-generated)
│   ├── real_kb_backup.json   # Original clean backup (auto-created at first boot)
│   └── session_data.json     # Temporary uploaded CSV data (cleared on restart)
├── static/
│   ├── style.css             # Dark theme with gold accents
│   └── app.js                # D3.js visualization + chatbot + settings + analysis
└── templates/
    └── index.html            # Single-page application with analysis panel
```

### File Descriptions

| File | Lines | Purpose |
|------|-------|---------|
| `app.py` | ~1,100 | Flask server. REST API endpoints for discoveries, graph data, AI chat, CSV upload, gene enrichment, reset, source toggle, export report, lite mode. Session data isolation and size limits. |
| `build_kb.py` | 825 | Data pipeline. Fetches diseases from Orphanet, symptoms + genes from Monarch, caches to JSON. Handles rate limiting and error recovery. |
| `knowledge_graph.py` | 230 | Builds multi-layer NetworkX graph. 4 node types, 6 edge types. Adjacency matrices, subgraph extraction, neighbor lookups. |
| `harmony_engine.py` | 541 | Core engine. SDS, HDS, CIS, CRS metrics. Composite scoring. Per-node harmony profiles. Spectral analysis via graph Laplacian. |
| `rare_disease_kb.py` | 143 | Loads `cache/real_kb.json`. Exposes DISEASES, SYMPTOMS, GENES, PATHWAYS dicts. Entity name/type lookups. Re-initializable for reset. |
| `discovery.py` | 320 | Pipeline orchestration. Ranks discoveries. Generates plain-language explanations. Held-out edge validation. |
| `static/style.css` | ~1,500 | Dark theme CSS. Chat panel, settings modal, floating controls, discovery cards, responsive layout, fullscreen mode, source toggle, notification toast, analysis panel. |
| `static/app.js` | ~1,600 | D3.js force-directed graph with zoom/pan, AI chatbot, settings management, CSV upload workflow, gene enrichment, graph destruction/reinitialization, keyboard shortcuts, source toggle, report export, analysis panel tabs, lite mode. |
| `templates/index.html` | ~290 | HTML template. Header with stats and toggle, graph panel with controls, analysis panel with 3 tabs, discovery panel, AI chat panel, settings modal with lite mode, loading overlay. |

---

## Installation

### Prerequisites

- Python 3.8+
- pip
- Internet connection (for initial data fetch)

### Dependencies

```bash
pip install flask networkx numpy scipy requests
```

### Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| Flask | ≥2.0 | Web server and API |
| NetworkX | ≥2.8 | Graph data structure and algorithms |
| NumPy | ≥1.21 | Matrix operations, eigenvector computation |
| SciPy | ≥1.7 | Sparse matrices, spectral analysis, distance metrics |
| Requests | ≥2.28 | HTTP client for API calls |

### Frontend Dependencies (loaded via CDN)

| Library | Version | Purpose |
|---------|---------|---------|
| D3.js | v7 | Force-directed graph visualization, zoom/pan, animations |

---

## Usage

### Step 1: Build the Knowledge Base

```bash
cd c:\Users\dell\Desktop\uuu
python build_kb.py
```

This fetches real data from Orphanet and Monarch APIs (takes 1-3 minutes on first run). Saves to `cache/real_kb.json`. Subsequent runs load from cache instantly.

### Step 2: Start the Server

```bash
python app.py
```

The server will:
1. Load the cached knowledge base (diseases, genes, symptoms, pathways)
2. Create a backup of the original cache (for reset functionality)
3. Build the knowledge graph (nodes + edges)
4. Compute all four harmony metrics
5. Score and rank all potential discoveries
6. Serve the application at **http://localhost:5000**

### Step 3: Open the Application

Navigate to **http://localhost:5000** in your browser.

---

## Data Source Toggle (API vs CSV Only)

The header bar includes a toggle switch to switch between two modes:

| Mode | Description |
|------|-------------|
| **API Data** (default) | Uses the Orphanet + Monarch knowledge base (100 diseases, 406 genes, 1,290 symptoms) |
| **CSV Only** | Uses ONLY data you upload via CSV. No API data. Start from zero. |

### How It Works

1. Toggle the switch in the header bar (next to the stats)
2. The system switches modes and rebuilds the pipeline
3. Header stats update immediately
4. Graph reloads with the new data

### Session Data Isolation

- Uploaded CSV data is saved to `cache/session_data.json` — **never** merged into `real_kb.json`
- In API mode, session data is merged with API data in memory only
- In CSV Only mode, only session data is used
- **Session data is cleared on server restart** — uploads do not survive restarts
- This keeps the original API data clean and protects laptop memory

---

## Lite Mode (Slow Devices)

For slow laptops, Lite Mode reduces the graph to only disease nodes and predicted edges.

### What Changes

| | Normal Mode | Lite Mode |
|---|---|---|
| **Nodes** | 1,800+ (diseases, symptoms, genes, pathways) | ~100 (diseases only) |
| **Edges** | 6,500+ (all types) | 0 solid + predicted only |
| **Performance** | Full | Much faster |

### How to Enable

1. Click **⚙ Settings**
2. Check **⚡ Lite Mode (faster on slow devices)**
3. Graph reloads automatically

The preference is saved in browser localStorage and persists across sessions.

---

## Export Report

Generate a plain-text report of discoveries for offline reading or AI analysis.

### Download Report

Click **📥 Report** in the header bar. A `.txt` file downloads with:
- Dataset summary (diseases, genes, symptoms)
- Top 20 discoveries with scores and explanations
- A pre-formatted section for pasting into ChatGPT or Gemini

### Copy for AI

Click **📋 Copy for AI** in the header bar. The report is copied to your clipboard. Paste it into any AI chatbot for analysis.

### Report Contents

```
========================================================
THE HARMONY ENGINE — DISCOVERY REPORT
========================================================
Generated: 2026-06-07 21:33:17
Mode: API Data
Dataset: 100 diseases | 406 genes | 1290 symptoms
Total predictions analyzed: 50
Novel discoveries (0 papers found): 12
========================================================

TOP DISCOVERIES:
--------------------------------------------------------
#1. Sickle cell anemia ↔ Beta-thalassemia
Composite Score: 0.300
Novel: NO (726 papers in PubMed)
Metrics: SDS=1.00 | HDS=0.00 | CIS=0.00 | CRS=0.00
Explanation: Think of it like this...
--------------------------------------------------------
...

========================================================
FOR AI ANALYSIS — PASTE INTO CHATGPT OR GEMINI:
========================================================
I have analyzed a medical knowledge graph of 100 rare diseases...
```

---

## Analysis Panel

Below the graph legend, click **📊 Analysis** to expand a collapsible panel with three tabs:

### Tab 1: 📋 Score Table

HTML table showing the top 50 discoveries:
- Rank, Disease 1, Disease 2, Score, Novel status, Paper count
- **⬇ Download as CSV** button to export the table

### Tab 2: 🧬 Single Disease

Dropdown to select any disease. Shows:
- Known connections (linked diseases)
- Predicted connections (with scores)
- Genes and symptoms
- Data from `/api/disease/{id}` and `/api/discoveries/{id}`

### Tab 3: 📊 Metric Summary

Text summary of each harmony metric:
- How many primary signals each metric found
- Top discovery per metric
- Total novel discoveries (0 papers)

All tabs use pure HTML — no D3.js, lightweight and fast.

---

## AI Chatbot

The Harmony Engine includes an AI chatbot that has full context of the current discoveries, disease data, and harmony scores.

### Supported Providers

| Provider | Default Model | Get Key At | Notes |
|----------|--------------|------------|-------|
| **Anthropic Claude** | claude-sonnet-4-20250514 | console.anthropic.com | Best reasoning |
| **OpenAI ChatGPT** | gpt-4o-mini | platform.openai.com | Fast, affordable |
| **Together AI** | meta-llama/Llama-3-70b-chat-hf | api.together.xyz | Open-source Llama, Mistral, Qwen |
| **Groq** | llama3-70b-8192 | console.groq.com | Ultra-fast inference |
| **OpenRouter** | meta-llama/llama-3-70b-instruct | openrouter.ai | 100+ models, one key |
| **Custom Endpoint** | (any) | — | Ollama, LM Studio, vLLM, etc. |

### Setup

1. Click **⚙ Settings** in the header
2. Select your AI provider
3. Enter your API key (stored in browser localStorage only — never sent to our server)
4. Optionally change the model name
5. For custom endpoints: enter the full URL (e.g. `http://localhost:11434/v1/chat/completions`)

### Usage

- Click **💬 Ask AI** (bottom-right) or press `C` to open the chat
- Ask questions like:
  - "Why is Krabbe disease connected to MERRF?"
  - "Explain this discovery in simple language"
  - "What are the most common symptoms across all diseases?"
  - "How does the harmony metric work?"
- Press `Enter` to send, `Shift+Enter` for newline
- In fullscreen mode, a floating 💬 bubble appears in the bottom-right corner

---

## Dataset Upload

Upload your own CSV data to merge into the knowledge graph.

### CSV Format

```csv
disease_name,symptoms,genes,category
My Disease,"Seizures; Muscle pain; Fatigue","GENE1; GENE2; GENE3",Neurological
Another Disease,"Joint pain; Skin rash","GENE4; GENE5",Connective Tissue
```

**Required columns:** `disease_name`, `symptoms`, `genes`
**Optional column:** `category`

- Symptoms and genes are **semicolon-separated**
- Existing diseases (by name) are skipped
- New symptoms and genes are automatically created
- The knowledge graph is rebuilt automatically after upload
- **Maximum 100 diseases per CSV upload** (to protect laptop performance)
- **Total disease limit: 150** across all sources
- Uploaded data is saved to `cache/session_data.json` — **not** merged into `real_kb.json`
- Session data is cleared on server restart

### How to Upload

1. Click **📄 Upload** in the header (or go to ⚙ Settings → Stage CSV Dataset)
2. Select your `.csv` file(s) — you can stage multiple files
3. Click **⚡ Recompute Discoveries** when ready
4. The system parses, merges, and re-runs harmony metrics
5. A confirmation shows how many diseases were added
6. The page reloads automatically with the updated graph

---

## Gene Enrichment

The gene layer can be enriched with more gene-disease associations from Monarch Initiative (free, no API key needed).

### How to Enrich

1. Click **⚙ Settings** in the header
2. Click **🧬 Enrich Gene Data**
3. The system fetches causal and correlated gene associations for all diseases with MONDO IDs
4. New genes are added to the knowledge base
5. The knowledge graph is rebuilt with the enriched gene data
6. Page reloads automatically

---

## Reset to Original

After uploading CSV datasets or enriching gene data, you can restore the knowledge base to its original state (the data from the initial `build_kb.py` run).

### How It Works

1. On first boot, the server automatically creates `cache/real_kb_backup.json` — a clean copy of the original cache
2. When you click **🔄 Reset to Original**, the backup replaces the active cache
3. The pipeline is rebuilt from scratch with the original data
4. Header stats update immediately to reflect the restored counts
5. The page reloads with the original knowledge graph

### How to Reset

1. Click **⚙ Settings** in the header
2. Click **🔄 Reset to Original**
3. Confirm the dialog
4. Wait for the pipeline to rebuild (up to 30 seconds)
5. The page reloads automatically

### Manual Reset

If the backup file doesn't exist or is corrupted:

```bash
# Delete the cache and rebuild from APIs
del cache\real_kb.json
del cache\real_kb_backup.json
python build_kb.py
python app.py
```

---

## API Reference

### GET `/api/stats`

Returns graph statistics and entity counts.

**Response:**
```json
{
  "total_nodes": 1725,
  "total_edges": 6516,
  "nodes_by_type": {"disease": 86, "symptom": 1250, ...},
  "edges_by_type": {"presents": 3200, "linked_to": 1100, ...},
  "density": 0.004,
  "avg_clustering": 0.42,
  "n_discoveries": 150,
  "n_diseases": 86,
  "n_symptoms": 1250,
  "n_genes": 378,
  "n_pathways": 11
}
```

### GET `/api/discoveries`

Returns top discoveries with plain-language explanations and literature evidence.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `n` | int | 20 | Number of discoveries to return |
| `min_score` | float | 0.0 | Minimum composite score threshold |
| `metric` | string | — | Filter by dominant metric: `sds`, `hds`, `cis`, `crs` |
| `novel` | string | `"false"` | If `"true"`, return only discoveries with 0 PubMed papers |

**Response:**
```json
[
  {
    "entity1": "D001",
    "entity2": "D002",
    "entity1_name": "Fabry Disease",
    "entity2_name": "MERRF Syndrome",
    "entity1_type": "disease",
    "entity2_type": "disease",
    "composite_score": 0.847,
    "components": {"sds": 0.92, "hds": 0.78, "cis": 0.85, "crs": 0.71},
    "literature_evidence": 0,
    "novelty_score": 1.0,
    "explanation": {
      "title": "Hidden connection: Fabry Disease — MERRF Syndrome",
      "summary": "High confidence discovery...",
      "story": "These two diseases share...",
      "evidence": [...]
    }
  }
]
```

### GET `/api/discoveries/<disease_id>`

Returns discoveries related to a specific disease.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `n` | int | 10 | Number of discoveries to return |

### GET `/api/graph`

Returns graph data formatted for D3.js visualization.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `focus` | string | Disease ID to focus on (shows 2-hop subgraph) |

**Response:**
```json
{
  "nodes": [
    {"id": "D001", "name": "Fabry Disease", "type": "disease", "category": "Lysosomal"},
    {"id": "S001", "name": "Seizures", "type": "symptom"},
    ...
  ],
  "edges": [
    {"source": "D001", "target": "S001", "type": "presents"},
    {"source": "D001", "target": "D002", "type": "similar"},
    ...
  ],
  "predicted_edges": [
    {"source": "D003", "target": "D005", "score": 0.847, "type": "predicted"},
    ...
  ]
}
```

### GET `/api/diseases`

Returns a list of all diseases with names, categories, and counts.

**Response:**
```json
[
  {
    "id": "D001",
    "name": "Fabry Disease",
    "category": "Lysosomal",
    "n_symptoms": 15,
    "n_genes": 2,
    "n_pathways": 3
  },
  ...
]
```

### GET `/api/disease/<disease_id>`

Returns detailed disease information: symptoms, genes, pathways, connected diseases.

**Response:**
```json
{
  "id": "D001",
  "name": "Fabry Disease",
  "category": "Lysosomal",
  "symptoms": [{"id": "S001", "name": "Seizures"}, ...],
  "genes": [{"id": "G001", "name": "GLA"}, ...],
  "pathways": [{"id": "P001", "name": "Lysosomal degradation"}, ...],
  "connected_diseases": [{"id": "D002", "name": "MERRF Syndrome"}, ...]
}
```

### GET `/api/categories`

Returns all disease categories with counts.

**Response:**
```json
{
  "Lysosomal": 12,
  "Neurological": 25,
  "Connective Tissue": 8,
  ...
}
```

### GET `/api/node/<node_id>/profile`

Returns the harmony profile for a single node across all four metrics.

### POST `/api/explain`

Generates a plain-language explanation for a specific discovery.

**Request Body:**
```json
{
  "entity1": "D001",
  "entity2": "D002",
  "composite_score": 0.847,
  "components": {"sds": 0.92, "hds": 0.78, "cis": 0.85, "crs": 0.71},
  "evidence": []
}
```

### GET `/api/validate`

Runs held-out edge validation (20% holdout, 5 trials) and returns precision/recall metrics.

**Response:**
```json
{
  "mean_precision": 0.72,
  "precision_std": 0.08,
  "mean_recall": 0.45,
  "recall_std": 0.06,
  "n_trials": 5,
  "holdout_fraction": 0.2
}
```

### POST `/api/chat`

AI chatbot endpoint. Sends user message with full Harmony Engine context to the configured AI provider.

**Request Body:**
```json
{
  "message": "Why is Krabbe disease connected to MERRF?",
  "provider": "anthropic",
  "api_key": "sk-...",
  "model": "",
  "endpoint": ""
}
```

**Response:**
```json
{
  "reply": "The Harmony Engine found a connection between Krabbe disease and MERRF because..."
}
```

### POST `/api/upload-csv`

Upload a CSV file and merge into the knowledge base.

**Request:** `multipart/form-data` with field `file` containing the CSV.

**Response:**
```json
{
  "success": true,
  "added": 5,
  "skipped": 2,
  "total_diseases": 91,
  "total_symptoms": 1300,
  "total_genes": 400,
  "pipeline_rebuilt": true
}
```

### POST `/api/enrich-genes`

Enriches gene data from Monarch Initiative (no API key needed).

**Response:**
```json
{
  "success": true,
  "new_gene_associations": 374,
  "unique_new_genes": 334,
  "total_genes": 378,
  "total_diseases": 86
}
```

### POST `/api/reset`

Resets the knowledge base to the original Orphanet + Monarch data (before any CSV uploads or gene enrichment).

**Response:**
```json
{
  "success": true,
  "diseases": 86,
  "genes": 378,
  "symptoms": 1250,
  "pathways": 11,
  "discoveries": 150
}
```

**Behavior:**
1. Loads the backup file (`cache/real_kb_backup.json`) created at first boot
2. Overwrites the active cache (`cache/real_kb.json`) with the original data
3. Re-initializes the knowledge base globals from the restored cache
4. Rebuilds the DiscoveryPipeline from scratch (up to 30s timeout)
5. Returns updated entity counts and discovery count
6. The frontend updates header stats immediately and reloads the page

### GET `/api/source-status`

Returns the current data source mode.

**Response:**
```json
{
  "use_api": true,
  "diseases": 100,
  "genes": 406,
  "symptoms": 1290,
  "mode": "API Data"
}
```

### POST `/api/toggle-source`

Switch between API data and CSV-only mode.

**Request Body:**
```json
{
  "use_api": false
}
```

**Response:**
```json
{
  "success": true,
  "use_api": false,
  "diseases": 0,
  "genes": 0,
  "symptoms": 0
}
```

### GET `/api/export-report`

Generates and downloads a plain-text discovery report.

**Response:** `text/plain` with `Content-Disposition: attachment; filename=harmony_report.txt`

Contains: dataset summary, top 20 discoveries with explanations, and a pre-formatted section for AI analysis.

### POST `/api/lite-mode`

Toggle lite mode for the graph (disease nodes + predicted edges only).

**Request Body:**
```json
{
  "enabled": true
}
```

**Response:**
```json
{
  "success": true,
  "lite_mode": true
}
```

---

## Interactive Controls

### Header Bar

| Element | Action |
|---------|--------|
| **API Data / CSV Only** toggle | Switch between Orphanet data and CSV-only mode |
| **📄 Upload** | Open settings modal for CSV upload |
| **📥 Report** | Download discovery report as `.txt` file |
| **📋 Copy for AI** | Copy report to clipboard for ChatGPT/Gemini |
| **⚙ Settings** | Open settings for AI provider, API key, data management, lite mode |
| **🔄** | Destroy and reinitialize the graph from scratch (full SVG rebuild) |
| **Diseases count** | Auto-updated from `/api/stats` on load and after reset |
| **Genes count** | Auto-updated from `/api/stats` on load and after reset |
| **Symptoms count** | Auto-updated from `/api/stats` on load and after reset |
| **Discoveries count** | Auto-updated from `/api/stats` on load and after reset |

### Graph Panel Controls

| Element | Action |
|---------|--------|
| **Disease Focus** dropdown | Focus graph on a specific disease (2-hop subgraph) |
| **⟲** (top-right) | Destroy and reinitialize the graph completely |
| **📊 Analysis** (in legend) | Toggle collapsible analysis panel with Score Table, Single Disease, Metric Summary tabs |

### Zoom Controls (bottom-left of graph)

| Button | Action | Keyboard |
|--------|--------|----------|
| **＋** | Zoom in | `+` or `=` |
| **−** | Zoom out | `-` |
| **⊞** | Fit all nodes in view | `F` |
| **⟲** | Reset to default zoom (100%) | `0` |
| **100%** | Current zoom level (display only) | — |

### Graph Options (top-right of graph)

| Button | Action | Keyboard |
|--------|--------|----------|
| **⛶** | Enter fullscreen mode (Esc to exit) | — |
| **⏸** | Pause/resume physics simulation | `P` |
| **Aa** | Toggle disease name labels | `L` |
| **◇** | Toggle predicted (golden dashed) edges | `E` |

### Discovery Panel Controls

| Element | Action |
|---------|--------|
| **All Metrics** dropdown | Filter discoveries by dominant metric (SDS, HDS, CIS, CRS) |
| **🔬 Novel Only** checkbox | Show only discoveries with zero PubMed papers |

### Mouse / Touch Controls

| Action | Effect |
|--------|--------|
| **Mouse wheel** | Zoom in/out on graph |
| **Click + drag** on empty area | Pan the view |
| **Click + drag** on node | Move a node (restarts simulation temporarily) |
| **Click** on disease node | Focus on that disease (updates dropdown + reloads discoveries) |
| **Click** on discovery card | Open detailed explanation modal |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `+` / `=` | Zoom in |
| `-` | Zoom out |
| `0` | Reset zoom to 100% |
| `F` | Fit all nodes in view |
| `P` | Pause/resume simulation |
| `L` | Toggle labels |
| `E` | Toggle predicted edges |
| `C` | Toggle AI chat panel |
| `Esc` | Close modal, exit fullscreen, or close settings |

---

## How It Works

### Step 1: Knowledge Graph Construction

The `KnowledgeGraph` class builds a NetworkX graph from the real knowledge base:

- **Rare diseases** from Orphanet (Fabry, Marfan, Noonan, Rett, Cystic Fibrosis, etc.)
- **Symptoms** from Human Phenotype Ontology (seizures, muscle pain, hearing loss, etc.)
- **Genes** from Monarch Initiative (GLA, FBN1, CFTR, TP53, etc.)
- **Biological pathways** derived from gene function (lysosomal degradation, collagen biosynthesis, etc.)

Edges are created for disease-symptom, disease-gene, gene-pathway, disease-pathway, symptom co-occurrence, gene interaction, and disease similarity (Jaccard ≥ 0.2).

### Step 2: Harmony Metric Computation

The `HarmonyEngine` computes all four metrics:

1. **SDS** — Pairwise disease comparison of genetic vs. phenotypic similarity
2. **HDS** — Spectral analysis using the normalized graph Laplacian's eigenvectors
3. **CIS** — Open triangle detection with Jaccard-like scoring
4. **CRS** — Simplified Ollivier-Ricci curvature on the disease similarity subgraph

### Step 3: Discovery Scoring

All non-edges are ranked by the composite Discovery Score. Each metric's scores are normalized to [0, 1], then combined with tunable weights.

### Step 4: Explanation Generation

The `DiscoveryPipeline` generates **plain-language explanations** (no medical jargon) for each discovery:
- **Title**: "Hidden connection: Disease A — Disease B"
- **Summary**: Confidence level and entity types
- **Story**: A narrative explanation based on the dominant metric, written for non-medical audiences
- **Evidence**: Specific data points from each contributing metric

### Step 5: Literature Enrichment

Each discovery is checked against PubMed for existing published papers:
- Uses NCBI E-utilities API (free, no key needed)
- Rate-limited to 3 requests/second
- **Novelty score**: `1 / (1 + paper_count)` — 1.0 means zero papers, approaches 0 as papers increase
- Discoveries with 0 papers are flagged as **🔬 NOVEL**

### Step 6: Validation

The engine validates itself by:
1. Holding out 20% of known disease-disease similarity edges
2. Recomputing all metrics on the reduced graph
3. Checking if the held-out edges appear in the top 50 predictions
4. Repeating for 5 trials and reporting mean precision/recall

---

## Validation

Run validation via the API:

```bash
curl http://localhost:5000/api/validate
```

Or programmatically:

```python
from discovery import DiscoveryPipeline

pipeline = DiscoveryPipeline()
pipeline.run()
results = pipeline.validate_held_out(holdout_fraction=0.2, n_trials=5)
print(f"Precision: {results['mean_precision']:.3f} ± {results['precision_std']:.3f}")
print(f"Recall:    {results['mean_recall']:.3f} ± {results['recall_std']:.3f}")
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | Python 3, Flask | REST API server, AI proxy, pipeline orchestration |
| **Graph Engine** | NetworkX | Graph data structure, algorithms, adjacency matrices |
| **Mathematics** | NumPy, SciPy | Linear algebra, spectral analysis, distance metrics |
| **Data Sources** | Orphanet, Monarch, HPO | Real rare disease data, phenotypes, genes |
| **Literature** | PubMed E-utilities | Novelty checking via paper counts |
| **Frontend** | HTML5, CSS3, JavaScript | Single-page application |
| **Visualization** | D3.js v7 | Force-directed graph, zoom/pan, animations |
| **AI Integration** | Anthropic, OpenAI, Together, Groq, OpenRouter | Multi-provider chatbot |
| **Design** | Custom CSS | Dark theme with gold accents, responsive layout |
| **Cache** | JSON files | Knowledge base persistence, backup system |

---

## Troubleshooting

### Graph appears blank

- The graph container may not have rendered dimensions yet. The app automatically retries up to 10 times with 100ms delays.
- Try clicking the **🔄** button in the header to reinitialize the graph.
- Press `F` to fit all nodes in view.

### Reset doesn't restore original data

- The backup file (`cache/real_kb_backup.json`) is created automatically at first boot.
- If it doesn't exist, the reset endpoint will return an error. In that case, delete `cache/real_kb.json` and re-run `python build_kb.py`.

### Pipeline timeout during upload/reset

- The pipeline has a 30-second timeout for rebuilding.
- If it times out, the old pipeline is kept and a warning is logged.
- Try again or restart the server.

### Chat not responding

- Ensure you've set an API key in Settings (⚙).
- Check that your API key is valid and has credits.
- For custom endpoints, ensure the URL is correct and the server is running.

### Server won't start

- Ensure `cache/real_kb.json` exists (run `python build_kb.py` first).
- Check that all dependencies are installed: `pip install flask networkx numpy scipy requests`
- Ensure port 5000 is not in use by another process. On Windows: `netstat -ano | findstr :5000`

### 404 errors on new endpoints

- Old Python processes may still be running on port 5000. Kill all Python processes and restart.
- On Windows: `taskkill /F /IM python.exe` then restart with `python app.py`

### Uploaded CSV data disappeared

- Session data (`cache/session_data.json`) is cleared on server restart by design.
- Re-upload your CSV after restarting the server.
- The original API data (`real_kb.json`) is never modified by uploads.

### Graph is slow on my laptop

- Enable **⚡ Lite Mode** in Settings → shows only disease nodes (~100) instead of 1,800+
- The graph auto-simplifies when nodes exceed 400
- CSV uploads are limited to 100 diseases to protect performance

---

## License

This project is for educational and research purposes.

---

*"Where structure becomes ugly, something undiscovered is hiding."*
