"""
Brain Doctor — health checker for AegisFlow brain (port from gbrain).

Runs filesystem-first checks (no DB required), then DB checks.
Computes a 0-100 health score across:
- resolver health (skills reachable)
- skill conformance (frontmatter valid)
- embedding coverage
- link integrity
- schema version
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class HealthStatus(str, Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class HealthIssue:
    type: str
    skill: str
    action: str
    severity: str = "warning"  # "error" or "warning"


@dataclass
class HealthCheck:
    name: str
    status: HealthStatus
    message: str
    issues: list[HealthIssue] = field(default_factory=list)

    @property
    def score_delta(self) -> int:
        if self.status == HealthStatus.FAIL:
            return -20
        if self.status == HealthStatus.WARN:
            return -5
        return 0


@dataclass
class BrainHealthReport:
    checks: list[HealthCheck]
    health_score: int

    def has_failures(self) -> bool:
        return any(c.status == HealthStatus.FAIL for c in self.checks)

    def has_warnings(self) -> bool:
        return any(c.status == HealthStatus.WARN for c in self.checks)

    def render(self) -> str:
        lines = [
            "# AegisFlow Brain Health Check",
            f"**Health score**: {self.health_score}/100",
            "",
        ]
        for check in self.checks:
            icon = "✅" if check.status == HealthStatus.OK else "⚠️" if check.status == HealthStatus.WARN else "❌"
            lines.append(f"{icon} **{check.name}**: {check.message}")
            for issue in check.issues:
                lines.append(f"   → {issue.severity.upper()}: {issue.skill}")
                lines.append(f"   ACTION: {issue.action}")
        lines.append("")
        if self.has_failures():
            lines.append("**Status**: Unhealthy — fix failures above")
        elif self.has_warnings():
            lines.append("**Status**: OK with warnings")
        else:
            lines.append("**Status**: All checks passed")
        return "\n".join(lines)


class BrainDoctor:
    """
    Filesystem-first brain health checker.

    Usage:
        doctor = BrainDoctor(skills_dir="/path/to/skills")
        report = doctor.run(json_output=False)
        print(report.render())
    """

    # Required frontmatter fields for skill conformance
    REQUIRED_FRONTMATTER = {"name", "description"}

    def __init__(self, skills_dir: str | Path, vault_path: str | Path | None = None):
        self.skills_dir = Path(skills_dir)
        self.vault_path = Path(vault_path) if vault_path else None
        self.issues_collected: list[HealthIssue] = []

    def run(self, json_output: bool = False) -> BrainHealthReport:
        checks: list[HealthCheck] = []

        # Always run filesystem checks
        checks.append(self._check_resolver_health())
        checks.append(self._check_skill_conformance())

        # Optional DB checks (if vault_path provided)
        if self.vault_path:
            checks.append(self._check_embedding_coverage())
            checks.append(self._check_link_integrity())
            checks.append(self._check_vault_structure())

        # Compute health score
        score = 100
        for check in checks:
            score += check.score_delta
        score = max(0, min(100, score))

        return BrainHealthReport(checks=checks, health_score=score)

    def _check_resolver_health(self) -> HealthCheck:
        """Check that RESOLVER.md exists and is readable."""
        resolver = self.skills_dir / "RESOLVER.md"
        if not resolver.exists():
            return HealthCheck(
                name="resolver_health",
                status=HealthStatus.WARN,
                message="RESOLVER.md not found — skill routing may not work",
                issues=[HealthIssue(
                    type="missing_resolver",
                    skill="RESOLVER.md",
                    action="Create skills/RESOLVER.md with skill routing table"
                )],
            )

        # Count skill references in resolver
        content = resolver.read_text()
        skill_refs = [line.strip() for line in content.split("\n") if "skills/" in line and ".md" in line]
        skill_count = len(set(skill_refs))

        if skill_count == 0:
            return HealthCheck(
                name="resolver_health",
                status=HealthStatus.WARN,
                message="No skills referenced in RESOLVER.md",
                issues=[HealthIssue(
                    type="empty_resolver",
                    skill="RESOLVER.md",
                    action="Add skill routing entries to RESOLVER.md"
                )],
            )

        return HealthCheck(
            name="resolver_health",
            status=HealthStatus.OK,
            message=f"{skill_count} skills routed via RESOLVER.md",
        )

    def _check_skill_conformance(self) -> HealthCheck:
        """Check that every skill has valid frontmatter."""
        if not self.skills_dir.exists():
            return HealthCheck(
                name="skill_conformance",
                status=HealthStatus.WARN,
                message="skills/ directory not found",
            )

        skill_dirs = [d for d in self.skills_dir.iterdir()
                      if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")]

        passing = 0
        failing: list[str] = []

        for skill_dir in skill_dirs:
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                # Try single-file skill
                skill_md = self.skills_dir / f"{skill_dir.name}.md"
                if not skill_md.exists():
                    failing.append(f"{skill_dir.name}: SKILL.md missing")
                    continue

            content = skill_md.read_text()
            if not content.startswith("---"):
                failing.append(f"{skill_dir.name}: no frontmatter")
                continue

            # Parse frontmatter
            parts = content.split("---")
            if len(parts) < 2:
                failing.append(f"{skill_dir.name}: malformed frontmatter")
                continue

            frontmatter = parts[1]
            for field_name in self.REQUIRED_FRONTMATTER:
                if field_name not in frontmatter:
                    failing.append(f"{skill_dir.name}: missing '{field_name}' in frontmatter")
                    continue
            passing += 1

        if failing:
            return HealthCheck(
                name="skill_conformance",
                status=HealthStatus.WARN,
                message=f"{passing}/{passing+len(failing)} skills pass. Failing: {', '.join(failing[:5])}",
                issues=[HealthIssue(
                    type="conformance_error",
                    skill=s,
                    action="Add required frontmatter (name, description) to SKILL.md"
                ) for s in failing[:5]],
            )

        return HealthCheck(
            name="skill_conformance",
            status=HealthStatus.OK,
            message=f"{passing}/{passing} skills conformant",
        )

    def _check_embedding_coverage(self) -> HealthCheck:
        """Check that vault has semantic embeddings."""
        if not self.vault_path:
            return HealthCheck(
                name="embeddings",
                status=HealthStatus.WARN,
                message="No vault_path provided — skipping embedding check",
            )

        index_path = self.vault_path / ".semantic_index.json"
        if not index_path.exists():
            return HealthCheck(
                name="embeddings",
                status=HealthStatus.WARN,
                message="No semantic index found — run SemanticMemory.build_index()",
                issues=[HealthIssue(
                    type="no_embeddings",
                    skill="SemanticMemory",
                    action="Call semantic.build_index() to generate embeddings for vault content"
                )],
            )

        import json
        try:
            with open(index_path) as f:
                index = json.load(f)
            count = len(index.get("vectors", []))
            if count == 0:
                return HealthCheck(
                    name="embeddings",
                    status=HealthStatus.WARN,
                    message="Embedding index empty — run semantic.build_index()",
                )
            return HealthCheck(
                name="embeddings",
                status=HealthStatus.OK,
                message=f"{count} embeddings indexed",
            )
        except Exception as e:
            return HealthCheck(
                name="embeddings",
                status=HealthStatus.WARN,
                message=f"Could not read embedding index: {e}",
            )

    def _check_link_integrity(self) -> HealthCheck:
        """Check for dead links in brain pages."""
        if not self.vault_path:
            return HealthCheck(
                name="link_integrity",
                status=HealthStatus.WARN,
                message="No vault_path provided — skipping link check",
            )

        dead_links: list[str] = []
        for md_file in self.vault_path.rglob("*.md"):
            content = md_file.read_text()
            for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", content):
                link = match.group(2)
                if link.startswith("http"):
                    continue  # Skip external links
                # Check internal links
                link_path = (md_file.parent / link).resolve()
                if not link_path.exists() and not self.vault_path / link.replace("#", "").split("?")[0].strip("/"):
                    dead_links.append(f"{md_file.name} → {link}")

        if dead_links:
            return HealthCheck(
                name="link_integrity",
                status=HealthStatus.WARN,
                message=f"{len(dead_links)} dead link(s) found",
                issues=[HealthIssue(
                    type="dead_link",
                    skill=link,
                    action=f"Fix or remove broken link in {md}"
                ) for md, link in [(d.split(" → ")[0], d.split(" → ")[1]) for d in dead_links[:5]]],
            )

        return HealthCheck(
            name="link_integrity",
            status=HealthStatus.OK,
            message="No dead links found",
        )

    def _check_vault_structure(self) -> HealthCheck:
        """Check that vault has expected directory structure."""
        if not self.vault_path:
            return HealthCheck(
                name="vault_structure",
                status=HealthStatus.WARN,
                message="No vault_path provided",
            )

        expected_dirs = ["people", "companies", "concepts", "originals", "work", "brain"]
        missing = [d for d in expected_dirs if not (self.vault_path / d).is_dir()]

        if missing:
            return HealthCheck(
                name="vault_structure",
                status=HealthStatus.WARN,
                message=f"Missing directories: {', '.join(missing)}",
                issues=[HealthIssue(
                    type="missing_directory",
                    skill=d,
                    action=f"Create vault/{d}/ directory for brain organization"
                ) for d in missing],
            )

        return HealthCheck(
            name="vault_structure",
            status=HealthStatus.OK,
            message="All expected directories present",
        )


def run_doctor(skills_dir: str, vault_path: str | None = None, json_output: bool = False) -> BrainHealthReport:
    doctor = BrainDoctor(skills_dir, vault_path)
    return doctor.run(json_output)
