"""
Build Real Knowledge Base
=========================
Fetches real rare disease data from:
  - Orphanet API (https://api.orphacode.org) — disease definitions, ORPHA codes
  - Monarch Initiative API (https://api.monarchinitiative.org) — symptoms, genes

Saves to cache/real_kb.json for instant loading by rare_disease_kb.py.

Usage:
    python build_kb.py

The first run fetches from APIs (takes 1-3 minutes).
Subsequent runs load from cache instantly.
Delete cache/real_kb.json to re-fetch.
"""

import requests
import json
import os
import time
import sys

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "real_kb.json")

# Orphanet requires a header but accepts any non-empty string
ORPHANET_HEADERS = {"apiKey": "harmony-engine"}

MONARCH_BASE = "https://api.monarchinitiative.org/v3/api"
ORPHANET_BASE = "https://api.orphacode.org/EN"

# ── Curated seed list: VERIFIED Orphanet ORPHAcodes ──
# Each code was looked up via api.orphacode.org to confirm accuracy.
# The build script enriches each with real symptoms and genes from Monarch.
SEED_DISEASES = [
    # Lysosomal Storage
    "324",    # Fabry disease
    "355",    # Gaucher disease
    "845",    # Tay-Sachs disease
    "646",    # Niemann-Pick disease type C
    "93473",  # Hurler syndrome (MPS I)
    "79269",  # Sanfilippo syndrome type A (MPS III)
    "487",    # Krabbe disease
    "586",    # Cystic fibrosis

    # Connective Tissue
    "558",    # Marfan syndrome
    "284963", # Marfan syndrome type 1
    "60030",  # Loeys-Dietz syndrome
    "98249",  # Ehlers-Danlos syndrome
    "666",    # Osteogenesis imperfecta
    "90354",  # Brittle cornea syndrome
    "758",    # Pseudoxanthoma elasticum
    "828",    # Stickler syndrome
    "63",     # Alport syndrome
    "377",    # Gorlin syndrome

    # Channelopathies
    "768",    # Congenital long QT syndrome
    "130",    # Brugada syndrome
    "211062", # Hereditary episodic ataxia
    "65283",  # Timothy syndrome
    "37553",  # Andersen-Tawil syndrome

    # RASopathies / Signaling
    "648",    # Noonan syndrome
    "3071",   # Costello syndrome
    "636",    # Neurofibromatosis type 1
    "805",    # Tuberous sclerosis complex
    "778",    # Rett syndrome
    "50",     # Aicardi syndrome
    "739",    # Prader-Willi syndrome
    "72",     # Angelman syndrome
    "137605", # Legius syndrome
    "544254", # SYNGAP1-related encephalopathy

    # DNA Repair / Telomere
    "191",    # Cockayne syndrome
    "1775",   # Dyskeratosis congenita
    "902",    # Werner syndrome
    "100",    # Ataxia-telangiectasia
    "95",     # Friedreich ataxia

    # Iron / Heme / Porphyria
    "738",    # Porphyria
    "446",    # Neonatal hemochromatosis

    # Metabolic
    "716",    # Phenylketonuria (PKU)
    "511",    # Maple syrup urine disease
    "510",    # Lesch-Nyhan syndrome
    "550",    # MELAS syndrome
    "506",    # Leigh syndrome
    "480",    # Kearns-Sayre syndrome
    "551",    # MERRF syndrome
    "905",    # Wilson disease

    # Peroxisomal
    "912",    # Zellweger syndrome
    "773",    # Refsum disease
    "44",     # Neonatal adrenoleukodystrophy

    # Complement / Coagulation
    "2134",   # Atypical hemolytic uremic syndrome
    "447",    # Paroxysmal nocturnal hemoglobinuria
    "91378",  # Hereditary angioedema
    "448",    # Hemophilia
    "903",    # Von Willebrand disease

    # Hematological
    "232",    # Sickle cell anemia
    "848",    # Beta-thalassemia

    # Skin
    "304",    # Epidermolysis bullosa simplex
    "910",    # Xeroderma pigmentosum
    "218",    # Darier disease

    # Tumor Suppression
    "524",    # Li-Fraumeni syndrome
    "790",    # Retinoblastoma
    "892",    # Von Hippel-Lindau disease
    "652",    # Multiple endocrine neoplasia type 1
    "653",    # Multiple endocrine neoplasia type 2
    "201",    # Cowden syndrome
    "2869",   # Peutz-Jeghers syndrome
    "227535", # Hereditary breast cancer

    # Neuromuscular
    "98896",  # Duchenne muscular dystrophy
    "206647", # Myotonic dystrophy
    "70",     # Proximal spinal muscular atrophy
    "101081", # Charcot-Marie-Tooth disease type 1A
    "589",    # Myasthenia gravis

    # Autoimmune / Inflammatory
    "90291",  # Systemic sclerosis
    "117",    # Behcet disease

    # Cardiac
    "293899", # Arrhythmogenic ventricular dysplasia
    "217569", # Hypertrophic cardiomyopathy

    # Pulmonary
    "182090", # Pulmonary arterial hypertension

    # Mitochondrial / Other
    "141",    # Canavan disease
    "58",     # Alexander disease
    "565",    # Menkes disease
    "111",    # Barth syndrome
    "699",    # Pearson syndrome
    "3205",   # Sturge-Weber syndrome
    "774",    # Hereditary hemorrhagic telangiectasia
]

# Deduplicate
SEED_DISEASES = list(dict.fromkeys(SEED_DISEASES))

# Category mapping: ORPHAcode prefix ranges → categories
# (approximate; real categories come from Orphanet PreferentialParent)
CATEGORY_MAP = {
    "Rare systemic or rheumatologic disease": "Connective Tissue",
    "Rare neurological disease": "Neurological",
    "Rare cardiac disease": "Cardiac",
    "Rare inborn error of metabolism": "Metabolic",
    "Rare hepatic disease": "Hepatic",
    "Rare renal disease": "Renal",
    "Rare skin disease": "Skin",
    "Rare hematological disease": "Hematological",
    "Rare endocrine disease": "Endocrine",
    "Rare immunological disease": "Immunological",
    "Rare neoplastic disease": "Oncological",
    "Rare developmental anomaly during embryogenesis": "Developmental",
    "Rare gastroenterological disease": "Gastroenterological",
    "Rare respiratory disease": "Respiratory",
    "Rare eye disease": "Ophthalmological",
    "Rare surgical thoracic disease": "Thoracic",
    "Rare circulatory system disease": "Cardiac",
    "Rare bone disease": "Bone",
    "Rare genetic disease": "Genetic",
}


def fetch_orphanet(url, retries=3):
    """Fetch from Orphanet API with retries."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=ORPHANET_HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            else:
                print(f"  Orphanet {resp.status_code}: {url}")
                return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                print(f"  Orphanet error: {e}")
                return None
    return None


def fetch_monarch(endpoint, params=None, retries=3, quiet=False):
    """Fetch from Monarch Initiative API with retries."""
    url = f"{MONARCH_BASE}{endpoint}"
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            else:
                if not quiet:
                    print(f"  Monarch {resp.status_code}: {endpoint}")
                return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                if not quiet:
                    print(f"  Monarch error: {e}")
                return None
    return None


def get_orphanet_omim(orpha_code):
    """Get OMIM codes for an Orphanet disease."""
    data = fetch_orphanet(
        f"{ORPHANET_BASE}/ClinicalEntity/orphacode/{orpha_code}/OMIM"
    )
    if not data or "References" not in data:
        return []
    omim_codes = []
    for ref in data["References"]:
        code = ref.get("Code OMIM")
        if code:
            omim_codes.append(str(code))
    return omim_codes


def get_orphanet_category(orpha_code):
    """Get the preferential parent category for a disease."""
    data = fetch_orphanet(
        f"{ORPHANET_BASE}/ClinicalEntity/orphacode/{orpha_code}/PreferentialParent"
    )
    if not data:
        return "Rare disease"
    parent = data.get("Preferential parent", {})
    return parent.get("Preferred term", "Rare disease")


def search_monarch(query, category="biolink:Disease"):
    """Search Monarch for a disease by name."""
    data = fetch_monarch("/search", params={
        "q": query,
        "category": category,
        "limit": 3,
    })
    if not data or not data.get("items"):
        return None
    return data["items"][0]


def get_monarch_entity(entity_id, quiet=False):
    """Get a Monarch entity by ID."""
    return fetch_monarch(f"/entity/{entity_id}", quiet=quiet)


def get_monarch_associations(subject_id, predicate_or_category, rows=100, use_object=False):
    """Get associations from Monarch."""
    if use_object:
        params = {"object": subject_id, "category": predicate_or_category, "rows": rows}
    else:
        params = {"subject": subject_id, "predicate": predicate_or_category, "rows": rows}
    data = fetch_monarch("/association", params=params)
    if not data:
        return []
    return data.get("items", [])


def build_disease(orpha_code, orphanet_data):
    """Build a complete disease record from APIs."""
    name = orphanet_data.get("Preferred term", f"Disease {orpha_code}")
    definition = orphanet_data.get("Definition", "")

    # Get Orphanet category
    raw_category = get_orphanet_category(orpha_code)
    category = CATEGORY_MAP.get(raw_category, "Rare disease")

    # Get OMIM codes for cross-referencing
    omim_codes = get_orphanet_omim(orpha_code)

    # Search Monarch for the disease (name search first — most reliable)
    monarch_id = None
    monarch_entity = None

    # Name-based search (gets MONDO ID directly)
    result = search_monarch(name)
    if result:
        monarch_id = result["id"]
        monarch_entity = get_monarch_entity(monarch_id)

    # Fall back to OMIM-based lookup if name search failed
    if not monarch_entity:
        for omim in omim_codes[:2]:
            monarch_entity = get_monarch_entity(f"OMIM:{omim}", quiet=True)
            if monarch_entity and monarch_entity.get("has_phenotype"):
                monarch_id = f"OMIM:{omim}"
                break
            monarch_entity = None

    # Extract symptoms (phenotypes) and genes
    symptoms = []
    genes = []

    if monarch_entity:
        # Symptoms from has_phenotype fields
        hp_ids = monarch_entity.get("has_phenotype") or []
        hp_names = monarch_entity.get("has_phenotype_label") or []
        for i, hp_id in enumerate(hp_ids[:30]):  # Limit to top 30
            hp_name = hp_names[i] if i < len(hp_names) else hp_id
            symptoms.append({
                "id": hp_id,
                "name": hp_name,
            })

        # Genes from causal_gene field
        seen_genes = set()
        causal_genes = monarch_entity.get("causal_gene") or []
        for gene in causal_genes[:10]:
            gene_id = gene.get("id", "")
            gene_name = gene.get("name", "")
            if gene_id and gene_name and gene_id not in seen_genes:
                seen_genes.add(gene_id)
                genes.append({
                    "id": gene_id.replace("HGNC:", "HGNC_"),
                    "name": gene_name,
                    "hgnc": gene_id,
                })

    # Fetch additional gene associations (causal + correlated)
    if monarch_id:
        for category in [
            "biolink:CausalGeneToDiseaseAssociation",
            "biolink:CorrelatedGeneToDiseaseAssociation",
        ]:
            gene_assocs = get_monarch_associations(
                monarch_id, category, rows=20, use_object=True
            )
            for assoc in gene_assocs[:15]:
                gene_id = assoc.get("subject", "")
                gene_name = assoc.get("subject_label", "")
                if gene_id and gene_name and gene_id not in seen_genes:
                    seen_genes.add(gene_id)
                    genes.append({
                        "id": gene_id.replace("HGNC:", "HGNC_"),
                        "name": gene_name,
                    })

    return {
        "name": name,
        "orpha_code": orpha_code,
        "monarch_id": monarch_id or "",
        "omim_codes": omim_codes,
        "category": category,
        "definition": definition,
        "symptoms": symptoms,
        "genes": genes,
        "pathways": [],  # Derived later from gene data
    }


def load_cache():
    """Load cached data if it exists."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_cache(data):
    """Save data to cache."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {CACHE_FILE}")


def build(force=False):
    """Build the knowledge base from APIs."""
    if not force:
        cached = load_cache()
        if cached:
            n = len(cached.get("diseases", {}))
            print(f"Using cached knowledge base ({n} diseases). "
                  f"Delete {CACHE_FILE} to re-fetch.")
            return cached

    print("=" * 60)
    print("  Building Real Knowledge Base")
    print("  Sources: Orphanet + Monarch Initiative")
    print("=" * 60)

    # Step 1: Fetch Orphanet disease data
    print(f"\nFetching {len(SEED_DISEASES)} diseases from Orphanet...")
    orphanet_cache = {}
    for i, orpha_code in enumerate(SEED_DISEASES):
        data = fetch_orphanet(
            f"{ORPHANET_BASE}/ClinicalEntity/orphacode/{orpha_code}"
        )
        if data:
            orphanet_cache[orpha_code] = data
            name = data.get("Preferred term", orpha_code)
            print(f"  [{i+1}/{len(SEED_DISEASES)}] {name}")
        else:
            print(f"  [{i+1}/{len(SEED_DISEASES)}] ORPHA:{orpha_code} — not found")
        time.sleep(0.2)  # Be polite

    print(f"\nFound {len(orphanet_cache)} diseases on Orphanet.")

    # Step 2: Enrich with Monarch data (symptoms + genes)
    print(f"\nEnriching with Monarch Initiative data...")
    diseases = {}
    all_symptoms = {}
    all_genes = {}
    all_pathways = {}
    pathway_counter = 1

    for i, (orpha_code, orphanet_data) in enumerate(orphanet_cache.items()):
        name = orphanet_data.get("Preferred term", orpha_code)
        print(f"  [{i+1}/{len(orphanet_cache)}] {name}...", end=" ", flush=True)

        disease = build_disease(orpha_code, orphanet_data)
        disease_id = f"D{i+1:02d}"

        # Assign symptom IDs and collect unique symptoms
        symptom_ids = []
        for s in disease["symptoms"]:
            hp_id = s["id"]
            if hp_id not in all_symptoms:
                all_symptoms[hp_id] = s["name"]
            symptom_ids.append(hp_id)

        # Assign gene IDs and collect unique genes
        gene_ids = []
        for g in disease["genes"]:
            gene_key = g["id"]
            if gene_key not in all_genes:
                all_genes[gene_key] = g["name"]
            gene_ids.append(gene_key)

        # Derive pathways from genes (group by gene function)
        pathway_ids = derive_pathways(gene_ids, all_genes, all_pathways, pathway_counter)
        pathway_counter = len(all_pathways) + 1

        diseases[disease_id] = {
            "name": disease["name"],
            "orpha_code": orpha_code,
            "monarch_id": disease["monarch_id"],
            "omim_codes": disease["omim_codes"],
            "category": disease["category"],
            "definition": disease["definition"],
            "symptoms": symptom_ids,
            "genes": gene_ids,
            "pathways": pathway_ids,
        }

        print(f"{len(symptom_ids)} symptoms, {len(gene_ids)} genes")
        time.sleep(0.3)  # Be polite to Monarch

    # Step 3: Normalize symptom names (HPO terms → plain language)
    symptoms_normalized = {}
    for hp_id, name in all_symptoms.items():
        symptoms_normalized[hp_id] = simplify_term_name(name)

    # Step 4: Save
    result = {
        "diseases": diseases,
        "symptoms": symptoms_normalized,
        "genes": all_genes,
        "pathways": all_pathways,
        "meta": {
            "sources": [
                "Orphanet (api.orphacode.org)",
                "Monarch Initiative (api.monarchinitiative.org)",
                "Human Phenotype Ontology (HPO)",
            ],
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "n_diseases": len(diseases),
            "n_symptoms": len(symptoms_normalized),
            "n_genes": len(all_genes),
            "n_pathways": len(all_pathways),
        },
    }

    save_cache(result)

    print(f"\n{'=' * 60}")
    print(f"  Knowledge Base Built Successfully")
    print(f"  {len(diseases)} diseases, {len(symptoms_normalized)} symptoms, "
          f"{len(all_genes)} genes, {len(all_pathways)} pathways")
    print(f"{'=' * 60}")

    return result


def derive_pathways(gene_ids, all_genes, all_pathways, start_idx):
    """
    Derive biological pathways from gene sets.
    Groups genes by known functional categories.
    """
    if not gene_ids:
        return []

    # Known gene → pathway mappings (curated from real biology)
    GENE_PATHWAY_MAP = {
        # Lysosomal
        "GLA": "Lysosomal degradation", "GBA": "Lysosomal degradation",
        "HEXA": "Lysosomal degradation", "HEXB": "Lysosomal degradation",
        "GALC": "Lysosomal degradation", "ARSA": "Lysosomal degradation",
        "IDUA": "Lysosomal degradation", "IDS": "Lysosomal degradation",
        "GUSB": "Lysosomal degradation", "SGSH": "Lysosomal degradation",
        "NAGLU": "Lysosomal degradation", "HGSNAT": "Lysosomal degradation",
        "GNS": "Lysosomal degradation", "GALNS": "Lysosomal degradation",
        "GAA": "Lysosomal degradation", "NPC1": "Lysosomal degradation",
        "NPC2": "Lysosomal degradation", "SMPD1": "Lysosomal degradation",
        "ASAH1": "Lysosomal degradation",

        # Connective tissue / ECM
        "FBN1": "Extracellular matrix remodeling",
        "COL1A1": "Collagen biosynthesis", "COL1A2": "Collagen biosynthesis",
        "COL3A1": "Collagen biosynthesis", "COL4A3": "Collagen biosynthesis",
        "COL4A4": "Collagen biosynthesis", "COL4A5": "Collagen biosynthesis",
        "COL5A1": "Collagen biosynthesis", "COL5A2": "Collagen biosynthesis",
        "COL11A1": "Collagen biosynthesis", "COL11A2": "Collagen biosynthesis",
        "TGFBR1": "TGF-beta signaling", "TGFBR2": "TGF-beta signaling",
        "SMAD3": "TGF-beta signaling", "TGFB2": "TGF-beta signaling",
        "BGN": "Extracellular matrix remodeling",
        "ADAMTS2": "Extracellular matrix remodeling",
        "PLOD1": "Collagen biosynthesis",
        "TNXB": "Extracellular matrix remodeling",
        "ABCC6": "Calcium signaling",
        "SLC26A2": "Ion channel regulation",

        # Ion channels
        "KCNQ1": "Ion channel regulation",
        "KCNH2": "Ion channel regulation",
        "SCN5A": "Ion channel regulation",
        "KCNA1": "Ion channel regulation",
        "KCND3": "Ion channel regulation",
        "CACNA1A": "Ion channel regulation",
        "CACNA1S": "Ion channel regulation",
        "KCNJ2": "Ion channel regulation",
        "KCNJ11": "Ion channel regulation",
        "CACNA1E": "Ion channel regulation",

        # RAS / signaling
        "PTPN11": "RAS-MAPK signaling",
        "SOS1": "RAS-MAPK signaling",
        "RAF1": "RAS-MAPK signaling",
        "HRAS": "RAS-MAPK signaling",
        "BRAF": "RAS-MAPK signaling",
        "MAP2K1": "RAS-MAPK signaling",
        "MAP2K2": "RAS-MAPK signaling",
        "KRAS": "RAS-MAPK signaling",
        "NF1": "RAS-MAPK signaling",
        "SPRED1": "RAS-MAPK signaling",
        "TSC1": "mTOR signaling", "TSC2": "mTOR signaling",
        "MECP2": "Neurotransmitter metabolism",
        "SYNGAP1": "Neurotransmitter metabolism",
        "UBE3A": "Neurotransmitter metabolism",
        "MAGEL2": "Neurotransmitter metabolism",
        "SNRPN": "Neurotransmitter metabolism",

        # DNA repair
        "ERCC6": "DNA damage repair", "ERCC8": "DNA damage repair",
        "DKC1": "Telomere maintenance", "TERT": "Telomere maintenance",
        "WRN": "DNA damage repair",

        # Iron / Heme
        "HMBS": "Heme biosynthesis", "ALAS2": "Heme biosynthesis",
        "FECH": "Heme biosynthesis", "UROS": "Heme biosynthesis",
        "HFE": "Iron metabolism", "SLC40A1": "Iron metabolism",
        "PKLR": "Glycogen metabolism",

        # Metabolic
        "PAH": "Neurotransmitter metabolism",
        "BCKDHA": "Neurotransmitter metabolism",
        "BCKDHB": "Neurotransmitter metabolism",
        "HPRT1": "Neurotransmitter metabolism",
        "CBS": "Neurotransmitter metabolism",
        "MT-TL1": "Mitochondrial electron transport",
        "MT-ND5": "Mitochondrial electron transport",
        "SURF1": "Mitochondrial electron transport",
        "COX8A": "Mitochondrial electron transport",

        # Peroxisomal
        "PEX1": "Peroxisomal function", "PEX6": "Peroxisomal function",
        "PEX26": "Peroxisomal function",
        "ABCD1": "Fatty acid oxidation",
        "PHYH": "Fatty acid oxidation",

        # Tumor suppression
        "TP53": "DNA damage repair",
        "RB1": "DNA damage repair",
        "VHL": "mTOR signaling",
        "MEN1": "mTOR signaling",
        "RET": "RAS-MAPK signaling",
        "PTEN": "PI3K-AKT signaling",
        "STK11": "mTOR signaling",
        "CDH1": "Extracellular matrix remodeling",
        "BRCA1": "DNA damage repair",
        "BRCA2": "DNA damage repair",
        "PTCH1": "Hedgehog signaling",

        # Muscular
        "DMD": "Extracellular matrix remodeling",
        "DMPK": "Neurotransmitter metabolism",
        "SMN1": "Neurotransmitter metabolism",
        "PMP22": "Myelination",
        "MPZ": "Myelination",

        # Complement / Coagulation
        "CFH": "Complement cascade",
        "CFI": "Complement cascade",
        "CD46": "Complement cascade",
        "ADAMTS13": "Coagulation cascade",
        "PIGA": "Complement cascade",
        "SERPING1": "Coagulation cascade",

        # Skin
        "KRT5": "Keratinocyte differentiation",
        "KRT14": "Keratinocyte differentiation",
        "DSC3": "Keratinocyte differentiation",
        "ATP2A2": "Calcium signaling",
        "XPA": "DNA damage repair",
        "XPC": "DNA damage repair",

        # Cardiac
        "PKP2": "Extracellular matrix remodeling",
        "DSP": "Extracellular matrix remodeling",
        "DSG2": "Extracellular matrix remodeling",
        "DSC2": "Extracellular matrix remodeling",
        "MYH7": "Calcium signaling",
        "MYBPC3": "Calcium signaling",
        "TTN": "Extracellular matrix remodeling",

        # Pulmonary
        "BMPR2": "TGF-beta signaling",
        "CFTR": "Ion channel regulation",
        "SMAD9": "TGF-beta signaling",
        "KCNK3": "Ion channel regulation",

        # Immune / Autoimmune (no single gene for most)
        "NLRP3": "NF-kB signaling",
        "MVK": "NF-kB signaling",
    }

    pathway_ids = []
    for gene_id in gene_ids:
        gene_symbol = all_genes.get(gene_id, "")
        pathway_name = GENE_PATHWAY_MAP.get(gene_symbol)
        if pathway_name:
            # Find or create pathway ID
            pid = None
            for existing_pid, existing_name in all_pathways.items():
                if existing_name == pathway_name:
                    pid = existing_pid
                    break
            if not pid:
                pid = f"P{len(all_pathways) + 1:02d}"
                all_pathways[pid] = pathway_name
            if pid not in pathway_ids:
                pathway_ids.append(pid)

    return pathway_ids


def simplify_term_name(hpo_name):
    """
    Simplify HPO term names to plain language.
    Removes medical jargon and makes terms understandable.
    """
    # Common HPO → plain language replacements
    REPLACEMENTS = {
        "Abnormality of the ": "",
        "Abnormality of ": "",
        "Abnormal ": "",
        "Increased ": "High ",
        "Decreased ": "Low ",
        "Recurrent ": "Repeated ",
        "Chronic ": "Long-lasting ",
        "Acute ": "Sudden ",
        "Congenital ": "Born with ",
        "Progressive ": "Gets worse over time ",
        "Intermittent ": "Comes and goes ",
        "Bilateral ": "Both sides ",
        "Unilateral ": "One side ",
        "Generalized ": "Widespread ",
        "Focal ": "Localized ",
        "Peripheral ": "Outer ",
        "Central ": "Inner ",
        "Myalgia": "Muscle pain",
        "Arthralgia": "Joint pain",
        "Arthrogryposis": "Stiff joints",
        "Dyspnea": "Trouble breathing",
        "Tachycardia": "Fast heartbeat",
        "Bradycardia": "Slow heartbeat",
        "Cardiomyopathy": "Heart muscle disease",
        "Hepatomegaly": "Enlarged liver",
        "Splenomegaly": "Enlarged spleen",
        "Lymphadenopathy": "Swollen glands",
        "Pancytopenia": "Low blood cell counts",
        "Thrombocytopenia": "Low platelets",
        "Leukopenia": "Low white blood cells",
        "Anemia": "Low red blood cells",
        "Hyperreflexia": "Overactive reflexes",
        "Hyporeflexia": "Weak reflexes",
        "Nystagmus": "Jerky eye movements",
        "Strabismus": "Crossed eyes",
        "Ptosis": "Droopy eyelid",
        "Macroglossia": "Large tongue",
        "Microcephaly": "Small head",
        "Macrocephaly": "Large head",
        "Dolichocephaly": "Long narrow head",
        "Brachydactyly": "Short fingers",
        "Syndactyly": "Fused fingers or toes",
        "Polydactyly": "Extra fingers or toes",
        "Clinodactyly": "Curved finger",
        "Camptodactyly": "Bent finger",
        "Pectus excavatum": "Sunken chest",
        "Pectus carinatum": "Pigeon chest",
        "Kyphosis": "Rounded upper back",
        "Lordosis": "Swayed back",
        "Scoliosis": "Curved spine",
        "Ataxia": "Poor coordination",
        "Dysarthria": "Slurred speech",
        "Dysphagia": "Trouble swallowing",
        "Feeding difficulty": "Trouble eating",
        "Failure to thrive": "Poor growth in babies",
        "Growth delay": "Slow growth",
        "Short stature": "Short height",
        "Tall stature": "Tall height",
        "Obesity": "Overweight",
        "Cachexia": "Extreme weight loss",
        "Alopecia": "Hair loss",
        "Hyperkeratosis": "Thick skin",
        "Ichthyosis": "Dry scaly skin",
        "Erythema": "Red skin",
        "Pruritus": "Itching",
        "Jaundice": "Yellow skin",
        "Cyanosis": "Blue skin",
        "Pallor": "Pale skin",
        "Edema": "Swelling",
        "Ascites": "Fluid in belly",
        "Pleural effusion": "Fluid around lungs",
        "Seizure": "Seizures",
        "Epilepsy": "Seizures",
        "Encephalopathy": "Brain disease",
        "Leukodystrophy": "White brain matter disease",
        "Leukoencephalopathy": "White brain disease",
        "Polyneuropathy": "Nerve damage",
        "Neuropathy": "Nerve damage",
        "Myopathy": "Muscle disease",
        "Dystonia": "Involuntary muscle contractions",
        "Chorea": "Involuntary movements",
        "Myoclonus": "Muscle jerks",
        "Spasticity": "Stiff muscles",
        "Hypotonia": "Weak muscles (floppy)",
        "Hypertonia": "Tight muscles",
        "Paresthesia": "Tingling or numbness",
        "Hypesthesia": "Reduced feeling",
        "Hyperesthesia": "Extreme sensitivity",
        "Photophobia": "Light sensitivity",
        "Phonophobia": "Sound sensitivity",
        "Cataract": "Cloudy eye lens",
        "Glaucoma": "High eye pressure",
        "Retinopathy": "Eye retina disease",
        "Optic atrophy": "Damaged eye nerve",
        "Corneal opacity": "Cloudy cornea",
        "Lenticiconus": "Cone-shaped lens",
        "Hearing loss": "Hearing loss",
        "Deafness": "Deafness",
        "Tinnitus": "Ringing in ears",
        "Vertigo": "Dizziness",
        "Syncope": "Fainting",
        "Apnea": "Stopped breathing",
        "Wheezing": "Noisy breathing",
        "Stridor": "Noisy breathing",
        "Cough": "Coughing",
        "Hemoptysis": "Coughing up blood",
        "Diarrhea": "Diarrhea",
        "Constipation": "Constipation",
        "Vomiting": "Vomiting",
        "Nausea": "Feeling sick to stomach",
        "Abdominal pain": "Belly pain",
        "Hematuria": "Blood in urine",
        "Proteinuria": "Protein in urine",
        "Polyuria": "Frequent urination",
        "Polydipsia": "Extreme thirst",
        "Polyphagia": "Extreme hunger",
    }

    name = hpo_name
    for old, new in REPLACEMENTS.items():
        name = name.replace(old, new)

    # Clean up extra spaces
    name = " ".join(name.split())
    return name


if __name__ == "__main__":
    force = "--force" in sys.argv or "-f" in sys.argv
    build(force=force)
