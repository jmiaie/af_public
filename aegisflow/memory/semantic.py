"""
AegisFlow Semantic Memory Layer.

Provides embedding-based retrieval over the MemoryVault.
Uses sentence-transformers (all-MiniLM-L6-v2) for embeddings.

Components:
- SemanticMemory: Stores content + embeddings, retrieves by cosine similarity
- VaultIndex: Full-text + semantic search over the entire vault
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

logger = logging.getLogger(__name__)

# Lazy import to avoid loading model at module import time
_st_encoder = None
_st_model_name = "sentence-transformers/all-MiniLM-L6-v2"


def _get_encoder() -> Any:
    """Lazy-load the sentence-transformers encoder."""
    global _st_encoder
    if _st_encoder is None:
        logger.info(f"Loading embedding model: {_st_model_name}")
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        _st_encoder = SentenceTransformer(_st_model_name)
        logger.info("Embedding model loaded")
    return _st_encoder


@dataclass
class MemoryChunk:
    """A stored memory entry with its embedding."""
    chunk_id: str
    content: str
    category: str
    filename: str
    embedding: Optional[List[float]] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "category": self.category,
            "filename": self.filename,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


class SemanticMemory:
    """
    Stores content with embeddings for semantic retrieval.

    Uses:
    - all-MiniLM-L6-v2: 384-dim embeddings, ~20ms encode on CPU
    - Cosine similarity for retrieval
    - Disk-persisted index for durability across restarts

    Usage:
        sm = SemanticMemory("/tmp/semantic_vault")
        sm.store("Analyze Arizona real estate market", category="work", filename="re.md")
        results = sm.retrieve("Arizona property investment", top_k=5)
    """

    def __init__(
        self,
        vault_path: str = "./semantic_vault",
        embed_model: Optional[str] = None,
        embedding_dim: int = 384,
    ):
        self.vault_path = Path(vault_path)
        self.embed_model = embed_model or _st_model_name
        self.embedding_dim = embedding_dim

        # Index stored on disk as JSON
        self.index_file = self.vault_path / ".semantic_index.json"
        self.index: List[MemoryChunk] = []

        # Load existing index
        self._ensure_structure()
        self._load_index()

    def _ensure_structure(self) -> None:
        """Create vault directories."""
        self.vault_path.mkdir(parents=True, exist_ok=True)
        (self.vault_path / "brain").mkdir(exist_ok=True)
        (self.vault_path / "work").mkdir(exist_ok=True)
        (self.vault_path / "org").mkdir(exist_ok=True)
        (self.vault_path / "perf").mkdir(exist_ok=True)
        (self.vault_path / ".index").mkdir(exist_ok=True)

    def _load_index(self) -> None:
        """Load index from disk."""
        if self.index_file.exists():
            try:
                with open(self.index_file) as f:
                    data = json.load(f)
                self.index = [MemoryChunk(**d) for d in data]
                logger.info(f"Loaded {len(self.index)} chunks from index")
            except Exception as e:
                logger.warning(f"Failed to load index: {e}")
                self.index = []
        else:
            self.index = []

    def _save_index(self) -> None:
        """Persist index to disk."""
        try:
            data = [c.to_dict() for c in self.index]
            with open(self.index_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save index: {e}")

    def _embed(self, texts: List[str]) -> List[List[float]]:
        """Encode texts to embedding vectors."""
        encoder = _get_encoder()
        embeddings = encoder.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return cast(List[List[float]], embeddings.tolist())

    def _cosine_sim(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        import math
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        return dot / (norm_a * norm_b + 1e-8)

    def store(
        self,
        content: str,
        category: str = "work",
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        embed: bool = True,
    ) -> str:
        """
        Store content with its embedding.

        Returns the chunk_id.
        """
        chunk_id = hashlib.sha256(content.encode()).hexdigest()[:16]
        filename = filename or f"{chunk_id}.md"

        # Generate embedding
        embedding = None
        if embed:
            try:
                embedding = self._embed([content])[0]
            except Exception as e:
                logger.warning(f"Embedding failed: {e}")

        chunk = MemoryChunk(
            chunk_id=chunk_id,
            content=content,
            category=category,
            filename=filename,
            embedding=embedding,
            metadata=metadata or {},
        )

        self.index.append(chunk)

        # Write content to vault
        cat_path = self.vault_path / category
        cat_path.mkdir(exist_ok=True)
        with open(cat_path / filename, "w") as f:
            f.write(content)

        self._save_index()
        return chunk_id

    def store_batch(self, items: List[Dict[str, str]], batch_size: int = 32) -> List[str]:
        """
        Store multiple items efficiently with batched embedding.

        Args:
            items: [{"content": "...", "category": "...", "filename": "..."}, ...]
        """
        chunk_ids = []
        contents = [item["content"] for item in items]

        # Batch embed
        embeddings: List[Optional[List[float]]]
        try:
            embeddings = cast(List[Optional[List[float]]], self._embed(contents))
        except Exception as e:
            logger.warning(f"Batch embedding failed: {e}, storing without embeddings")
            embeddings = [None] * len(contents)

        for i, item in enumerate(items):
            chunk_id = hashlib.sha256(item["content"].encode()).hexdigest()[:16]
            chunk = MemoryChunk(
                chunk_id=chunk_id,
                content=item["content"],
                category=item.get("category", "work"),
                filename=item.get("filename", f"{chunk_id}.md"),
                embedding=embeddings[i] if i < len(embeddings) else None,
            )
            self.index.append(chunk)
            chunk_ids.append(chunk_id)

            # Write file
            cat_path = self.vault_path / chunk.category
            cat_path.mkdir(exist_ok=True)
            with open(cat_path / chunk.filename, "w") as f:
                f.write(chunk.content)

        self._save_index()
        return chunk_ids

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the most semantically similar chunks to the query.

        Args:
            query: Natural language query
            top_k: Number of results to return
            category: Filter by category (brain/work/org/perf)
            min_score: Minimum cosine similarity threshold

        Returns:
            List of {"chunk": MemoryChunk, "score": float, "content": str}
        """
        if not self.index:
            return []

        # Encode query
        try:
            query_emb = self._embed([query])[0]
        except Exception as e:
            logger.warning(f"Query embedding failed: {e}")
            return []

        # Score all chunks with embeddings
        scored = []
        for chunk in self.index:
            if chunk.embedding is None:
                continue
            if category and chunk.category != category:
                continue
            score = self._cosine_sim(query_emb, chunk.embedding)
            if score >= min_score:
                scored.append((chunk, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for chunk, score in scored[:top_k]:
            results.append({
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "category": chunk.category,
                "filename": chunk.filename,
                "score": round(score, 4),
                "created_at": chunk.created_at,
                "metadata": chunk.metadata,
            })

        return results

    def retrieve_text(self, query: str, top_k: int = 3) -> str:
        """Retrieve as a formatted text string for LLM context injection."""
        results = self.retrieve(query, top_k=top_k)
        if not results:
            return "(No relevant memory found)"

        lines = ["--- Relevant Memory ---"]
        for r in results:
            lines.append(f"[{r['category']}] {r['content'][:300]}... (score: {r['score']})")
        return "\n".join(lines)

    def search_by_keyword(self, keyword: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Simple keyword search (BM25-style) as a fallback."""
        results = []
        for chunk in self.index:
            if keyword.lower() in chunk.content.lower():
                if category is None or chunk.category == category:
                    results.append({
                        "chunk_id": chunk.chunk_id,
                        "content": chunk.content,
                        "category": chunk.category,
                        "filename": chunk.filename,
                        "score": 1.0,  # keyword match = 1.0
                        "created_at": chunk.created_at,
                    })
        return results[:10]

    def stats(self) -> Dict[str, Any]:
        """Return index statistics."""
        categories: Dict[str, int] = {}
        for chunk in self.index:
            categories[chunk.category] = categories.get(chunk.category, 0) + 1
        with_emb = sum(1 for c in self.index if c.embedding is not None)
        return {
            "total_chunks": len(self.index),
            "with_embeddings": with_emb,
            "without_embeddings": len(self.index) - with_emb,
            "by_category": categories,
            "embedding_model": self.embed_model,
            "embedding_dim": self.embedding_dim,
        }

    def clear(self) -> None:
        """Clear all chunks and reset index."""
        self.index = []
        self._save_index()
        import shutil
        for cat in ["brain", "work", "org", "perf"]:
            p = self.vault_path / cat
            if p.exists():
                shutil.rmtree(p)
        self._ensure_structure()
