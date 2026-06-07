"""
Discovery Pipeline
==================
Orchestrates the Harmony Engine to find, rank, and explain
undiscovered connections in the rare disease knowledge graph.

The pipeline:
1. Build the knowledge graph
2. Compute all harmony metrics
3. Rank non-edges by composite discovery score
4. Generate human-readable explanations
5. Validate by held-out edge recovery
"""

import numpy as np
from collections import defaultdict

from knowledge_graph import KnowledgeGraph
from harmony_engine import HarmonyEngine
from rare_disease_kb import get_entity_name, get_entity_type, DISEASES


class DiscoveryPipeline:
    """Finds undiscovered knowledge by measuring structural beauty."""

    def __init__(self):
        print("Building knowledge graph...")
        self.kg = KnowledgeGraph()
        print(f"  {self.kg.G.number_of_nodes()} nodes, "
              f"{self.kg.G.number_of_edges()} edges")

        self.engine = HarmonyEngine(self.kg)
        self._metrics = None
        self._discoveries = None

    def run(self):
        """Run the full discovery pipeline."""
        print("\nComputing harmony metrics...")
        self._metrics = self.engine.compute_all_metrics()

        print("\nComputing discovery scores...")
        self._discoveries = self.engine.discovery_score(self._metrics)

        print(f"\nFound {len(self._discoveries)} potential discoveries.")
        return self._discoveries

    def top_discoveries(self, n=20, min_score=0.0):
        """Get the top N discoveries above a minimum score."""
        if self._discoveries is None:
            self.run()
        filtered = [d for d in self._discoveries
                    if d["composite_score"] >= min_score]
        return filtered[:n]

    def discoveries_for_disease(self, disease_id, n=10):
        """Get discoveries related to a specific disease."""
        if self._discoveries is None:
            self.run()
        related = [d for d in self._discoveries
                   if disease_id in (d["entity1"], d["entity2"])]
        return related[:n]

    def discoveries_by_metric(self, metric_name, n=20):
        """
        Get discoveries where a specific metric contributes most.
        metric_name: 'sds', 'hds', 'cis', 'crs'
        """
        if self._discoveries is None:
            self.run()

        def dominant_metric(disc):
            components = disc["components"]
            max_metric = max(components, key=components.get)
            return max_metric == metric_name

        filtered = [d for d in self._discoveries if dominant_metric(d)]
        return filtered[:n]

    def explain_discovery(self, discovery):
        """Generate a detailed explanation of a discovery."""
        e1 = discovery["entity1_name"]
        e2 = discovery["entity2_name"]
        t1 = discovery["entity1_type"]
        t2 = discovery["entity2_type"]
        score = discovery["composite_score"]
        components = discovery["components"]
        evidence = discovery["evidence"]

        # Determine the primary "story"
        dominant = max(components, key=components.get)

        stories = {
            "sds": self._explain_sds,
            "hds": self._explain_hds,
            "cis": self._explain_cis,
            "crs": self._explain_crs,
        }

        story_fn = stories.get(dominant, self._explain_generic)
        story = story_fn(discovery)

        explanation = {
            "title": f"Hidden connection: {e1} — {e2}",
            "summary": (
                f"The harmony structure of the knowledge graph suggests "
                f"a connection between {e1} ({t1}) and {e2} ({t2}) "
                f"with confidence {score:.2f}."
            ),
            "story": story,
            "evidence": evidence,
            "scores": components,
            "dominant_metric": dominant,
        }

        return explanation

    def _explain_sds(self, disc):
        e1 = disc["entity1_name"]
        e2 = disc["entity2_name"]
        sds_evidence = [e for e in disc["evidence"]
                        if e["metric"] == "Symmetry Defect"]
        if sds_evidence:
            detail = sds_evidence[0]["detail"]
            return (
                f"Think of it like this: {e1} and {e2} share "
                f"certain features — either similar genes, similar "
                f"symptoms, or both. But the overlap isn't balanced. "
                f"{detail} "
                f"When two diseases are alike in one way but not "
                f"another, it often means there's a hidden link "
                f"between them that hasn't been discovered yet."
            )
        return (
            f"The patterns connecting {e1} and {e2} don't line up "
            f"the way they should, suggesting a missing connection."
        )

    def _explain_hds(self, disc):
        e1 = disc["entity1_name"]
        e2 = disc["entity2_name"]
        return (
            f"Imagine the knowledge graph as a web where every "
            f"disease is connected to others through shared features. "
            f"When we look at the overall pattern of connections, "
            f"{e1} and {e2} should be linked — their positions in "
            f"the network suggest they belong together. The fact "
            f"that no connection is recorded between them is like "
            f"a missing note in a melody."
        )

    def _explain_cis(self, disc):
        e1 = disc["entity1_name"]
        e2 = disc["entity2_name"]
        cis_evidence = [e for e in disc["evidence"]
                        if e["metric"] == "Compositional Incompleteness"]
        if cis_evidence:
            detail = cis_evidence[0]["detail"]
            return (
                f"Here's what we found: {detail} "
                f"These shared connections form a pattern — like "
                f"two friends who know all the same people. "
                f"When two diseases share many of the same "
                f"connections, they should also be connected to "
                f"each other. The missing link between {e1} and "
                f"{e2} looks like a gap in the map."
            )
        return (
            f"The network pattern strongly suggests {e1} and "
            f"{e2} should be connected."
        )

    def _explain_crs(self, disc):
        e1 = disc["entity1_name"]
        e2 = disc["entity2_name"]
        return (
            f"Think of the knowledge graph like a map. In a "
            f"well-connected area, everything is close together. "
            f"But near {e1} and {e2}, there's a gap — a bridge "
            f"that should exist but doesn't. The shape of the "
            f"network around these two diseases suggests they're "
            f"meant to be linked, like two islands that should "
            f"have a road between them."
        )

    def _explain_generic(self, disc):
        e1 = disc["entity1_name"]
        e2 = disc["entity2_name"]
        return (
            f"Several different patterns in the knowledge graph "
            f"point to a connection between {e1} and {e2}. "
            f"The evidence from multiple angles suggests these "
            f"two diseases are more closely related than what's "
            f"currently documented."
        )

    def validate_held_out(self, holdout_fraction=0.2, n_trials=5):
        """
        Validate by holding out known edges and checking if the
        engine recovers them.
        """
        import random

        # Get disease-disease similarity edges
        disease_edges = [(u, v) for u, v, d in self.kg.G.edges(data=True)
                         if d.get("type") == "similar"]

        if len(disease_edges) < 10:
            return {"error": "Not enough disease edges for validation"}

        precisions = []
        recalls = []

        for trial in range(n_trials):
            random.seed(trial * 42)
            n_holdout = max(1, int(len(disease_edges) * holdout_fraction))
            holdout = random.sample(disease_edges, n_holdout)

            # Remove held-out edges temporarily
            for u, v in holdout:
                self.kg.G.remove_edge(u, v)

            # Recompute
            engine = HarmonyEngine(self.kg)
            metrics = engine.compute_all_metrics()
            discoveries = engine.discovery_score(metrics)

            # Restore edges
            for u, v in holdout:
                self.kg.G.add_edge(u, v, type="similar", weight=0.5)

            # Check recovery
            discovered_pairs = set()
            for d in discoveries[:50]:  # Top 50
                pair = tuple(sorted([d["entity1"], d["entity2"]]))
                discovered_pairs.add(pair)

            holdout_pairs = set(tuple(sorted(e)) for e in holdout)
            recovered = discovered_pairs & holdout_pairs

            precision = len(recovered) / len(discovered_pairs) \
                if discovered_pairs else 0
            recall = len(recovered) / len(holdout_pairs) \
                if holdout_pairs else 0

            precisions.append(precision)
            recalls.append(recall)

        return {
            "mean_precision": float(np.mean(precisions)),
            "mean_recall": float(np.mean(recalls)),
            "precision_std": float(np.std(precisions)),
            "recall_std": float(np.std(recalls)),
            "n_trials": n_trials,
            "holdout_fraction": holdout_fraction,
        }

    def graph_data_for_visualization(self, focus_disease=None):
        """
        Prepare graph data for D3.js visualization.
        Returns nodes and edges with harmony annotations.
        """
        G = self.kg.G

        # Determine which nodes to include
        if focus_disease:
            subgraph = self.kg.subgraph_for_disease(focus_disease, hops=2)
            node_ids = set(subgraph.nodes())
        else:
            # Include all diseases and their direct connections
            node_ids = set(self.kg.nodes_by_type("disease"))
            for d in list(node_ids):
                for neighbor in G.neighbors(d):
                    node_ids.add(neighbor)

        # Build node list with harmony scores
        nodes = []
        for nid in node_ids:
            ndata = G.nodes[nid]
            node = {
                "id": nid,
                "name": ndata.get("name", nid),
                "type": ndata.get("type", "unknown"),
                "degree": G.degree(nid),
            }
            if ndata.get("type") == "disease":
                node["category"] = ndata.get("category", "")
            nodes.append(node)

        # Build edge list
        edges = []
        for u, v, edata in G.edges(data=True):
            if u in node_ids and v in node_ids:
                edges.append({
                    "source": u,
                    "target": v,
                    "type": edata.get("type", "unknown"),
                    "weight": edata.get("weight", 1),
                })

        # Add top predicted edges (discoveries)
        if self._discoveries:
            predicted = []
            for disc in self._discoveries[:30]:
                e1, e2 = disc["entity1"], disc["entity2"]
                if e1 in node_ids and e2 in node_ids:
                    predicted.append({
                        "source": e1,
                        "target": e2,
                        "type": "predicted",
                        "score": disc["composite_score"],
                        "components": disc["components"],
                    })
        else:
            predicted = []

        return {
            "nodes": nodes,
            "edges": edges,
            "predicted_edges": predicted,
        }
