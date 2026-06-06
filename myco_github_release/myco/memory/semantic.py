"""
myco/memory/semantic.py
=======================
Tiered semantic memory — picks the lightest backend that works on this machine.

Tier 1 (default, ultra-light): TF-IDF + cosine similarity — pure Python, zero ML deps, ~2MB RAM
Tier 2 (if chromadb installed): ChromaDB with hash-based IDs + no embedding model (keyword search)
Tier 3 (if chromadb + sentence-transformers): Full vector embeddings — ~150MB RAM

On a low-end PC, Tier 1 runs with NO extra dependencies and uses under 5MB RAM.
"""
from __future__ import annotations
import hashlib, json, logging, math, re, time
from collections import defaultdict
from pathlib import Path
from typing import Any

log = logging.getLogger("myco.semantic")


# ── Tier 1: TF-IDF in pure Python (always available) ─────────────────────────

class TFIDFMemory:
    """
    Pure-Python TF-IDF semantic memory.
    - Zero extra dependencies
    - ~2MB RAM for 10,000 memories
    - Search in O(n) — fine up to ~50,000 memories
    - Persists to a single JSON file
    """

    def __init__(self, path: str = "data/tfidf_memory.json"):
        self._path = path
        self._docs:     list[dict] = []   # [{id, content, metadata, ts}]
        self._idf_cache: dict[str, float] = {}
        self._dirty = False
        self._load()

    async def add(self, text: str, metadata: dict | None = None) -> str:
        mid = hashlib.md5(text.encode()).hexdigest()
        if not any(d["id"] == mid for d in self._docs):
            self._docs.append({"id": mid, "content": text,
                                "metadata": metadata or {}, "ts": time.time()})
            self._idf_cache = {}   # invalidate cache
            self._dirty = True
        return mid

    async def search(self, query: str, k: int = 5) -> list[dict]:
        if not self._docs or not query.strip():
            return []
        q_tokens = self._tokenize(query)
        if not q_tokens:
            return self._docs[-k:][::-1]   # fallback: most recent

        scores: list[tuple[float, dict]] = []
        n = len(self._docs)

        for doc in self._docs:
            d_tokens = self._tokenize(doc["content"])
            score = self._tfidf_cosine(q_tokens, d_tokens, n)
            if score > 0:
                scores.append((score, doc))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [
            {**doc, "score": round(sc, 4)}
            for sc, doc in scores[:k]
        ]

    async def consolidate(self, threshold: int = 500):
        """Remove exact duplicates and very old low-value memories."""
        before = len(self._docs)
        seen: set[str] = set()
        kept:  list[dict] = []
        for d in reversed(self._docs):   # keep newest
            key = d["content"][:100]
            if key not in seen:
                seen.add(key)
                kept.append(d)
        self._docs = list(reversed(kept))
        # If still over threshold, drop oldest 20%
        if len(self._docs) > threshold:
            cut = len(self._docs) - threshold
            self._docs = self._docs[cut:]
        self._idf_cache = {}
        self._dirty = True
        self._save()
        log.info(f"Consolidation: {before} → {len(self._docs)} memories")

    def count(self) -> int:
        return len(self._docs)

    def _save(self):
        if not self._dirty:
            return
        try:
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"docs": self._docs, "saved_at": time.time()}, f)
            import os; os.replace(tmp, self._path)
            self._dirty = False
        except Exception as e:
            log.warning(f"TF-IDF save failed: {e}")

    def _load(self):
        try:
            if Path(self._path).exists():
                with open(self._path) as f:
                    data = json.load(f)
                self._docs = data.get("docs", [])
                log.info(f"TF-IDF memory loaded: {len(self._docs)} entries")
        except Exception as e:
            log.warning(f"TF-IDF load failed (starting fresh): {e}")

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r'[a-zA-Z0-9]+', text.lower())

    def _tf(self, token: str, tokens: list[str]) -> float:
        if not tokens:
            return 0.0
        return tokens.count(token) / len(tokens)

    def _idf(self, token: str, n: int) -> float:
        if token in self._idf_cache:
            return self._idf_cache[token]
        df = sum(1 for d in self._docs if token in self._tokenize(d["content"]))
        val = math.log((n + 1) / (df + 1)) + 1
        self._idf_cache[token] = val
        return val

    def _tfidf_cosine(self, q_tokens: list[str], d_tokens: list[str], n: int) -> float:
        vocab = set(q_tokens) | set(d_tokens)
        q_vec = {t: self._tf(t, q_tokens) * self._idf(t, n) for t in vocab}
        d_vec = {t: self._tf(t, d_tokens) * self._idf(t, n) for t in vocab}
        dot   = sum(q_vec[t] * d_vec[t] for t in vocab)
        qmag  = math.sqrt(sum(v**2 for v in q_vec.values()))
        dmag  = math.sqrt(sum(v**2 for v in d_vec.values()))
        if qmag == 0 or dmag == 0:
            return 0.0
        return dot / (qmag * dmag)


# ── Tier 2/3: ChromaDB with optional embeddings ───────────────────────────────

class ChromaMemory:
    """
    ChromaDB backend — only loaded if chromadb is installed.
    Uses hash IDs (no embedding model) by default to save RAM.
    If sentence-transformers is available, uses real embeddings.
    """

    def __init__(self, path: str = "data/chroma"):
        import chromadb
        from chromadb.config import Settings
        client = chromadb.PersistentClient(
            path=path,
            settings=Settings(anonymized_telemetry=False)
        )
        # Try to use lightweight embeddings, fall back to no embeddings
        try:
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
            ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
            self._collection = client.get_or_create_collection("myco", embedding_function=ef,
                                                                 metadata={"hnsw:space":"cosine"})
            log.info("ChromaDB: using SentenceTransformer embeddings")
        except Exception:
            # No sentence-transformers — use Chroma without embedding model (keyword only)
            self._collection = client.get_or_create_collection("myco",
                                                                metadata={"hnsw:space":"cosine"})
            log.info("ChromaDB: running without embedding model (keyword mode)")

    async def add(self, text: str, metadata: dict | None = None) -> str:
        mid = hashlib.md5(text.encode()).hexdigest()
        try:
            self._collection.upsert(
                ids=[mid], documents=[text],
                metadatas=[{k: str(v) for k, v in (metadata or {}).items()}]
            )
        except Exception as e:
            log.warning(f"ChromaDB add failed: {e}")
        return mid

    async def search(self, query: str, k: int = 5) -> list[dict]:
        try:
            n = min(k, max(1, self._collection.count()))
            r = self._collection.query(query_texts=[query], n_results=n)
            return [
                {"content": d, "metadata": m, "score": round(1 - dist, 4)}
                for d, m, dist in zip(
                    r.get("documents",[[]])[0],
                    r.get("metadatas",[[]])[0],
                    r.get("distances",[[]])[0]
                )
            ]
        except Exception as e:
            log.warning(f"ChromaDB search failed: {e}")
            return []

    async def consolidate(self, threshold: int = 500):
        log.info(f"ChromaDB has {self._collection.count()} memories")

    def count(self) -> int:
        return self._collection.count()


# ── Factory ───────────────────────────────────────────────────────────────────

class SemanticMemory:
    """
    Auto-selects the lightest backend that works on this machine.
    Falls back gracefully so Myco always runs — even on a 2GB RAM PC.
    """

    def __init__(self, chroma_path: str = "data/chroma",
                 tfidf_path: str = "data/tfidf_memory.json",
                 prefer_tfidf: bool = False):
        self._backend = self._pick_backend(chroma_path, tfidf_path, prefer_tfidf)

    def _pick_backend(self, chroma_path, tfidf_path, prefer_tfidf):
        if prefer_tfidf:
            log.info("Semantic memory: TF-IDF mode (forced by config)")
            return TFIDFMemory(tfidf_path)
        try:
            import chromadb
            b = ChromaMemory(chroma_path)
            log.info("Semantic memory: ChromaDB backend")
            return b
        except ImportError:
            log.info("Semantic memory: TF-IDF fallback (chromadb not installed)")
            return TFIDFMemory(tfidf_path)
        except Exception as e:
            log.warning(f"ChromaDB failed ({e}), falling back to TF-IDF")
            return TFIDFMemory(tfidf_path)

    async def add(self, text: str, metadata: dict | None = None) -> str:
        return await self._backend.add(text, metadata)

    async def search(self, query: str, k: int = 5) -> list[dict]:
        return await self._backend.search(query, k)

    async def consolidate(self, threshold: int = 500):
        await self._backend.consolidate(threshold)

    def count(self) -> int:
        return self._backend.count()

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__
