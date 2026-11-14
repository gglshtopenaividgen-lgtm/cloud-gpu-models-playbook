#!/usr/bin/env python3
"""
Unit Tests for Exhaustive Audit & Repair (UMACAR):
- GitDiffAnalyzer (Hunk chunking, semantic classification, risk scoring)
- BoundedArbitrationBus (Deadlock prevention, 3-round arbitration cap)
- AntiRegressionEngine (Detection of historical failures from mistakes.md)
- RequirementTraceabilityEngine (RTM extraction, historical milestone filtering)
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from audit_orchestrator import (
    GitDiffAnalyzer,
    BoundedArbitrationBus,
    AntiRegressionEngine,
    RequirementTraceabilityEngine,
    AuditFinding,
    FindingCategory,
    Severity,
    DiffHunk,
)


class TestGitDiffAnalyzer(unittest.TestCase):
    def test_parse_unified_diff_and_classification(self):
        sample_diff = """diff --git a/services/auth.ts b/services/auth.ts
--- a/services/auth.ts
+++ b/services/auth.ts
@@ -10,4 +10,6 @@ export interface UserSession {
+  api_key: string;
+  password_hash: string;
+  id: string;
"""
        hunks = GitDiffAnalyzer.parse_unified_diff(sample_diff)
        self.assertEqual(len(hunks), 1)
        hunk = hunks[0]
        self.assertEqual(hunk.file_path, "services/auth.ts")
        self.assertEqual(hunk.semantic_classification, "SECURITY_RISK")
        self.assertGreater(hunk.risk_score, 2.0)


class TestBoundedArbitrationBus(unittest.TestCase):
    def test_arbitration_cap_and_ruling(self):
        bus = BoundedArbitrationBus(conversation_id="test_audit")
        finding = AuditFinding(
            id="FIND-001",
            category=FindingCategory.CODE_SMELL,
            severity=Severity.LOW,
            title="Potential Minor Inefficiency",
            description="Consider using a set lookup instead of list scan.",
            file_path="utils.py",
            line_start=15,
            line_end=15,
            confidence=0.6,
        )

        decision, rationale = bus.force_orchestrator_ruling(finding)
        self.assertEqual(decision, "DISMISSED_LOW_CONFIDENCE")
        self.assertEqual(finding.status, "DISMISSED_LOW_CONFIDENCE")


class TestAntiRegressionEngine(unittest.TestCase):
    def test_scan_for_defective_subagent(self):
        engine = AntiRegressionEngine()
        hunk = DiffHunk(
            file_path="orchestrator.py",
            old_start=1,
            old_length=5,
            new_start=1,
            new_length=5,
            hunk_header="@@ -1,5 +1,5 @@",
            added_lines=["invoke_subagent(TypeName='DeepCoder', Role='Coder')"],
        )
        findings = engine.scan_diff_and_files(Path("."), [hunk])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, FindingCategory.REGRESSION_MISTAKE)
        self.assertEqual(findings[0].severity, Severity.CRITICAL)


class TestRequirementTraceabilityEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ideas_file = Path(self.temp_dir.name) / "ideas.md"
        content = """# Central Master Ideas

## 1. Universal Multi-Project Architectural Invariants
1. **The 5-Tier Cloud Cost & Free-Tier Guardrail**:
   - Supabase 500MB DB Limit, Azure Postgres Standard_B1ms.

## 3. Historical System-Wide Architectural Decisions
- **2026-09-25 (Unconventional Hardware Testing Mandate)**: Private GPU tiers reserved.
- **2026-08-20 (Cloudflare Edge LLM Relay)**: Anycast relay deployed.

## [HI Synced: 2026-09-03]
### 🚀 Tier 1: TPU Max
"""
        self.ideas_file.write_text(content, encoding="utf-8")
        self.rtm = RequirementTraceabilityEngine(Path(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_filter_historical_decisions_and_foreign_sync(self):
        atoms = self.rtm.extract_requirements_from_markdown(self.ideas_file)
        titles = [a.title for a in atoms]
        
        # Invariants should be extracted
        self.assertIn("The 5-Tier Cloud Cost & Free-Tier Guardrail", titles)
        
        # Historical date entries should be filtered out
        for t in titles:
            self.assertFalse(t.startswith("2026-"), f"Historical date {t} was not filtered out!")
            self.assertNotIn("TPU Max", t, "Foreign project sync header was not filtered out!")


if __name__ == "__main__":
    unittest.main()
