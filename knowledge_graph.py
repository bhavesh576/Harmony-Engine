"""
Knowledge Graph Engine
======================
Constructs and manages the multi-layer knowledge graph from the
rare disease knowledge base. The graph has four node types
(Disease, Symptom, Gene, Pathway) and six edge types.

The graph is the substrate on which the Harmony Engine operates.
"""

import networkx as nx
import numpy as np
from collections import defaultdict

from rare_disease_kb import (
    DISEASES, SYMPTOMS, GENES, PATHWAYS,
    get_entity_name, get_entity_type,
)


class KnowledgeGraph:
    """Multi-layer knowledge graph for rare disease analysis."""

    def __init__(self):
        self.G = nx.Graph()
        self._build_graph()

    def _build_graph(self):
        """Construct the full multi-layer knowledge graph."""
        # Add all nodes with their types
        for did, ddata in DISEASES.items():
            self.G.add_node(did, type="disease", name=ddata["name"],
                            category=ddata["category"])
        for sid, sname in SYMPTOMS.items():
            self.G.add_node(sid, type="symptom", name=sname)
        for gid, gname in GENES.items():
            self.G.add_node(gid, type="gene", name=gname)
        for pid, pname in PATHWAYS.items():
            self.G.add_node(pid, type="pathway", name=pname)

        # Add edges: Disease — Symptom
        for did, ddata in DISEASES.items():
            for sid in ddata["symptoms"]:
                self.G.add_edge(did, sid, type="presents")

        # Add edges: Disease — Gene
        for did, ddata in DISEASES.items():
            for gid in ddata["genes"]:
                self.G.add_edge(did, gid, type="linked_gene")

        # Add edges: Gene — Pathway
        for did, ddata in DISEASES.items():
            for gid in ddata["genes"]:
                for pid in ddata["pathways"]:
                    self.G.add_edge(gid, pid, type="participates")

        # Add edges: Disease — Pathway (through genes)
        for did, ddata in DISEASES.items():
            for pid in ddata["pathways"]:
                self.G.add_edge(did, pid, type="in_pathway")

        # Add edges: Symptom — Symptom (co-occurrence in diseases)
        symptom_co = defaultdict(int)
        for ddata in DISEASES.values():
            symptoms = ddata["symptoms"]
            for i, s1 in enumerate(symptoms):
                for s2 in symptoms[i+1:]:
                    pair = tuple(sorted([s1, s2]))
                    symptom_co[pair] += 1
        for (s1, s2), count in symptom_co.items():
            if count >= 2:  # Only if co-occurring in ≥2 diseases
                self.G.add_edge(s1, s2, type="co_occurs", weight=count)

        # Add edges: Gene — Gene (shared pathway or shared disease)
        gene_shared = defaultdict(int)
        for ddata in DISEASES.values():
            genes = ddata["genes"]
            for i, g1 in enumerate(genes):
                for g2 in genes[i+1:]:
                    pair = tuple(sorted([g1, g2]))
                    gene_shared[pair] += 1
        # Also from shared pathways
        gene_pathway = defaultdict(set)
        for ddata in DISEASES.values():
            for gid in ddata["genes"]:
                for pid in ddata["pathways"]:
                    gene_pathway[gid].add(pid)
        all_genes = list(GENES.keys())
        for i, g1 in enumerate(all_genes):
            for g2 in all_genes[i+1:]:
                shared_p = len(gene_pathway[g1] & gene_pathway[g2])
                if shared_p > 0:
                    gene_shared[tuple(sorted([g1, g2]))] += shared_p
        for (g1, g2), count in gene_shared.items():
            self.G.add_edge(g1, g2, type="interacts", weight=count)

        # Add edges: Disease — Disease (phenotypic similarity)
        # Note: Limited to 500 diseases for faster startup
        disease_sim = {}
        dlist = list(DISEASES.keys())[:500]  # Limit to first 500 diseases for performance
        for i, d1 in enumerate(dlist):
            s1 = set(DISEASES[d1]["symptoms"])
            if not s1:  # Skip diseases with no symptoms
                continue
            for d2 in dlist[i+1:]:
                s2 = set(DISEASES[d2]["symptoms"])
                if not s2:  # Skip diseases with no symptoms
                    continue
                jaccard = len(s1 & s2) / len(s1 | s2) if s1 | s2 else 0
                if jaccard >= 0.3:  # Increased threshold for faster computation
                    self.G.add_edge(d1, d2, type="similar", weight=jaccard)
                    disease_sim[(d1, d2)] = jaccard

    # ── Accessors ────────────────────────────────────────────────────

    def nodes_by_type(self, node_type):
        """Get all nodes of a given type."""
        return [n for n, d in self.G.nodes(data=True)
                if d.get("type") == node_type]

    def edges_by_type(self, edge_type):
        """Get all edges of a given type."""
        return [(u, v) for u, v, d in self.G.edges(data=True)
                if d.get("type") == edge_type]

    def disease_symptom_matrix(self):
        """Build the disease-symptom incidence matrix."""
        diseases = self.nodes_by_type("disease")
        symptoms = self.nodes_by_type("symptom")
        matrix = np.zeros((len(diseases), len(symptoms)))
        for i, d in enumerate(diseases):
            neighbors = set(self.G.neighbors(d))
            for j, s in enumerate(symptoms):
                if s in neighbors:
                    matrix[i, j] = 1
        return diseases, symptoms, matrix

    def disease_gene_matrix(self):
        """Build the disease-gene incidence matrix."""
        diseases = self.nodes_by_type("disease")
        genes = self.nodes_by_type("gene")
        matrix = np.zeros((len(diseases), len(genes)))
        for i, d in enumerate(diseases):
            neighbors = set(self.G.neighbors(d))
            for j, g in enumerate(genes):
                if g in neighbors:
                    matrix[i, j] = 1
        return diseases, genes, matrix

    def gene_pathway_matrix(self):
        """Build the gene-pathway incidence matrix."""
        genes = self.nodes_by_type("gene")
        pathways = self.nodes_by_type("pathway")
        matrix = np.zeros((len(genes), len(pathways)))
        for i, g in enumerate(genes):
            neighbors = set(self.G.neighbors(g))
            for j, p in enumerate(pathways):
                if p in neighbors:
                    matrix[i, j] = 1
        return genes, pathways, matrix

    def adjacency_matrix(self, node_type=None):
        """
        Build the adjacency matrix, optionally filtered to a node type.
        Returns (node_list, matrix).
        """
        if node_type:
            nodes = self.nodes_by_type(node_type)
        else:
            nodes = list(self.G.nodes())
        n = len(nodes)
        node_idx = {node: i for i, node in enumerate(nodes)}
        matrix = np.zeros((n, n))
        for u, v in self.G.edges():
            if u in node_idx and v in node_idx:
                i, j = node_idx[u], node_idx[v]
                w = self.G[u][v].get("weight", 1.0)
                matrix[i, j] = w
                matrix[j, i] = w
        return nodes, matrix

    def get_non_edges(self, node_type=None):
        """
        Get all non-edges (missing connections) in the graph,
        optionally filtered to a specific node type.
        """
        if node_type:
            nodes = self.nodes_by_type(node_type)
        else:
            nodes = list(self.G.nodes())
        non_edges = []
        for i, u in enumerate(nodes):
            for v in nodes[i+1:]:
                if not self.G.has_edge(u, v):
                    non_edges.append((u, v))
        return non_edges

    def get_disease_neighbors_by_type(self, disease_id):
        """Get all neighbors of a disease grouped by type."""
        result = defaultdict(list)
        for neighbor in self.G.neighbors(disease_id):
            ntype = self.G.nodes[neighbor].get("type", "unknown")
            result[ntype].append(neighbor)
        return dict(result)

    def subgraph_for_disease(self, disease_id, hops=1):
        """Get the local subgraph around a disease."""
        nodes = {disease_id}
        frontier = {disease_id}
        for _ in range(hops):
            new_frontier = set()
            for node in frontier:
                for neighbor in self.G.neighbors(node):
                    if neighbor not in nodes:
                        new_frontier.add(neighbor)
            nodes |= new_frontier
            frontier = new_frontier
        return self.G.subgraph(nodes)

    def stats(self):
        """Return graph statistics."""
        type_counts = defaultdict(int)
        for _, d in self.G.nodes(data=True):
            type_counts[d.get("type", "unknown")] += 1
        edge_type_counts = defaultdict(int)
        for _, _, d in self.G.edges(data=True):
            edge_type_counts[d.get("type", "unknown")] += 1
        return {
            "total_nodes": self.G.number_of_nodes(),
            "total_edges": self.G.number_of_edges(),
            "nodes_by_type": dict(type_counts),
            "edges_by_type": dict(edge_type_counts),
            "density": nx.density(self.G),
            "avg_clustering": nx.average_clustering(self.G),
        }
