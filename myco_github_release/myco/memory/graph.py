"""
myco/memory/graph.py
NetworkX-based knowledge graph with JSON persistence.
Extracted entities + relationships grow across sessions.
"""
from __future__ import annotations
import json, logging, os, re, time
from collections import defaultdict
from pathlib import Path
from typing import Any

log = logging.getLogger("myco.graph")

ENTITY_PATTERNS = [
    (r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\b', "proper_noun"),
    (r'\b(\d{4})\b',                           "year"),
    (r'\b([A-Z]{2,})\b',                       "acronym"),
]
RELATION_VERBS = ["is","are","was","were","has","have","contains",
                  "produces","causes","enables","prevents","requires"]

_STOP_WORDS = {
    "the","a","an","this","that","these","those","is","are","was","were","be","been",
    "have","has","had","do","does","did","will","would","could","should","may","might",
    "shall","can","not","no","but","and","or","so","yet","for","nor","with","at","by",
    "from","into","during","until","against","among","throughout","despite","towards",
    "upon","concerning","of","in","on","to","up","about","after","before","between",
    "out","off","over","under","again","further","then","once","here","there","when",
    "where","why","how","all","both","each","few","more","most","other","some","such",
    "than","too","very","just","because","as","while","although","i","you","he","she",
    "we","they","it","me","him","her","us","them","my","your","his","our","their","its"
}


class KnowledgeGraph:
    """
    Grows as Myco encounters information.
    Bounded: max 2,000 nodes and 5,000 edges to keep RAM use under 10MB.
    Persisted to disk as JSON so it survives restarts.
    """

    MAX_NODES = 2_000
    MAX_EDGES = 5_000

    def __init__(self, graph_path: str = "data/graph.json"):
        self._graph_path = graph_path
        try:
            import networkx as nx
            self._g  = nx.DiGraph()
            self._nx = nx
        except ImportError:
            log.warning("NetworkX not installed. pip install networkx")
            self._g  = None
            self._nx = None
        self._entity_freq: dict[str, int] = defaultdict(int)
        self._load()

    # ── public ────────────────────────────────────────────────────────────────

    def extract_and_add(self, text: str):
        entities  = self._extract_entities(text)
        relations = self._extract_relations(text, entities)
        for entity, etype in entities:
            self._add_node(entity, etype)
        for subj, verb, obj in relations:
            self._add_edge(subj, verb, obj)
        self._prune()
        if sum(self._entity_freq.values()) % 50 == 0:
            self.save()

    def get_context(self, query: str, hops: int = 2) -> dict:
        if self._g is None:
            return {}
        q_lower  = query.lower()
        anchors  = [n for n in self._g.nodes if q_lower in n.lower()][:3]
        if not anchors:
            return {}
        context: dict[str, list] = {}
        for anchor in anchors:
            try:
                neighbours = list(self._nx.ego_graph(self._g, anchor, radius=hops).edges(data=True))
                context[anchor] = [
                    f"{u} —[{d.get('relation','?')}]→ {v}"
                    for u, v, d in neighbours[:10]
                ]
            except Exception:
                pass
        return context

    def get_stats(self) -> dict:
        if self._g is None:
            return {"nodes": 0, "edges": 0}
        return {"nodes": self._g.number_of_nodes(), "edges": self._g.number_of_edges()}

    def most_connected(self, n: int = 10) -> list[tuple[str, int]]:
        if self._g is None:
            return []
        return sorted(self._g.degree(), key=lambda x: x[1], reverse=True)[:n]

    def save(self):
        """Persist graph to JSON."""
        if self._g is None:
            return
        try:
            Path(self._graph_path).parent.mkdir(parents=True, exist_ok=True)
            data = {
                "nodes": [
                    {"id": n, **self._g.nodes[n]}
                    for n in self._g.nodes
                ],
                "edges": [
                    {"source": u, "target": v, **d}
                    for u, v, d in self._g.edges(data=True)
                ],
                "saved_at": time.time(),
            }
            # Atomic write: write to .tmp then rename
            tmp = self._graph_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self._graph_path)
            log.debug(f"Graph saved: {self._g.number_of_nodes()} nodes, {self._g.number_of_edges()} edges")
        except Exception as e:
            log.warning(f"Graph save failed: {e}")

    # ── private ───────────────────────────────────────────────────────────────

    def _prune(self):
        """Keep graph bounded by removing lowest-frequency nodes when limits exceeded."""
        if self._g is None:
            return
        if self._g.number_of_nodes() > self.MAX_NODES:
            # Remove the least-connected, lowest-frequency nodes
            by_freq = sorted(self._g.nodes(data=True),
                             key=lambda x: (x[1].get("freq", 1), self._g.degree(x[0])))
            to_remove = [n for n, _ in by_freq[:self._g.number_of_nodes() - self.MAX_NODES]]
            self._g.remove_nodes_from(to_remove)
            log.debug(f"Graph pruned: removed {len(to_remove)} low-freq nodes")

        if self._g.number_of_edges() > self.MAX_EDGES:
            # Remove oldest edges (no timestamp, so just trim by count)
            edges = list(self._g.edges())
            to_remove = edges[:self._g.number_of_edges() - self.MAX_EDGES]
            self._g.remove_edges_from(to_remove)

    def _load(self):
        """Load graph from JSON on startup."""
        if self._g is None or not Path(self._graph_path).exists():
            return
        try:
            with open(self._graph_path) as f:
                data = json.load(f)
            for node in data.get("nodes", []):
                nid = node.pop("id")
                self._g.add_node(nid, **node)
                self._entity_freq[nid] = node.get("freq", 1)
            for edge in data.get("edges", []):
                src = edge.pop("source")
                tgt = edge.pop("target")
                self._g.add_edge(src, tgt, **edge)
            log.info(f"Graph loaded: {self._g.number_of_nodes()} nodes, "
                     f"{self._g.number_of_edges()} edges")
        except Exception as e:
            log.warning(f"Graph load failed (starting fresh): {e}")

    def _extract_entities(self, text: str) -> list[tuple[str, str]]:
        found = []
        for pattern, etype in ENTITY_PATTERNS:
            for match in re.finditer(pattern, text):
                entity = match.group(1)
                if len(entity) > 2 and entity.lower() not in _STOP_WORDS:
                    found.append((entity, etype))
        return list(set(found))[:20]

    def _extract_relations(self, text: str, entities: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
        relations = []
        entity_names = [e[0] for e in entities]
        if not entity_names:
            return []
        sentences = re.split(r'[.!?]', text)
        for sent in sentences:
            for verb in RELATION_VERBS:
                pattern = rf'({"|".join(re.escape(n) for n in entity_names)})\s+{verb}\s+(\w+)'
                for m in re.finditer(pattern, sent, re.IGNORECASE):
                    relations.append((m.group(1), verb, m.group(2)))
        return relations[:10]

    def _add_node(self, name: str, etype: str):
        if self._g is None:
            return
        self._entity_freq[name] += 1
        if not self._g.has_node(name):
            self._g.add_node(name, type=etype, freq=0)
        self._g.nodes[name]["freq"] = self._entity_freq[name]

    def _add_edge(self, subj: str, relation: str, obj: str):
        if self._g is None:
            return
        for node in (subj, obj):
            if not self._g.has_node(node):
                self._g.add_node(node, type="unknown", freq=1)
        self._g.add_edge(subj, obj, relation=relation)
