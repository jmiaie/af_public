"""
Tests for aegisflow.brain — BrainFirstLookup, SignalDetector, BrainDoctor.

All tests are offline (no LLM, no OMPA import required).
"""

from __future__ import annotations

from aegisflow.brain.doctor import (
    BrainDoctor,
    BrainHealthReport,
    HealthStatus,
)
from aegisflow.brain.lookup import BrainFirstLookup, brain_first
from aegisflow.brain.signal_detector import SignalDetector, SignalSummary

# ── BrainFirstLookup ────────────────────────────────────────────────────────


class TestBrainFirstLookup:
    def test_slugify(self):
        assert BrainFirstLookup._slugify("Jordan Chen") == "jordan-chen"
        assert BrainFirstLookup._slugify("MiCap AI!") == "micap-ai"

    def test_summarize_short(self):
        assert BrainFirstLookup._summarize("hello") == "hello"

    def test_summarize_long(self):
        content = "x" * 500
        result = BrainFirstLookup._summarize(content, max_chars=100)
        assert result.endswith("...")
        assert len(result) == 103  # 100 + "..."

    def test_lookup_returns_not_found_without_gbrain(self):
        lookup = BrainFirstLookup(memory=None, gbrain_vault_path=None)
        result = lookup.run("Nonexistent Entity")
        assert result.found is False

    def test_gbrain_file_hit(self, tmp_path):
        """Step 1: GBrain finds a markdown page."""
        people_dir = tmp_path / "people"
        people_dir.mkdir()
        (people_dir / "jordan-chen.md").write_text("# Jordan Chen\nCTO at MiCap.")

        lookup = BrainFirstLookup(memory=None, gbrain_vault_path=str(tmp_path))
        result = lookup.run("Jordan Chen")
        assert result.found is True
        assert result.source == "gbrain"
        assert "CTO" in result.page_content

    def test_brain_first_convenience(self, tmp_path):
        result = brain_first("Nobody", gbrain_vault_path=str(tmp_path))
        assert result.found is False

    def test_backlinks(self, tmp_path):
        people_dir = tmp_path / "people"
        people_dir.mkdir()
        (people_dir / "alpha.md").write_text("Links to bravo-team here.")
        (people_dir / "bravo-team.md").write_text("# Bravo Team")

        lookup = BrainFirstLookup(memory=None, gbrain_vault_path=str(tmp_path))
        backlinks = lookup._gbrain_backlinks("bravo-team")
        assert any("alpha.md" in b for b in backlinks)


# ── SignalDetector ───────────────────────────────────────────────────────────


class _StubVault:
    """Stub vault that records calls."""

    def __init__(self):
        self.stored = []

    def store_verbatim(self, content, category="work", filename="notes.md"):
        self.stored.append({"content": content, "category": category, "filename": filename})


class TestSignalDetector:
    def test_operational_skip(self):
        detector = SignalDetector(vault=_StubVault())
        summary = detector.detect("ok", is_operational=True)
        assert summary.skipped is True

    def test_short_message_skip(self):
        detector = SignalDetector(vault=_StubVault())
        summary = detector.detect("hi")
        assert summary.skipped is True

    def test_original_thinking_captured(self):
        vault = _StubVault()
        detector = SignalDetector(vault=vault)
        summary = detector.detect(
            "I think the AegisFlow memory system should use a temporal graph"
        )
        assert summary.ideas >= 1

    def test_company_extraction(self):
        detector = SignalDetector(vault=_StubVault())
        companies = detector._extract_companies("We should partner with NVIDIA and Google on this")
        assert "NVIDIA" in companies or "Google" in companies

    def test_person_extraction(self):
        detector = SignalDetector(vault=_StubVault())
        people = detector._extract_people("Talk to Jordan Chen about this")
        assert any("Jordan Chen" in p for p in people)

    def test_log_summary_formatting(self):
        detector = SignalDetector(vault=_StubVault())
        summary = SignalSummary(ideas=2, entities=1, idea_paths=["originals/x.md"])
        log = detector.log_summary(summary)
        assert "2 ideas" in log
        assert "1 entities" in log


# ── BrainDoctor ──────────────────────────────────────────────────────────────


class TestBrainDoctor:
    def test_missing_skills_dir(self, tmp_path):
        doctor = BrainDoctor(skills_dir=tmp_path / "nonexistent")
        report = doctor.run()
        assert isinstance(report, BrainHealthReport)
        assert report.health_score <= 100

    def test_empty_skills_dir(self, tmp_path):
        skills = tmp_path / "skills"
        skills.mkdir()
        doctor = BrainDoctor(skills_dir=skills)
        report = doctor.run()
        # Should warn about no RESOLVER.md
        assert any(c.name == "resolver_health" for c in report.checks)

    def test_resolver_present(self, tmp_path):
        skills = tmp_path / "skills"
        skills.mkdir()
        (skills / "RESOLVER.md").write_text("- skills/example.md\n")
        doctor = BrainDoctor(skills_dir=skills)
        report = doctor.run()
        resolver_check = next(c for c in report.checks if c.name == "resolver_health")
        assert resolver_check.status == HealthStatus.OK

    def test_report_render(self, tmp_path):
        doctor = BrainDoctor(skills_dir=tmp_path)
        report = doctor.run()
        rendered = report.render()
        assert "Health score" in rendered
        assert "AegisFlow" in rendered

    def test_vault_structure_check(self, tmp_path):
        skills = tmp_path / "skills"
        skills.mkdir()
        vault = tmp_path / "vault"
        vault.mkdir()
        doctor = BrainDoctor(skills_dir=skills, vault_path=vault)
        report = doctor.run()
        # Should warn about missing directories (people, companies, etc.)
        structure_check = next(
            (c for c in report.checks if c.name == "vault_structure"), None
        )
        assert structure_check is not None
        assert structure_check.status == HealthStatus.WARN
