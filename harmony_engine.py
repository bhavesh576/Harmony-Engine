"""
The Harmony Engine
==================
Measures structural beauty — and its absence — in a knowledge graph.

Four metrics capture different kinds of "ugliness":

1. Symmetry Defect Score (SDS)
   Where cross-dimensional similarity breaks down.
   If two diseases are genetically similar, they should be phenotypically
   similar. The deviation = undiscovered knowledge.

2. Harmonic Dissonance Score (HDS)
   Where the graph's natural harmonics predict connections that don't exist.
   Uses spectral analysis of the graph Laplacian.

3. Compositional Incompleteness Score (CIS)
   Where triangles should close but don't.
   If A-B and B-C exist, A-C should complete the pattern.

4. Curvature Defect Score (CRS)
   Where the network geometry is "wrong" — negative Ollivier-Ricci
   curvature indicates bridges that should exist.

Each metric returns both per-node scores and per-non-edge prediction
strengths. The composite Discovery Score ranks all gaps.
"""

import numpy as np
from scipy.spatial.distance import cosine as cosine_dist
from scipy.linalg import eigh
from collections import defaultdict
import networkx as nx

from knowledge_graph import KnowledgeGraph
from rare_disease_kb import get_entity_name, get_entity_type


class HarmonyEngine:
    """Measures structural harmony and surfaces its violations."""

    def __init__(self, kg: KnowledgeGraph):
        self.kg = kg
        self.G = kg.G
        self._cache = {}

    # ═══════════════════════════════════════════════════════════════════
    # METRIC 1: Symmetry Defect Score (SDS)
    # ═══════════════════════════════════════════════════════════════════

    def symmetry_defect(self):
        """
        Measures where cross-dimensional similarity breaks down.

        For each pair of diseases, compare:
        - Genetic similarity (shared genes)
        - Phenotypic similarity (shared symptoms)

        High defect = the two dimensions disagree = undiscovered connection.
        """
        diseases = self.kg.nodes_by_type("disease")
        n = len(diseases)

        # Build similarity matrices
        d_symptoms = {}
        d_genes = {}
        for d in diseases:
            neighbors = set(self.G.neighbors(d))
            d_symptoms[d] = {s for s in neighbors
                            if self.G.nodes[s].get("type") == "symptom"}
            d_genes[d] = {g for g in neighbors
                          if self.G.nodes[g].get("type") == "gene"}

        # Compute pairwise symmetry defects
        defects = {}
        for i, d1 in enumerate(diseases):
            for d2 in diseases[i+1:]:
                # Gene similarity
                g1, g2 = d_genes[d1], d_genes[d2]
                gene_sim = (len(g1 & g2) / len(g1 | g2)
                            if g1 | g2 else 0)

                # Symptom similarity
                s1, s2 = d_symptoms[d1], d_symptoms[d2]
                symptom_sim = (len(s1 & s2) / len(s1 | s2)
                               if s1 | s2 else 0)

                # The defect: how much do the two dimensions disagree?
                defect = abs(gene_sim - symptom_sim)

                # Direction matters: which way is the gap?
                # gene_sim > symptom_sim → missing phenotypic links
                # symptom_sim > gene_sim → missing genetic links
                direction = "missing_phenotype" if gene_sim > symptom_sim \
                    else "missing_genetics" if symptom_sim > gene_sim \
                    else "balanced"

                if defect > 0.05:  # Only store meaningful defects
                    defects[(d1, d2)] = {
                        "score": defect,
                        "gene_similarity": gene_sim,
                        "symptom_similarity": symptom_sim,
                        "direction": direction,
                    }

        return defects

    # ═══════════════════════════════════════════════════════════════════
    # METRIC 2: Harmonic Dissonance Score (HDS)
    # ═══════════════════════════════════════════════════════════════════

    def harmonic_dissonance(self, k_eigenvectors=20):
        """
        Uses spectral graph theory to find where the graph's natural
        harmonics predict connections that don't exist.

        The graph Laplacian's eigenvectors are the "natural modes" of
        the knowledge structure. Each node's position in harmonic space
        predicts what it should connect to. Deviations = dissonance.
        """
        # Work with the disease subgraph for tractability
        diseases = self.kg.nodes_by_type("disease")
        nodes, adj = self.kg.adjacency_matrix("disease")
        n = len(nodes)

        if n < 3:
            return {}, {}

        # Compute normalized graph Laplacian
        degree = np.diag(adj.sum(axis=1))
        # Avoid division by zero
        deg_inv_sqrt = np.zeros(n)
        mask = degree.diagonal() > 0
        deg_inv_sqrt[mask] = 1.0 / np.sqrt(degree.diagonal()[mask])
        D_inv_sqrt = np.diag(deg_inv_sqrt)

        L_norm = np.eye(n) - D_inv_sqrt @ adj @ D_inv_sqrt

        # Compute eigenvectors (the harmonics)
        k = min(k_eigenvectors, n - 2)
        try:
            eigenvalues, eigenvectors = eigh(L_norm, subset_by_index=[1, k+1])
        except Exception:
            return {}, {}

        # Each node's harmonic signature
        signatures = {}
        for i, node in enumerate(nodes):
            signatures[node] = eigenvectors[i, :]

        # For each non-edge, compute predicted connection strength
        # from harmonic signature similarity
        node_idx = {node: i for i, node in enumerate(nodes)}
        dissonance_scores = {}
        predicted_edges = {}

        for i, u in enumerate(nodes):
            for v in nodes[i+1:]:
                if not self.G.has_edge(u, v):
                    # Predicted connection: cosine similarity in harmonic space
                    sig_u = signatures[u]
                    sig_v = signatures[v]

                    norm_u = np.linalg.norm(sig_u)
                    norm_v = np.linalg.norm(sig_v)
                    if norm_u > 0 and norm_v > 0:
                        predicted = np.dot(sig_u, sig_v) / (norm_u * norm_v)
                    else:
                        predicted = 0

                    if predicted > 0.1:  # Only meaningful predictions
                        predicted_edges[(u, v)] = {
                            "score": float(predicted),
                            "harmonic_strength": float(predicted),
                        }

        # Per-node dissonance: average deviation from harmonic predictions
        node_dissonance = {}
        for node in nodes:
            neighbors_actual = set(self.G.neighbors(node)) & set(diseases)
            predicted_neighbors = []
            for other in nodes:
                if other != node and not self.G.has_edge(node, other):
                    sig_n = signatures[node]
                    sig_o = signatures[other]
                    norm_n = np.linalg.norm(sig_n)
                    norm_o = np.linalg.norm(sig_o)
                    if norm_n > 0 and norm_o > 0:
                        pred = np.dot(sig_n, sig_o) / (norm_n * norm_o)
                        if pred > 0.3:
                            predicted_neighbors.append((other, pred))

            if predicted_neighbors:
                avg_pred = np.mean([p for _, p in predicted_neighbors])
                node_dissonance[node] = {
                    "score": float(avg_pred),
                    "n_predicted_missing": len(predicted_neighbors),
                    "top_predictions": sorted(predicted_neighbors,
                                              key=lambda x: -x[1])[:5],
                }

        return predicted_edges, node_dissonance

    # ═══════════════════════════════════════════════════════════════════
    # METRIC 3: Compositional Incompleteness Score (CIS)
    # ═══════════════════════════════════════════════════════════════════

    def compositional_incompleteness(self):
        """
        Finds where triangles should close but don't.

        If A-B and B-C exist, the pattern predicts A-C.
        Non-edges with many common neighbors are the strongest
        predictions of missing knowledge.
        """
        diseases = self.kg.nodes_by_type("disease")
        disease_set = set(diseases)

        predictions = {}
        node_cis = defaultdict(list)

        for i, u in enumerate(diseases):
            u_neighbors = set(self.G.neighbors(u)) & disease_set
            for v in diseases[i+1:]:
                if self.G.has_edge(u, v):
                    continue
                v_neighbors = set(self.G.neighbors(v)) & disease_set
                common = u_neighbors & v_neighbors

                if len(common) >= 1:
                    # Jaccard-like prediction strength
                    union = u_neighbors | v_neighbors
                    score = len(common) / np.sqrt(len(u_neighbors) * len(v_neighbors)) \
                        if len(u_neighbors) > 0 and len(v_neighbors) > 0 else 0

                    if score > 0.05:
                        predictions[(u, v)] = {
                            "score": float(score),
                            "common_neighbors": len(common),
                            "neighbors": [get_entity_name(n) for n in sorted(common)],
                            "bridge_diseases": sorted(common),
                        }
                        node_cis[u].append((v, score))
                        node_cis[v].append((u, score))

        # Per-node CIS: average prediction strength
        node_scores = {}
        for node, preds in node_cis.items():
            if preds:
                scores = [s for _, s in preds]
                node_scores[node] = {
                    "score": float(np.mean(scores)),
                    "n_missing": len(preds),
                    "top_predictions": sorted(preds, key=lambda x: -x[1])[:5],
                }

        return predictions, node_scores

    # ═══════════════════════════════════════════════════════════════════
    # METRIC 4: Curvature Defect Score (CRS)
    # ═══════════════════════════════════════════════════════════════════

    def curvature_defect(self):
        """
        Computes approximate Ollivier-Ricci curvature on the disease
        similarity graph.

        Negative curvature = "bridge-like" edges where the two endpoints
        are structurally farther apart than their neighborhoods suggest.
        These are locations where the geometry of knowledge is "wrong."
        """
        diseases = self.kg.nodes_by_type("disease")
        disease_set = set(diseases)

        # Compute curvature for each existing edge
        edge_curvature = {}
        for u, v in self.G.edges():
            if u not in disease_set or v not in disease_set:
                continue

            u_neighbors = set(self.G.neighbors(u)) & disease_set - {v}
            v_neighbors = set(self.G.neighbors(v)) & disease_set - {u}

            if not u_neighbors or not v_neighbors:
                continue

            # Simplified curvature: overlap-based
            common = len(u_neighbors & v_neighbors)
            total = len(u_neighbors | v_neighbors)
            # Positive curvature = high overlap, negative = low overlap
            curvature = (2 * common - total) / max(total, 1)
            edge_curvature[(u, v)] = curvature

        # Find non-edges near negative-curvature regions
        # These are where the geometry "wants" a bridge
        predictions = {}
        node_crs = defaultdict(list)

        negative_edges = [(u, v) for (u, v), c in edge_curvature.items()
                          if c < -0.2]

        for u, v in negative_edges:
            # Look for non-edges that would "fix" the curvature
            u_neighbors = set(self.G.neighbors(u)) & disease_set
            v_neighbors = set(self.G.neighbors(v)) & disease_set

            for w in u_neighbors:
                if w != v and not self.G.has_edge(v, w):
                    # Edge v-w would increase curvature at u-v
                    score = abs(edge_curvature.get((u, v), 0)) * 0.5
                    existing = predictions.get((v, w), 0)
                    predictions[(v, w)] = max(existing, score)
                    node_crs[v].append((w, score))

            for w in v_neighbors:
                if w != u and not self.G.has_edge(u, w):
                    score = abs(edge_curvature.get((u, v), 0)) * 0.5
                    existing = predictions.get((u, w), 0)
                    predictions[(u, w)] = max(existing, score)
                    node_crs[u].append((w, score))

        # Convert to proper format
        formatted_predictions = {}
        for (u, v), score in predictions.items():
            if score > 0.05:
                formatted_predictions[(u, v)] = {
                    "score": float(score),
                    "curvature_context": float(score),
                }

        node_scores = {}
        for node, preds in node_crs.items():
            if preds:
                scores = [s for _, s in preds]
                node_scores[node] = {
                    "score": float(np.mean(scores)),
                    "n_bridges": len(preds),
                }

        return formatted_predictions, node_scores, edge_curvature

    # ═══════════════════════════════════════════════════════════════════
    # COMPOSITE DISCOVERY SCORE
    # ═══════════════════════════════════════════════════════════════════

    def compute_all_metrics(self):
        """Run all four metrics and return raw results."""
        results = {}

        print("  Computing Symmetry Defect Score...")
        results["sds"] = self.symmetry_defect()

        print("  Computing Harmonic Dissonance Score...")
        results["hds_edges"], results["hds_nodes"] = self.harmonic_dissonance()

        print("  Computing Compositional Incompleteness Score...")
        results["cis_edges"], results["cis_nodes"] = \
            self.compositional_incompleteness()

        print("  Computing Curvature Defect Score...")
        results["crs_edges"], results["crs_nodes"], results["curvature"] = \
            self.curvature_defect()

        return results

    def discovery_score(self, metrics=None, weights=None):
        """
        Compute the composite Discovery Score for all non-edges.

        Combines all four metrics with tunable weights.
        Returns ranked list of discoveries.
        """
        if metrics is None:
            metrics = self.compute_all_metrics()

        if weights is None:
            weights = {
                "sds": 0.30,
                "hds": 0.25,
                "cis": 0.30,
                "crs": 0.15,
            }

        # Collect all predicted non-edges across metrics (canonicalized)
        all_pairs = set()
        for source_dict in [metrics.get("sds", {}),
                            metrics.get("hds_edges", {}),
                            metrics.get("cis_edges", {}),
                            metrics.get("crs_edges", {})]:
            for (a, b) in source_dict.keys():
                all_pairs.add((min(a, b), max(a, b)))

        # Normalize scores per metric to [0, 1]
        def normalize(scores_dict):
            if not scores_dict:
                return {}
            vals = [v["score"] for v in scores_dict.values()]
            max_val = max(vals) if vals else 1
            min_val = min(vals) if vals else 0
            rng = max_val - min_val if max_val != min_val else 1
            # Store with canonical key
            result = {}
            for (a, b), v in scores_dict.items():
                canonical = (min(a, b), max(a, b))
                result[canonical] = (v["score"] - min_val) / rng
            return result

        sds_norm = normalize(metrics.get("sds", {}))
        hds_norm = normalize(metrics.get("hds_edges", {}))
        cis_norm = normalize(metrics.get("cis_edges", {}))
        crs_norm = normalize(metrics.get("crs_edges", {}))

        # Composite score
        discoveries = []
        for pair in all_pairs:
            u, v = pair

            score_components = {
                "sds": sds_norm.get(pair, 0),
                "hds": hds_norm.get(pair, 0),
                "cis": cis_norm.get(pair, 0),
                "crs": crs_norm.get(pair, 0),
            }

            composite = sum(weights.get(k, 0) * v
                            for k, v in score_components.items())

            if composite > 0.01:
                # Gather evidence
                evidence = self._gather_evidence(
                    u, v, metrics, score_components)

                discoveries.append({
                    "entity1": u,
                    "entity2": v,
                    "entity1_name": get_entity_name(u),
                    "entity2_name": get_entity_name(v),
                    "entity1_type": get_entity_type(u),
                    "entity2_type": get_entity_type(v),
                    "composite_score": float(composite),
                    "components": score_components,
                    "evidence": evidence,
                })

        # Rank by composite score
        discoveries.sort(key=lambda x: -x["composite_score"])
        return discoveries

    def _gather_evidence(self, u, v, metrics, components):
        """Gather human-readable evidence for a discovery."""
        evidence = []

        # SDS evidence
        sds_data = metrics.get("sds", {}).get((u, v)) or \
                   metrics.get("sds", {}).get((v, u))
        if sds_data:
            evidence.append({
                "metric": "Symmetry Defect",
                "detail": (
                    f"Gene similarity: {sds_data['gene_similarity']:.2f}, "
                    f"Symptom similarity: {sds_data['symptom_similarity']:.2f}. "
                    f"Direction: {sds_data['direction'].replace('_', ' ')}."
                ),
            })

        # HDS evidence
        hds_data = metrics.get("hds_edges", {}).get((u, v)) or \
                   metrics.get("hds_edges", {}).get((v, u))
        if hds_data:
            evidence.append({
                "metric": "Harmonic Dissonance",
                "detail": (
                    f"Spectral analysis predicts connection strength "
                    f"{hds_data['harmonic_strength']:.3f}."
                ),
            })

        # CIS evidence
        cis_data = metrics.get("cis_edges", {}).get((u, v)) or \
                   metrics.get("cis_edges", {}).get((v, u))
        if cis_data:
            neighbors_str = ", ".join(cis_data.get("neighbors", [])[:5])
            evidence.append({
                "metric": "Compositional Incompleteness",
                "detail": (
                    f"{cis_data['common_neighbors']} common neighbor(s): "
                    f"{neighbors_str}."
                ),
            })

        # CRS evidence
        crs_data = metrics.get("crs_edges", {}).get((u, v)) or \
                   metrics.get("crs_edges", {}).get((v, u))
        if crs_data:
            evidence.append({
                "metric": "Curvature Defect",
                "detail": (
                    f"Network geometry indicates a structural gap "
                    f"(curvature context: {crs_data['curvature_context']:.3f})."
                ),
            })

        return evidence

    def node_harmony_profile(self, node_id):
        """
        Compute a full harmony profile for a single node.
        Shows how beautiful/ugly each dimension of the node's
        local structure is.
        """
        profile = {
            "node": node_id,
            "name": get_entity_name(node_id),
            "type": get_entity_type(node_id),
            "degree": self.G.degree(node_id),
        }

        # Run metrics if not cached
        metrics = self.compute_all_metrics()

        # SDS: average defect for this node's disease pairs
        if get_entity_type(node_id) == "disease":
            sds_scores = []
            for pair, data in metrics["sds"].items():
                if node_id in pair:
                    sds_scores.append(data["score"])
            profile["sds"] = float(np.mean(sds_scores)) if sds_scores else 0

        # HDS
        if node_id in metrics.get("hds_nodes", {}):
            profile["hds"] = metrics["hds_nodes"][node_id]

        # CIS
        if node_id in metrics.get("cis_nodes", {}):
            profile["cis"] = metrics["cis_nodes"][node_id]

        # CRS
        if node_id in metrics.get("crs_nodes", {}):
            profile["crs"] = metrics["crs_nodes"][node_id]

        return profile
