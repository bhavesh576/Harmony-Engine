"""
The Harmony Engine — Web Application
=====================================
Flask backend serving the discovery API and the interactive
knowledge graph visualization.

Data sources:
  - Orphanet (api.orphacode.org)
  - Monarch Initiative (api.monarchinitiative.org)
  - Human Phenotype Ontology (HPO)

First run: python build_kb.py  (fetches real data from APIs)
Then run:  python app.py       (serves the application)
"""

from flask import Flask, jsonify, render_template, request, Response
import json
import os
import csv
import io
import threading
import requests as http_requests
from datetime import datetime
import psutil
import networkx as nx

# Lower process priority to protect laptop
try:
    p = psutil.Process(os.getpid())
    p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    pass

from discovery import DiscoveryPipeline
import rare_disease_kb as kb_module

app = Flask(__name__)

# Check if knowledge base is loaded
CACHE_FILE = os.path.join(os.path.dirname(__file__), "cache", "real_kb.json")
BACKUP_FILE = os.path.join(os.path.dirname(__file__), "cache", "real_kb_backup.json")
SESSION_FILE = os.path.join(os.path.dirname(__file__), "cache", "session_data.json")

# ── Mode and limits ────────────────────────────────────────────────
USE_API_DATA = True          # True = API mode, False = CSV-only mode
MAX_DISEASES = 50            # Max diseases in memory (protect 8GB RAM)
MAX_CSV_DISEASES = 40        # Max diseases from a single CSV upload
LITE_MODE = False             # Always lite mode (disease nodes only)

# Create backup of the original cache on first run (before any uploads)
if os.path.exists(CACHE_FILE) and not os.path.exists(BACKUP_FILE):
    import shutil
    shutil.copy2(CACHE_FILE, BACKUP_FILE)
    print("  Created backup of original knowledge base.")

# PubMed literature cache (disease_pair → paper_count)
_lit_cache = {}


def _pubmed_count(disease1, disease2):
    """
    Search PubMed for papers mentioning both diseases together.
    Uses the free E-utilities API (no key needed).
    Returns the number of papers found.
    """
    cache_key = tuple(sorted([disease1.lower(), disease2.lower()]))
    if cache_key in _lit_cache:
        return _lit_cache[cache_key]

    # Build search query: "disease1" AND "disease2"
    q1 = disease1.replace("-", " ").split()[0]  # First word for broader match
    q2 = disease2.replace("-", " ").split()[0]
    query = f'"{disease1}" AND "{disease2}"'

    try:
        resp = http_requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "rettype": "json",
                "retmax": 0,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            # Parse XML response (E-utilities returns XML by default)
            text = resp.text
            # Extract count from <Count>N</Count>
            import re
            match = re.search(r"<Count>(\d+)</Count>", text)
            count = int(match.group(1)) if match else 0
            _lit_cache[cache_key] = count
            return count
    except Exception:
        pass

    _lit_cache[cache_key] = 0
    return 0


def _enrich_with_literature(discoveries, max_check=50):
    """
    Add literature_evidence and novelty_score to discoveries.
    Checks PubMed for the top N discoveries (rate-limited).
    """
    import time

    for i, disc in enumerate(discoveries[:max_check]):
        e1 = disc.get("entity1_name", disc["entity1"])
        e2 = disc.get("entity2_name", disc["entity2"])
        count = _pubmed_count(e1, e2)
        disc["literature_evidence"] = count
        # Novelty: 1.0 = zero papers, approaches 0 as papers increase
        disc["novelty_score"] = 1.0 / (1.0 + count)

        # Be polite to PubMed API (3 requests/second without API key)
        if i < max_check - 1:
            time.sleep(0.35)

    # For discoveries beyond max_check, set defaults
    for disc in discoveries[max_check:]:
        disc.setdefault("literature_evidence", -1)  # -1 = not checked
        disc.setdefault("novelty_score", 0.5)

    return discoveries

if not kb_module.DISEASES:
    print("\n" + "=" * 60)
    print("  THE HARMONY ENGINE")
    print("  No cached data found!")
    print("  Run 'python build_kb.py' first to fetch real data.")
    print("=" * 60 + "\n")
    pipeline = None
else:
    print("=" * 60)
    print("  THE HARMONY ENGINE")
    print("  Finding undiscovered truth by measuring structural beauty")
    print("=" * 60)
    try:
        pipeline = DiscoveryPipeline()
        # Run pipeline initialization in a background thread
        def init_pipeline():
            try:
                pipeline.run()
                print("=" * 60)
                print("  Pipeline initialization complete!")
                print("=" * 60)
            except Exception as e:
                print(f"  ERROR: Pipeline init failed: {e}")
                pipeline._discoveries = []
        
        import threading
        init_thread = threading.Thread(target=init_pipeline, daemon=True)
        init_thread.start()
        print("=" * 60)
        print("  Pipeline initializing in background...")
        print("  Serving at http://localhost:5000")
        print("=" * 60)
    except Exception as e:
        print(f"  WARNING: Pipeline creation error: {e}")
        if pipeline is None:
            pipeline = DiscoveryPipeline()
            pipeline._discoveries = []


# ── Page Routes ──────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── API Routes ───────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    """Graph statistics."""
    if not pipeline:
        return jsonify({
            "total_nodes": 0, "total_edges": 0,
            "nodes_by_type": {}, "edges_by_type": {},
            "density": 0, "avg_clustering": 0,
            "n_discoveries": 0, "n_diseases": 0,
            "n_symptoms": 0, "n_genes": 0, "n_pathways": 0,
        })
    stats = pipeline.kg.stats()
    stats["n_discoveries"] = len(pipeline._discoveries or [])
    stats["n_diseases"] = len(kb_module.DISEASES)
    stats["n_symptoms"] = len(kb_module.SYMPTOMS)
    stats["n_genes"] = len(kb_module.GENES)
    stats["n_pathways"] = len(kb_module.PATHWAYS)
    return jsonify(stats)


@app.route("/api/discoveries")
def api_discoveries():
    """Top discoveries with explanations and literature check."""
    if not pipeline:
        return jsonify([])
    n = request.args.get("n", 20, type=int)
    min_score = request.args.get("min_score", 0.0, type=float)
    metric = request.args.get("metric", None)
    novel_only = request.args.get("novel", "false").lower() == "true"

    if metric:
        discoveries = pipeline.discoveries_by_metric(metric, n * 3)
    else:
        discoveries = pipeline.top_discoveries(n * 3, min_score)

    # Add literature evidence to top discoveries
    discoveries = _enrich_with_literature(discoveries, max_check=min(len(discoveries), 40))

    # Filter for novel discoveries if requested
    if novel_only:
        discoveries = [d for d in discoveries if d.get("literature_evidence", -1) == 0]
        # Sort by composite score (highest first)
        discoveries.sort(key=lambda x: -x.get("composite_score", 0))

    # Limit to requested count
    discoveries = discoveries[:n]

    # Add explanations
    results = []
    for disc in discoveries:
        explanation = pipeline.explain_discovery(disc)
        results.append({
            **disc,
            "explanation": explanation,
        })

    return jsonify(results)


@app.route("/api/discoveries/<disease_id>")
def api_discoveries_for_disease(disease_id):
    """Discoveries for a specific disease."""
    if not pipeline:
        return jsonify([])
    n = request.args.get("n", 10, type=int)
    discoveries = pipeline.discoveries_for_disease(disease_id, n * 2)

    # Add literature evidence
    discoveries = _enrich_with_literature(discoveries, max_check=min(len(discoveries), 20))
    discoveries = discoveries[:n]

    results = []
    for disc in discoveries:
        explanation = pipeline.explain_discovery(disc)
        results.append({
            **disc,
            "explanation": explanation,
        })

    return jsonify(results)


@app.route("/api/diseases")
def api_diseases():
    """List all diseases."""
    result = []
    for did, ddata in kb_module.DISEASES.items():
        result.append({
            "id": did,
            "name": ddata["name"],
            "category": ddata["category"],
            "n_symptoms": len(ddata["symptoms"]),
            "n_genes": len(ddata["genes"]),
            "n_pathways": len(ddata["pathways"]),
        })
    result.sort(key=lambda x: x["name"])
    return jsonify(result)


@app.route("/api/disease/<disease_id>")
def api_disease_detail(disease_id):
    """Detailed disease information."""
    if disease_id not in kb_module.DISEASES:
        return jsonify({"error": "Disease not found"}), 404

    ddata = kb_module.DISEASES[disease_id]
    neighbors = pipeline.kg.get_disease_neighbors_by_type(disease_id)

    result = {
        "id": disease_id,
        "name": ddata["name"],
        "category": ddata["category"],
        "symptoms": [{"id": s, "name": kb_module.SYMPTOMS[s]} for s in ddata["symptoms"]],
        "genes": [{"id": g, "name": kb_module.GENES[g]} for g in ddata["genes"]],
        "pathways": [{"id": p, "name": kb_module.PATHWAYS[p]} for p in ddata["pathways"]],
        "connected_diseases": [
            {"id": n, "name": kb_module.get_entity_name(n)}
            for n in neighbors.get("disease", [])
        ],
    }

    return jsonify(result)


@app.route("/api/categories")
def api_categories():
    """List all disease categories."""
    return jsonify(kb_module.get_categories())


@app.route("/api/node/<node_id>/profile")
def api_node_profile(node_id):
    """Harmony profile for a node."""
    if not pipeline:
        return jsonify({"error": "No data loaded. Run build_kb.py first."})
    profile = pipeline.engine.node_harmony_profile(node_id)
    return jsonify(profile)


@app.route("/api/explain", methods=["POST"])
def api_explain():
    """Explain a specific discovery."""
    if not pipeline:
        return jsonify({"error": "No data loaded. Run build_kb.py first."})
    data = request.get_json()
    disc = {
        "entity1": data["entity1"],
        "entity2": data["entity2"],
        "entity1_name": kb_module.get_entity_name(data["entity1"]),
        "entity2_name": kb_module.get_entity_name(data["entity2"]),
        "entity1_type": kb_module.get_entity_type(data["entity1"]),
        "entity2_type": kb_module.get_entity_type(data["entity2"]),
        "composite_score": data.get("composite_score", 0),
        "components": data.get("components", {}),
        "evidence": data.get("evidence", []),
    }
    explanation = pipeline.explain_discovery(disc)
    return jsonify(explanation)


@app.route("/api/validate")
def api_validate():
    """Run held-out edge validation."""
    if not pipeline:
        return jsonify({"error": "No data loaded. Run build_kb.py first."})
    result = pipeline.validate_held_out()
    return jsonify(result)


# ── AI Chat Endpoint ──────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """AI chatbot with full Harmony Engine context."""
    data = request.get_json()
    user_message = data.get("message", "")
    provider = data.get("provider", "anthropic")
    api_key = data.get("api_key", "")
    model = data.get("model", "")
    endpoint = data.get("endpoint", "")

    if not api_key:
        return jsonify({"error": "No API key provided"}), 400
    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    # Build context from current state
    context = _build_chat_context()

    system_prompt = (
        "You are the Harmony Engine AI assistant — an expert in rare disease "
        "research and biomedical knowledge graphs. You have access to the current "
        "state of the Harmony Engine, which measures structural beauty in a "
        "rare disease knowledge graph to find undiscovered connections.\n\n"
        "GUIDELINES:\n"
        "- Explain discoveries in plain language, avoiding medical jargon\n"
        "- When asked about a disease or discovery, use the provided data\n"
        "- Be helpful, concise, and scientifically grounded\n"
        "- If asked about something not in the data, say so honestly\n"
        "- Use the harmony metrics (SDS, HDS, CIS, CRS) to explain WHY a "
        "connection was predicted\n\n"
        f"CURRENT HARMONY ENGINE STATE:\n{context}"
    )

    try:
        if provider == "anthropic":
            reply = _call_anthropic(api_key, system_prompt, user_message, model)
        elif provider == "openai":
            reply = _call_openai(api_key, system_prompt, user_message, model)
        elif provider == "together":
            reply = _call_openai_compatible(
                "https://api.together.xyz/v1/chat/completions",
                api_key, system_prompt, user_message,
                model or "meta-llama/Llama-3-70b-chat-hf"
            )
        elif provider == "groq":
            reply = _call_openai_compatible(
                "https://api.groq.com/openai/v1/chat/completions",
                api_key, system_prompt, user_message,
                model or "llama3-70b-8192"
            )
        elif provider == "openrouter":
            reply = _call_openai_compatible(
                "https://openrouter.ai/api/v1/chat/completions",
                api_key, system_prompt, user_message,
                model or "meta-llama/llama-3-70b-instruct"
            )
        elif provider == "custom":
            if not endpoint:
                return jsonify({"error": "Custom endpoint URL required"}), 400
            reply = _call_openai_compatible(
                endpoint, api_key, system_prompt, user_message,
                model or "default"
            )
        else:
            return jsonify({"error": f"Unknown provider: {provider}"}), 400
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _build_chat_context():
    """Build a text context summary of the current Harmony Engine state."""
    lines = []

    # Stats
    if pipeline:
        stats = pipeline.kg.stats()
        lines.append(f"Graph: {stats['total_nodes']} nodes, {stats['total_edges']} edges")
        lines.append(f"Diseases: {len(kb_module.DISEASES)}, Symptoms: {len(kb_module.SYMPTOMS)}, "
                     f"Genes: {len(kb_module.GENES)}, Pathways: {len(kb_module.PATHWAYS)}")
        lines.append(f"Discoveries: {len(pipeline._discoveries or [])}")

        # Top 10 discoveries
        top = pipeline.top_discoveries(10)
        if top:
            lines.append("\nTop 10 Discoveries:")
            for i, d in enumerate(top):
                e1 = d.get("entity1_name", d["entity1"])
                e2 = d.get("entity2_name", d["entity2"])
                score = d.get("composite_score", 0)
                components = d.get("components", {})
                dominant = max(components, key=components.get) if components else "?"
                lines.append(f"  {i+1}. {e1} — {e2} "
                            f"(score: {score:.3f}, dominant: {dominant})")

        # Disease list (names only, for reference)
        disease_names = [d["name"] for d in kb_module.DISEASES.values()]
        lines.append(f"\nDiseases in database: {', '.join(disease_names[:30])}...")
    else:
        lines.append("No data loaded. Run build_kb.py first.")

    return "\n".join(lines)


def _call_anthropic(api_key, system_prompt, user_message, model=""):
    """Call Anthropic Claude API."""
    resp = http_requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model or "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()
    return result["content"][0]["text"]


def _call_openai(api_key, system_prompt, user_message, model=""):
    """Call OpenAI ChatGPT API."""
    return _call_openai_compatible(
        "https://api.openai.com/v1/chat/completions",
        api_key, system_prompt, user_message,
        model or "gpt-4o-mini"
    )


def _call_openai_compatible(url, api_key, system_prompt, user_message, model):
    """Call any OpenAI-compatible API (Together, Groq, OpenRouter, custom)."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    resp = http_requests.post(
        url,
        headers=headers,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 1024,
        },
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()
    return result["choices"][0]["message"]["content"]


# ── CSV Upload Endpoint ───────────────────────────────────────────────

@app.route("/api/upload-csv", methods=["POST"])
def api_upload_csv():
    """Upload a CSV file and merge into the knowledge base."""
    global pipeline

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename.endswith(".csv"):
        return jsonify({"error": "File must be a .csv"}), 400

    try:
        content = file.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))

        # Validate columns
        required = {"disease_name", "symptoms", "genes"}
        if not required.issubset(set(reader.fieldnames or [])):
            return jsonify({
                "error": f"CSV must have columns: disease_name, symptoms, genes "
                         f"(optional: category). Found: {reader.fieldnames}"
            }), 400

        # Load session data (NOT real_kb.json — keep API data clean)
        session_data = _load_session_data()
        diseases = dict(session_data.get("diseases", {}))
        symptoms = dict(session_data.get("symptoms", {}))
        genes = dict(session_data.get("genes", {}))

        existing_names = {d["name"].lower() for d in diseases.values()}
        added = 0
        skipped = 0
        limited = False
        warning = ""

        for row_num, row in enumerate(reader, start=2):
            # Enforce CSV disease limit
            if added >= MAX_CSV_DISEASES:
                limited = True
                warning = f"Large dataset detected. Limited to {MAX_CSV_DISEASES} diseases to protect performance."
                break
            try:
                # Validate row has required fields
                name = (row.get("disease_name") or "").strip()
                if not name or name.lower() in existing_names:
                    skipped += 1
                    continue

                raw_symptoms = row.get("symptoms", "")
                raw_genes = row.get("genes", "")

                if not raw_symptoms and not raw_genes:
                    skipped += 1
                    continue

                # Parse symptoms
                symptom_ids = []
                for s in [x.strip() for x in raw_symptoms.split(";") if x.strip()]:
                    sid = None
                    for eid, ename in symptoms.items():
                        if ename.lower() == s.lower():
                            sid = eid
                            break
                    if not sid:
                        sid = f"S{len(symptoms)+1:03d}"
                        symptoms[sid] = s
                    symptom_ids.append(sid)

                # Parse genes
                gene_ids = []
                for g in [x.strip() for x in raw_genes.split(";") if x.strip()]:
                    gid = None
                    for eid, ename in genes.items():
                        if ename.lower() == g.lower():
                            gid = eid
                            break
                    if not gid:
                        gid = f"G{len(genes)+1:03d}"
                        genes[gid] = g
                    gene_ids.append(gid)

                category = (row.get("category") or "").strip() or "Uploaded"

                disease_id = f"D{len(diseases)+1:03d}"
                diseases[disease_id] = {
                    "name": name,
                    "orpha_code": "",
                    "monarch_id": "",
                    "omim_codes": [],
                    "category": category,
                    "definition": f"User-uploaded disease: {name}",
                    "symptoms": symptom_ids,
                    "genes": gene_ids,
                    "pathways": [],
                }
                existing_names.add(name.lower())
                added += 1

            except Exception:
                # Skip malformed rows silently
                skipped += 1
                continue

        # Save to session_data.json (NOT real_kb.json)
        session_out = {"diseases": diseases, "symptoms": symptoms, "genes": genes,
                        "pathways": {}, "meta": {"n_diseases": len(diseases),
                        "n_symptoms": len(symptoms), "n_genes": len(genes)}}
        _save_session_data(session_out)

        # If API mode, merge with API data in memory for pipeline
        if USE_API_DATA:
            api_data = _load_cache_data()
            merged = _merge_data(api_data, session_out)
        else:
            merged = session_out

        # Write merged data temporarily for pipeline rebuild
        _save_cache_data(merged)

        # Rebuild pipeline with timeout
        pipeline_rebuilt = False
        try:
            kb_module._init_globals()

            result = [None]
            error = [None]

            def _run_pipeline():
                try:
                    p = DiscoveryPipeline()
                    p.run()
                    result[0] = p
                except Exception as e:
                    error[0] = e

            t = threading.Thread(target=_run_pipeline)
            t.daemon = True
            t.start()
            t.join(timeout=30)  # 30 second timeout

            if t.is_alive():
                # Timeout — pipeline still running, use old one
                print("  WARNING: Pipeline timed out after 30s, keeping existing pipeline")
            elif error[0]:
                print(f"  WARNING: Pipeline error: {error[0]}")
            elif result[0]:
                pipeline = result[0]
                pipeline_rebuilt = True
        except Exception as e:
            print(f"  WARNING: Pipeline rebuild failed: {e}")

        resp = {
            "success": True,
            "added": added,
            "skipped": skipped,
            "total_diseases": len(diseases),
            "total_symptoms": len(symptoms),
            "total_genes": len(genes),
            "pipeline_rebuilt": pipeline_rebuilt,
        }
        if warning:
            resp["warning"] = warning
        return jsonify(resp)

    except Exception as e:
        return jsonify({"error": f"Failed to parse CSV: {str(e)}"}), 500


def _load_cache_data():
    """Load the cache file."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"diseases": {}, "symptoms": {}, "genes": {}, "pathways": {}, "meta": {}}


def _save_cache_data(data):
    """Save to the cache file."""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_session_data():
    """Load session data (uploaded CSV data)."""
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"diseases": {}, "symptoms": {}, "genes": {}, "pathways": {}, "meta": {}}


def _save_session_data(data):
    """Save session data."""
    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _merge_data(api_data, session_data):
    """Merge API data with session data in memory (no disk write of API data)."""
    merged = {
        "diseases": {**api_data.get("diseases", {}), **session_data.get("diseases", {})},
        "symptoms": {**api_data.get("symptoms", {}), **session_data.get("symptoms", {})},
        "genes": {**api_data.get("genes", {}), **session_data.get("genes", {})},
        "pathways": {**api_data.get("pathways", {}), **session_data.get("pathways", {})},
        "meta": api_data.get("meta", {}),
    }
    return merged


# ── Gene Enrichment Endpoint ─────────────────────────────────────────

@app.route("/api/enrich-genes", methods=["POST"])
def api_enrich_genes():
    """Enrich gene data from Monarch Initiative (no API key needed)."""
    global pipeline

    if not kb_module.DISEASES:
        return jsonify({"error": "No data loaded. Run build_kb.py first."}), 400

    try:
        cache_data = _load_cache_data()
        diseases = cache_data.get("diseases", {})
        genes = cache_data.get("genes", {})
        enriched_count = 0
        new_genes = 0

        for did, ddata in diseases.items():
            monarch_id = ddata.get("monarch_id", "")
            if not monarch_id:
                continue

            existing_genes = set(ddata.get("genes", []))

            # Fetch gene associations from Monarch (causal + correlated)
            for category in [
                "biolink:CausalGeneToDiseaseAssociation",
                "biolink:CorrelatedGeneToDiseaseAssociation",
            ]:
                try:
                    resp = http_requests.get(
                        "https://api.monarchinitiative.org/v3/api/association",
                        params={
                            "object": monarch_id,
                            "category": category,
                            "rows": 30,
                        },
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        for item in resp.json().get("items", []):
                            gene_id = item.get("subject", "")
                            gene_name = item.get("subject_label", "")
                            if gene_id and gene_name:
                                gene_key = gene_id.replace("HGNC:", "HGNC_")
                                if gene_key not in genes:
                                    genes[gene_key] = gene_name
                                    new_genes += 1
                                if gene_key not in existing_genes:
                                    existing_genes.add(gene_key)
                                    enriched_count += 1
                except Exception:
                    pass

            ddata["genes"] = list(existing_genes)
            diseases[did] = ddata

        # Save
        cache_data["diseases"] = diseases
        cache_data["genes"] = genes
        cache_data["meta"]["n_genes"] = len(genes)
        _save_cache_data(cache_data)

        # Rebuild pipeline with timeout
        try:
            kb_module._init_globals()

            result = [None]
            def _run():
                try:
                    p = DiscoveryPipeline()
                    p.run()
                    result[0] = p
                except Exception:
                    pass

            t = threading.Thread(target=_run)
            t.daemon = True
            t.start()
            t.join(timeout=30)

            if not t.is_alive() and result[0]:
                pipeline = result[0]
        except Exception as e:
            print(f"  WARNING: Pipeline rebuild failed: {e}")

        return jsonify({
            "success": True,
            "new_gene_associations": enriched_count,
            "unique_new_genes": new_genes,
            "total_genes": len(genes),
            "total_diseases": len(diseases),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Reset Endpoint ──────────────────────────────────────────────────

@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Reset knowledge base to original Orphanet + Monarch data."""
    global pipeline

    # Use the backup file (created at startup before any uploads)
    if not os.path.exists(BACKUP_FILE):
        return jsonify({"error": "No original backup found. Run build_kb.py first."}), 400

    try:
        # Load original backup (untouched by uploads)
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            original_data = json.load(f)

        # Save the clean original data as the active cache
        _save_cache_data(original_data)

        # Rebuild pipeline from scratch with timeout
        try:
            kb_module._init_globals()

            result = [None]
            error = [None]

            def _run():
                try:
                    p = DiscoveryPipeline()
                    p.run()
                    result[0] = p
                except Exception as e:
                    error[0] = e

            t = threading.Thread(target=_run)
            t.daemon = True
            t.start()
            t.join(timeout=30)

            if t.is_alive():
                print("  WARNING: Pipeline timed out after 30s during reset")
            elif error[0]:
                print(f"  WARNING: Pipeline error during reset: {error[0]}")
            elif result[0]:
                pipeline = result[0]
        except Exception as e:
            print(f"  WARNING: Pipeline rebuild failed: {e}")

        # Return complete stats including discovery count
        n_diseases = len(kb_module.DISEASES)
        n_genes = len(kb_module.GENES)
        n_symptoms = len(kb_module.SYMPTOMS)
        n_pathways = len(kb_module.PATHWAYS)
        n_discoveries = len(pipeline._discoveries) if pipeline and pipeline._discoveries else 0

        return jsonify({
            "success": True,
            "diseases": n_diseases,
            "genes": n_genes,
            "symptoms": n_symptoms,
            "pathways": n_pathways,
            "discoveries": n_discoveries,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Data Source Toggle Endpoints ────────────────────────────────────

@app.route("/api/source-status")
def api_source_status():
    """Return current data source mode."""
    return jsonify({
        "use_api": USE_API_DATA,
        "diseases": len(kb_module.DISEASES),
        "genes": len(kb_module.GENES),
        "symptoms": len(kb_module.SYMPTOMS),
        "mode": "API Data" if USE_API_DATA else "CSV Only",
    })


@app.route("/api/toggle-source", methods=["POST"])
def api_toggle_source():
    """Switch between API data and CSV-only mode."""
    global pipeline, USE_API_DATA

    data = request.get_json()
    use_api = data.get("use_api", True)
    USE_API_DATA = bool(use_api)

    try:
        if USE_API_DATA:
            # Load from real_kb.json (API data)
            kb_module._init_globals()
        else:
            # Load only session data
            if os.path.exists(SESSION_FILE):
                with open(SESSION_FILE, "r", encoding="utf-8") as f:
                    session_data = json.load(f)
                # Temporarily write session data as the cache for kb_module to load
                _save_cache_data(session_data)
                kb_module._init_globals()
            else:
                # No session data — empty knowledge base
                empty = {"diseases": {}, "symptoms": {}, "genes": {}, "pathways": {}, "meta": {}}
                _save_cache_data(empty)
                kb_module._init_globals()

        # Rebuild pipeline
        result = [None]
        def _run():
            try:
                p = DiscoveryPipeline()
                p.run()
                result[0] = p
            except Exception:
                pass

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=30)

        if not t.is_alive() and result[0]:
            pipeline = result[0]

        # If switching back to API mode, restore real_kb.json from backup
        if USE_API_DATA and os.path.exists(BACKUP_FILE):
            with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                original = json.load(f)
            _save_cache_data(original)
            kb_module._init_globals()

        return jsonify({
            "success": True,
            "use_api": USE_API_DATA,
            "diseases": len(kb_module.DISEASES),
            "genes": len(kb_module.GENES),
            "symptoms": len(kb_module.SYMPTOMS),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Export Report Endpoint ─────────────────────────────────────────

@app.route("/api/export-report")
def api_export_report():
    """Generate and download a plain-text discovery report."""
    if not pipeline:
        return jsonify({"error": "No data loaded."}), 400

    # Get ALL discoveries
    discoveries = pipeline.top_discoveries(200)
    discoveries = _enrich_with_literature(discoveries, max_check=min(len(discoveries), 30))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_diseases = len(kb_module.DISEASES)
    n_genes = len(kb_module.GENES)
    n_symptoms = len(kb_module.SYMPTOMS)
    n_total = len(discoveries)
    n_novel = sum(1 for d in discoveries if d.get("literature_evidence", -1) == 0)

    # Get disease subgraph for NetworkX metrics
    G = None
    try:
        G = pipeline.kg.G
    except Exception:
        pass

    # Metric counts
    metric_counts = {"sds": 0, "hds": 0, "cis": 0, "crs": 0}
    score_dist = {"high": 0, "medium": 0, "low": 0}
    for d in discoveries:
        comps = d.get("components", {})
        if comps:
            dominant = max(comps, key=comps.get)
            if dominant in metric_counts:
                metric_counts[dominant] += 1
        s = d.get("composite_score", 0)
        if s > 0.4:
            score_dist["high"] += 1
        elif s > 0.2:
            score_dist["medium"] += 1
        else:
            score_dist["low"] += 1

    lines = []
    lines.append("=" * 56)
    lines.append("HARMONY_ENGINE_REPORT")
    lines.append("=" * 56)
    lines.append(f"TS:{now}")
    lines.append(f"DATASET: D={n_diseases} G={n_genes} S={n_symptoms}")
    lines.append(f"TOTAL_PREDICTIONS:{n_total}")
    lines.append(f"NOVEL_COUNT:{n_novel}")
    lines.append("WEIGHTS: SDS=0.30 HDS=0.25 CIS=0.30 CRS=0.15")
    lines.append("=" * 56)

    # DISEASE NODES
    lines.append("DISEASE_NODES:")
    for did, ddata in kb_module.DISEASES.items():
        name = ddata.get("name", did)
        cat = ddata.get("category", "")
        gc = len(ddata.get("genes", []))
        sc = len(ddata.get("symptoms", []))
        lines.append(f"{did}|{name}|{cat}|{gc}|{sc}")
    lines.append("=" * 56)

    # KNOWN EDGES (disease-disease)
    lines.append("EDGE_LIST (known connections):")
    if G:
        for u, v, edata in G.edges(data=True):
            n1 = G.nodes[u].get("type", "")
            n2 = G.nodes[v].get("type", "")
            if n1 == "disease" and n2 == "disease":
                w = edata.get("weight", 0.0)
                lines.append(f"{u}|{v}|{w:.4f}")
    lines.append("=" * 56)

    # DISCOVERIES
    lines.append("DISCOVERIES:")
    for i, d in enumerate(discoveries):
        e1 = d.get("entity1_name", d["entity1"])
        e2 = d.get("entity2_name", d["entity2"])
        did1 = d.get("entity1", "")
        did2 = d.get("entity2", "")
        score = d.get("composite_score", 0)
        papers = d.get("literature_evidence", -1)
        novel = "YES" if papers == 0 else "NO"
        comps = d.get("components", {})
        sds = comps.get("sds", 0)
        hds = comps.get("hds", 0)
        cis = comps.get("cis", 0)
        crs = comps.get("crs", 0)

        # Primary signal
        metric_names = {"sds": "SDS", "hds": "HDS", "cis": "CIS", "crs": "CRS"}
        primary = metric_names.get(max(comps, key=comps.get), "?") if comps else "?"

        # Gene/symptom overlap
        d1_data = kb_module.DISEASES.get(did1, {})
        d2_data = kb_module.DISEASES.get(did2, {})
        shared_genes = set(d1_data.get("genes", [])) & set(d2_data.get("genes", []))
        shared_symptoms = set(d1_data.get("symptoms", [])) & set(d2_data.get("symptoms", []))
        gene_names = [kb_module.GENES.get(g, g) for g in shared_genes]
        symptom_names = [kb_module.SYMPTOMS.get(s, s) for s in shared_symptoms][:5]
        gene_jaccard = len(shared_genes) / len(set(d1_data.get("genes", [])) | set(d2_data.get("genes", []))) if (set(d1_data.get("genes", [])) | set(d2_data.get("genes", []))) else 0.0

        # NetworkX metrics
        common_n = 0
        aa = 0.0
        ra = 0.0
        if G and G.has_node(did1) and G.has_node(did2):
            try:
                common_n = len(list(nx.common_neighbors(G, did1, did2)))
            except Exception:
                common_n = 0
            try:
                aa = next(nx.adamic_adar_index(G, [(did1, did2)]))[2]
            except Exception:
                aa = 0.0
            try:
                ra = next(nx.resource_allocation_index(G, [(did1, did2)]))[2]
            except Exception:
                ra = 0.0

        lines.append(f"RANK:{i+1}|SCORE:{score:.4f}|NOVEL:{novel}|PAPERS:{papers}")
        lines.append(f"D1:{e1}")
        lines.append(f"D2:{e2}")
        lines.append(f"SDS:{sds:.4f}|HDS:{hds:.4f}|CIS:{cis:.4f}|CRS:{crs:.4f}")
        lines.append(f"GENE_JACCARD:{gene_jaccard:.4f}|COMMON_N:{common_n}")
        lines.append(f"ADAMIC_ADAR:{aa:.4f}|RESOURCE_ALLOC:{ra:.4f}")
        lines.append(f"SHARED_GENES:{','.join(gene_names) if gene_names else 'NONE'}")
        lines.append(f"SHARED_SYMPTOMS:{','.join(symptom_names) if symptom_names else 'NONE'}")
        lines.append(f"PRIMARY_SIGNAL:{primary}")

        # Shortest path for NOVEL discoveries only
        if novel == "YES" and G and G.has_node(did1) and G.has_node(did2):
            try:
                path = nx.shortest_path(G, did1, did2)
                path_len = len(path) - 1
                path_names = []
                for p in path[:4]:
                    pname = G.nodes[p].get("name", p)
                    path_names.append(pname)
                lines.append(f"PATH_LENGTH:{path_len}|PATH:{' -> '.join(path_names)}")
            except Exception:
                lines.append("PATH_LENGTH:DISCONNECTED|PATH:NONE")

        lines.append("---")

    lines.append("=" * 56)

    # SCORE DISTRIBUTION
    lines.append("SCORE_DISTRIBUTION:")
    lines.append(f"HIGH(>0.4):{score_dist['high']}|MED(0.2-0.4):{score_dist['medium']}|LOW(<0.2):{score_dist['low']}")
    lines.append(f"SDS_PRIMARY:{metric_counts['sds']}|HDS_PRIMARY:{metric_counts['hds']}")
    lines.append(f"CIS_PRIMARY:{metric_counts['cis']}|CRS_PRIMARY:{metric_counts['crs']}")
    lines.append("=" * 56)

    # AI PROMPT
    lines.append("AI_PROMPT:")
    lines.append("You are a biomedical researcher. Below is a rare disease")
    lines.append("knowledge graph analysis using structural harmony mathematics")
    lines.append("(SDS=genetic/phenotypic symmetry break, HDS=spectral dissonance,")
    lines.append("CIS=incomplete network triangles, CRS=Ricci curvature defect,")
    lines.append("ADAMIC_ADAR and RESOURCE_ALLOC=link prediction confidence).")
    lines.append(f"Dataset: {n_diseases} diseases, {n_genes} genes, {n_symptoms} symptoms.")
    lines.append("Task: For each NOVEL discovery, assess biological plausibility,")
    lines.append("identify the most likely shared molecular mechanism,")
    lines.append("and suggest one specific testable experiment.")
    lines.append("Prioritize entries where GENE_JACCARD>0 and COMMON_N>0.")
    lines.append("=" * 56)

    report_text = "\n".join(lines)
    return Response(
        report_text,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=harmony_report.txt"},
    )


# ── Graph Endpoint with Lite Mode + Size Limit ────────────────────

@app.route("/api/graph")
def api_graph():
    """Graph data for visualization."""
    if not pipeline:
        return jsonify({"nodes": [], "edges": [], "predicted_edges": []})
    focus = request.args.get("focus", None)
    data = pipeline.graph_data_for_visualization(focus)

    # Lite mode: return only disease nodes + predicted edges
    if LITE_MODE:
        disease_nodes = [n for n in data.get("nodes", []) if n.get("type") == "disease"]
        predicted = data.get("predicted_edges", [])
        return jsonify({"nodes": disease_nodes, "edges": [], "predicted_edges": predicted, "lite": True})

    # Size limit: if too many nodes, simplify
    nodes = data.get("nodes", [])
    if len(nodes) > 400:
        # Keep only disease nodes and their direct connections
        disease_ids = {n["id"] for n in nodes if n.get("type") == "disease"}
        keep_ids = set(disease_ids)
        for e in data.get("edges", []):
            if e["source"] in disease_ids or e["target"] in disease_ids:
                keep_ids.add(e["source"])
                keep_ids.add(e["target"])
        data["nodes"] = [n for n in nodes if n["id"] in keep_ids]
        data["edges"] = [e for e in data.get("edges", [])
                         if e["source"] in keep_ids and e["target"] in keep_ids]
        data["limited"] = True
        data["message"] = "Showing simplified graph (too many nodes)"

    return jsonify(data)


# ── Lite Mode Toggle ───────────────────────────────────────────────

@app.route("/api/lite-mode", methods=["POST"])
def api_lite_mode():
    """Toggle lite mode for graph."""
    global LITE_MODE
    data = request.get_json()
    LITE_MODE = bool(data.get("enabled", False))
    return jsonify({"success": True, "lite_mode": LITE_MODE})


if __name__ == "__main__":
    # Clear session data on startup (uploaded CSV data does not survive restart)
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)
        print("  Session data cleared on startup")

    app.run(debug=False, port=5000)
