"""
Rare Disease Knowledge Base
===========================
Loads real rare disease data from the cache built by build_kb.py.

Data sources:
  - Orphanet (api.orphacode.org) — disease names, definitions, categories
  - Monarch Initiative (api.monarchinitiative.org) — symptoms, genes
  - Human Phenotype Ontology (HPO) — phenotype terms

First run: python build_kb.py    (fetches from APIs, takes 1-3 minutes)
Then run:  python app.py         (loads from cache instantly)

The interface is identical to the rest of the codebase:
  DISEASES, SYMPTOMS, GENES, PATHWAYS dictionaries
  get_entity_name(), get_entity_type(), etc.
"""

import json
import os

CACHE_FILE = os.path.join(os.path.dirname(__file__), "cache", "real_kb.json")


def _load_cache():
    """Load the cached knowledge base."""
    if not os.path.exists(CACHE_FILE):
        print(f"\n{'=' * 60}")
        print(f"  ERROR: Cache file not found!")
        print(f"  Run 'python build_kb.py' first to fetch real data.")
        print(f"  Expected: {CACHE_FILE}")
        print(f"{'=' * 60}\n")
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading cache: {e}")
        return None


def _init_globals():
    """Initialize global dictionaries from cache."""
    global DISEASES, SYMPTOMS, GENES, PATHWAYS
    global _DISEASE_NAME_MAP, _SYMPTOM_NAME_MAP, _GENE_NAME_MAP

    data = _load_cache()
    if data is None:
        # Empty fallback — app will show no data but won't crash
        DISEASES = {}
        SYMPTOMS = {}
        GENES = {}
        PATHWAYS = {}
        _DISEASE_NAME_MAP = {}
        _SYMPTOM_NAME_MAP = {}
        _GENE_NAME_MAP = {}
        return

    DISEASES = data.get("diseases", {})
    SYMPTOMS = data.get("symptoms", {})
    GENES = data.get("genes", {})
    PATHWAYS = data.get("pathways", {})

    # Build name lookup maps
    _DISEASE_NAME_MAP = {}
    for did, ddata in DISEASES.items():
        _DISEASE_NAME_MAP[did] = ddata.get("name", did)

    _SYMPTOM_NAME_MAP = {}
    for sid, sname in SYMPTOMS.items():
        _SYMPTOM_NAME_MAP[sid] = sname

    _GENE_NAME_MAP = {}
    for gid, gname in GENES.items():
        _GENE_NAME_MAP[gid] = gname

    # Print summary
    meta = data.get("meta", {})
    sources = meta.get("sources", [])
    fetched = meta.get("fetched_at", "unknown")

    print(f"  Knowledge base loaded from cache")
    print(f"  {len(DISEASES)} diseases, {len(SYMPTOMS)} symptoms, "
          f"{len(GENES)} genes, {len(PATHWAYS)} pathways")
    print(f"  Sources: {', '.join(sources)}")
    print(f"  Fetched: {fetched}")


# ── Lookup Maps ────────────────────────────────────────────────────────

_DISEASE_NAME_MAP = {}
_SYMPTOM_NAME_MAP = {}
_GENE_NAME_MAP = {}


# ── Public Interface ───────────────────────────────────────────────────

def get_entity_name(entity_id):
    """Get the display name for any entity (disease, symptom, gene, pathway)."""
    if entity_id in _DISEASE_NAME_MAP:
        return _DISEASE_NAME_MAP[entity_id]
    if entity_id in _SYMPTOM_NAME_MAP:
        return _SYMPTOM_NAME_MAP[entity_id]
    if entity_id in _GENE_NAME_MAP:
        return _GENE_NAME_MAP[entity_id]
    if entity_id in PATHWAYS:
        return PATHWAYS[entity_id]
    return entity_id


def get_entity_type(entity_id):
    """Get the type of an entity."""
    if entity_id in DISEASES:
        return "disease"
    if entity_id in SYMPTOMS:
        return "symptom"
    if entity_id in GENES:
        return "gene"
    if entity_id in PATHWAYS:
        return "pathway"
    return "unknown"


def get_categories():
    """Get all disease categories with counts."""
    cats = {}
    for ddata in DISEASES.values():
        cat = ddata.get("category", "Unknown")
        cats[cat] = cats.get(cat, 0) + 1
    return cats


def get_diseases_by_category(category):
    """Get all diseases in a category."""
    return {
        did: ddata for did, ddata in DISEASES.items()
        if ddata.get("category") == category
    }


# ── Initialize on import ──────────────────────────────────────────────

_init_globals()
