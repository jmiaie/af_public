"""
Tests for aegisflow.memory — SemanticMemory (with a fake, deterministic
encoder instead of sentence-transformers) and the AegisFlowMemory bridge
(with a fake OMPA object).
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

import aegisflow.memory.semantic as semantic_mod
from aegisflow.memory.ompa_memory import AegisFlowMemory
from aegisflow.memory.semantic import MemoryChunk, SemanticMemory

# ── fake encoder ─────────────────────────────────────────────────────────────

_VOCAB = ["arizona", "property", "python", "code", "weather"]


class _Vectors:
    def __init__(self, rows: List[List[float]]):
        self._rows = rows

    def tolist(self) -> List[List[float]]:
        return self._rows


class _FakeEncoder:
    """Bag-of-words over a tiny vocabulary: similar text → similar vectors."""

    def __init__(self) -> None:
        self.calls = 0

    def encode(self, texts: List[str], **kwargs: Any) -> _Vectors:
        self.calls += 1
        rows = []
        for t in texts:
            low = t.lower()
            rows.append([float(low.count(w)) for w in _VOCAB])
        return _Vectors(rows)


class _BrokenEncoder:
    def encode(self, texts: List[str], **kwargs: Any) -> _Vectors:
        raise RuntimeError("model unavailable")


@pytest.fixture
def encoder(monkeypatch):
    enc = _FakeEncoder()
    monkeypatch.setattr(semantic_mod, "_st_encoder", enc)
    return enc


@pytest.fixture
def broken_encoder(monkeypatch):
    monkeypatch.setattr(semantic_mod, "_st_encoder", _BrokenEncoder())


# ── SemanticMemory ───────────────────────────────────────────────────────────


class TestSemanticMemory:
    def test_structure_created(self, tmp_path, encoder):
        SemanticMemory(str(tmp_path / "v"))
        for d in ["brain", "work", "org", "perf", ".index"]:
            assert (tmp_path / "v" / d).is_dir()

    def test_get_encoder_lazy_loads_once(self, monkeypatch):
        loaded: List[str] = []

        class _ST:
            def __init__(self, name: str) -> None:
                loaded.append(name)

        fake_mod = MagicMock(SentenceTransformer=_ST)
        monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)
        monkeypatch.setattr(semantic_mod, "_st_encoder", None)
        first = semantic_mod._get_encoder()
        assert semantic_mod._get_encoder() is first
        assert loaded == [semantic_mod._st_model_name]

    def test_store_and_retrieve_ranked(self, tmp_path, encoder):
        sm = SemanticMemory(str(tmp_path))
        a = sm.store("Arizona property deal", category="work", filename="az.md")
        sm.store("python code review", category="brain", metadata={"k": 1})
        sm.store("weather today", category="org")
        assert (tmp_path / "work" / "az.md").read_text() == "Arizona property deal"

        results = sm.retrieve("arizona property investment", top_k=2)
        assert results[0]["chunk_id"] == a
        assert results[0]["score"] > 0.9
        assert len(results) == 2

        only_brain = sm.retrieve("python", category="brain")
        assert [r["category"] for r in only_brain] == ["brain"]
        assert only_brain[0]["metadata"] == {"k": 1}

        assert sm.retrieve("arizona property", min_score=0.99)[0]["chunk_id"] == a
        assert len(sm.retrieve("arizona property", min_score=0.99)) == 1

    def test_retrieve_empty_index(self, tmp_path, encoder):
        assert SemanticMemory(str(tmp_path)).retrieve("x") == []

    def test_store_without_embedding_is_skipped_in_retrieve(self, tmp_path, encoder):
        sm = SemanticMemory(str(tmp_path))
        sm.store("arizona", embed=False)
        assert sm.retrieve("arizona") == []
        assert sm.stats()["without_embeddings"] == 1

    def test_index_persists_and_reloads(self, tmp_path, encoder):
        sm = SemanticMemory(str(tmp_path))
        cid = sm.store("python code", category="brain")
        data = json.loads((tmp_path / ".semantic_index.json").read_text())
        assert data[0]["chunk_id"] == cid
        reloaded = SemanticMemory(str(tmp_path))
        assert [c.chunk_id for c in reloaded.index] == [cid]

    def test_corrupt_index_is_ignored(self, tmp_path, encoder):
        (tmp_path / ".semantic_index.json").write_text("{not json")
        assert SemanticMemory(str(tmp_path)).index == []

    def test_save_failure_is_logged_not_raised(self, tmp_path, encoder, caplog):
        sm = SemanticMemory(str(tmp_path))
        sm.index_file = tmp_path / "missing_dir" / "idx.json"
        sm._save_index()
        assert "Failed to save index" in caplog.text

    def test_embedding_failure_still_stores(self, tmp_path, broken_encoder):
        sm = SemanticMemory(str(tmp_path))
        sm.store("arizona")
        assert sm.index[0].embedding is None
        assert sm.retrieve("arizona") == []  # query embedding fails too

    def test_store_batch(self, tmp_path, encoder):
        sm = SemanticMemory(str(tmp_path))
        ids = sm.store_batch(
            [
                {"content": "arizona property", "category": "work", "filename": "a.md"},
                {"content": "python code"},
            ]
        )
        assert len(ids) == 2 and encoder.calls == 1
        assert (tmp_path / "work" / "a.md").exists()
        assert (tmp_path / "work" / f"{ids[1]}.md").exists()
        assert sm.stats()["with_embeddings"] == 2

    def test_store_batch_embedding_failure(self, tmp_path, broken_encoder):
        sm = SemanticMemory(str(tmp_path))
        sm.store_batch([{"content": "a"}, {"content": "b"}])
        assert all(c.embedding is None for c in sm.index)

    def test_retrieve_text(self, tmp_path, encoder):
        sm = SemanticMemory(str(tmp_path))
        assert sm.retrieve_text("arizona") == "(No relevant memory found)"
        sm.store("Arizona property", category="work")
        text = sm.retrieve_text("arizona")
        assert text.startswith("--- Relevant Memory ---")
        assert "[work] Arizona property" in text

    def test_keyword_search(self, tmp_path, encoder):
        sm = SemanticMemory(str(tmp_path))
        sm.store("Arizona property", category="work")
        sm.store("arizona weather", category="org")
        assert len(sm.search_by_keyword("ARIZONA")) == 2
        assert [r["category"] for r in sm.search_by_keyword("arizona", "org")] == ["org"]
        assert sm.search_by_keyword("nothing") == []

    def test_stats_and_clear(self, tmp_path, encoder):
        sm = SemanticMemory(str(tmp_path))
        sm.store("a", category="work")
        sm.store("b", category="brain")
        stats = sm.stats()
        assert stats["total_chunks"] == 2
        assert stats["by_category"] == {"work": 1, "brain": 1}
        assert stats["embedding_dim"] == 384
        sm.clear()
        assert sm.index == [] and sm.stats()["total_chunks"] == 0
        assert list((tmp_path / "work").iterdir()) == []

    def test_cosine_sim(self, tmp_path, encoder):
        sm = SemanticMemory(str(tmp_path))
        assert sm._cosine_sim([1, 0], [1, 0]) == pytest.approx(1.0, abs=1e-6)
        assert sm._cosine_sim([1, 0], [0, 1]) == pytest.approx(0.0)
        assert sm._cosine_sim([0, 0], [0, 0]) == 0.0

    def test_memory_chunk_to_dict_omits_embedding(self):
        d = MemoryChunk("id", "c", "work", "f.md", embedding=[1.0]).to_dict()
        assert "embedding" not in d and d["chunk_id"] == "id"


# ── AegisFlowMemory ──────────────────────────────────────────────────────────


@pytest.fixture
def no_ompa(monkeypatch):
    # A None entry in sys.modules makes `from ompa import Ompa` raise ImportError.
    monkeypatch.setitem(sys.modules, "ompa", None)


class TestAegisFlowMemoryWithoutOmpa:
    def test_everything_degrades_gracefully(self, tmp_path, no_ompa, encoder):
        mem = AegisFlowMemory(vault_path=tmp_path)
        unavailable = {"success": False, "error": "OMPA not available"}
        assert mem.ompa is None
        assert mem.session_start() == unavailable
        assert mem.standup() == unavailable
        assert mem.handle_message("hi") == unavailable
        assert mem.post_tool("write", {}) == unavailable
        assert mem.stop() == unavailable
        assert mem.wrap_up() == unavailable
        assert mem.classify("hi") is None
        assert mem.get_routing_hint("hi") == "ompa_unavailable"
        assert mem.kg_add("a", "b", "c") is None
        assert mem.kg_query("a") == []
        assert mem.get_stats() == {}
        assert mem.update_brain("n", "c") is None
        assert mem.rebuild_index() == 0
        assert mem.sync() == {}

    def test_search_falls_back_to_semantic_memory(self, tmp_path, no_ompa, encoder):
        mem = AegisFlowMemory(vault_path=tmp_path)
        assert isinstance(mem.semantic_memory, SemanticMemory)
        assert mem.semantic_memory is mem.semantic_memory  # cached
        mem.semantic_memory.store("Arizona property", category="work")
        results = mem.qsearch("arizona", limit=3)
        assert results[0]["content"] == "Arizona property"


class TestAegisFlowMemoryWithOmpa:
    @pytest.fixture
    def mem(self, tmp_path):
        m = AegisFlowMemory(vault_path=tmp_path, gbrain_vault_path=tmp_path / "gb")
        fake = MagicMock()
        fake.session_start.return_value = {"success": True}
        fake.stop.return_value = {"stopped": True}
        fake.get_routing_hint.return_value = "route:db"
        fake.kg_query.return_value = [{"s": "a"}]
        fake.get_stats.return_value = {"notes": 3}
        fake.rebuild_index.return_value = 5
        fake.sync.return_value = {"synced": True}
        fake.search.return_value = ["hit"]
        m._ompa = fake
        return m

    def test_lifecycle(self, mem):
        assert mem.session_start() == {"success": True}
        assert mem._session_started is True
        assert mem.stop() == {"stopped": True}
        assert mem._session_started is False
        mem.handle_message("m")
        mem.post_tool("write", {"file_path": "x"})
        mem._ompa.handle_message.assert_called_once_with("m")
        mem._ompa.post_tool.assert_called_once_with("write", {"file_path": "x"})

    def test_routing_search_kg_and_vault(self, mem):
        assert mem.get_routing_hint("db") == "route:db"
        mem.classify("x")
        mem._ompa.classify.assert_called_once_with("x")
        assert mem.search("q", limit=2, hybrid=False) == ["hit"]
        mem._ompa.search.assert_called_with("q", limit=2, hybrid=False)
        mem.kg_add("a", "rel", "b", valid_from="2026-01-01")
        mem._ompa.kg_add.assert_called_once_with("a", "rel", "b", valid_from="2026-01-01")
        assert mem.kg_query("a") == [{"s": "a"}]
        assert mem.get_stats() == {"notes": 3}
        mem.update_brain("note", "body", append=True)
        mem._ompa.update_brain.assert_called_once_with("note", "body", append=True)
        assert mem.rebuild_index() == 5
        assert mem.sync() == {"synced": True}

    def test_ompa_lazy_constructed(self, tmp_path, monkeypatch):
        created: Dict[str, Any] = {}

        class _Ompa:
            def __init__(self, **kwargs: Any) -> None:
                created.update(kwargs)

        monkeypatch.setitem(sys.modules, "ompa", MagicMock(Ompa=_Ompa))
        mem = AegisFlowMemory(vault_path=tmp_path, agent_name="bot", enable_semantic=False)
        assert isinstance(mem.ompa, _Ompa)
        assert mem.ompa is mem.ompa
        assert created == {
            "vault_path": str(tmp_path),
            "agent_name": "bot",
            "enable_semantic": False,
        }
