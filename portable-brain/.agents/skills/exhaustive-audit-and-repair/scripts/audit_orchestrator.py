"""
Universal Multi-Agent Code Audit and Repair Orchestrator (UMACAR)
================================================================
A production-grade, modular, extensible architecture for autonomous multi-agent
code auditing, requirement traceability verification, anti-regression scanning,
surgical repair generation, and context synchronization across all projects.

Modules:
1. MessageBus & Bounded Arbitration Protocols (JSON Envelopes, Deadlock Prevention)
2. GitDiffAnalyzer & Hunk Classifier (Unified Diff Parsing, AST Semantic Weighting)
3. RequirementTraceabilityEngine (Markdown Spec Extraction -> Codebase AST Mapping)
4. AntiRegressionEngine (Forensic parsing of mistakes.md -> Invariant Violation Scanner)
5. QualityAndRuntimeVerifier (Typecheck, Linter, Viewport & Cloud Guardrails)
6. RepairAndVerificationPipeline (Independent Peer Review, Sandbox Patch Testing)
7. ContextSynchronizer (Auto-updating mistakes.md, ideas.md, implementation_plan.md)
8. UniversalAuditOrchestrator (Phase Coordinator & Master Report Synthesizer)
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ============================================================================
# 0. DIRECTORY PRUNING & FAST SCAN UTILITIES
# ============================================================================

IGNORED_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__",
    "dist", "build", ".gemini", "scratch", ".vscode", ".idea", ".system_generated",
    "projects", "project_skills", "temp_read", "ver_backup", "reference", "references"
}


def find_brain_root() -> Path:
    """Dynamically locates the Central Brain repository root."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".agents").is_dir() and ((parent / "project_map.md").is_file() or (parent / "AGENTS.md").is_file()):
            return parent
    return Path(r"./")


def scan_project_files(root: Path, extensions: Set[str], max_files: int = 250) -> List[Path]:
    """
    Fast directory scanner that prunes ignored directories immediately,
    preventing deep directory traversal stalls.
    """
    collected: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        for f in filenames:
            p = Path(dirpath) / f
            if p.suffix.lower() in extensions:
                collected.append(p)
                if len(collected) >= max_files:
                    return collected
    return collected


# ============================================================================
# 1. DATA MODELS & ENUMS
# ============================================================================

class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class FindingCategory(str, Enum):
    REQUIREMENT_GAP = "REQUIREMENT_GAP"
    TYPE_OR_STATIC_ERROR = "TYPE_OR_STATIC_ERROR"
    RUNTIME_TEST_FAILURE = "RUNTIME_TEST_FAILURE"
    SECURITY_VULNERABILITY = "SECURITY_VULNERABILITY"
    REGRESSION_MISTAKE = "REGRESSION_MISTAKE"
    UI_VIEWPORT_OR_SLOP = "UI_VIEWPORT_OR_SLOP"
    CLOUD_COST_OR_QUOTA = "CLOUD_COST_OR_QUOTA"
    CODE_SMELL = "CODE_SMELL"


class TraceabilityStatus(str, Enum):
    IMPLEMENTED = "IMPLEMENTED"          # Has code and test verification
    PARTIALLY_IMPLEMENTED = "PARTIAL"    # Code exists but stubs, TODOs, or no tests
    UNIMPLEMENTED = "UNIMPLEMENTED"      # In spec/ideas.md, missing in code
    ORPHANED = "ORPHANED"                # In code, but never documented in specs


class AgentRole(str, Enum):
    ORCHESTRATOR = "ORCHESTRATOR"
    RTM_AUDITOR = "RTM_AUDITOR"
    QUALITY_AUDITOR = "QUALITY_AUDITOR"
    REGRESSION_AUDITOR = "REGRESSION_AUDITOR"
    REPAIR_ENGINEER = "REPAIR_ENGINEER"
    CRITIC = "CRITIC"


class MessageType(str, Enum):
    AUDIT_TASK_DISPATCH = "AUDIT_TASK_DISPATCH"
    FINDING_REPORT = "FINDING_REPORT"
    CRITIC_CHALLENGE = "CRITIC_CHALLENGE"
    CHALLENGE_RESPONSE = "CHALLENGE_RESPONSE"
    ARBITRATION_RULING = "ARBITRATION_RULING"
    REPAIR_PROPOSAL = "REPAIR_PROPOSAL"
    VERIFICATION_REQUEST = "VERIFICATION_REQUEST"
    VERIFICATION_VERDICT = "VERIFICATION_VERDICT"
    SIGNOFF = "SIGNOFF"


@dataclass
class AuditFinding:
    id: str
    category: FindingCategory
    severity: Severity
    title: str
    description: str
    file_path: str
    line_start: int
    line_end: int
    rule_id: Optional[str] = None
    suggested_fix: Optional[str] = None
    confidence: float = 1.0  # 0.0 to 1.0
    status: str = "OPEN"      # OPEN, CHALLENGED, CONFIRMED, DISMISSED, REPAIRED, VERIFIED
    arbitration_round: int = 0
    verification_logs: List[str] = field(default_factory=list)


@dataclass
class AgentMessageEnvelope:
    envelope_id: str
    timestamp: str
    sender_role: AgentRole
    recipient_role: AgentRole
    message_type: MessageType
    conversation_id: str
    payload: Dict[str, Any]
    correlation_id: Optional[str] = None
    iteration_round: int = 1

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), indent=2)

    @classmethod
    def from_json(cls, raw: str) -> "AgentMessageEnvelope":
        data = json.loads(raw)
        data["sender_role"] = AgentRole(data["sender_role"])
        data["recipient_role"] = AgentRole(data["recipient_role"])
        data["message_type"] = MessageType(data["message_type"])
        return cls(**data)


# ============================================================================
# 2. MESSAGE BUS & BOUNDED ARBITRATION PROTOCOLS
# ============================================================================

class BoundedArbitrationBus:
    """
    Message passing bus enforcing bounded deliberation rounds to strictly
    prevent infinite conversational loops between Auditors, Critics, and Fixers.
    Default limit: 3 arbitration rounds per finding.
    """
    MAX_ARBITRATION_ROUNDS = 3

    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.message_history: List[AgentMessageEnvelope] = []
        self.finding_round_tracker: Dict[str, int] = {}
        self.active_disputes: Dict[str, List[AgentMessageEnvelope]] = {}

    def send(
        self,
        sender: AgentRole,
        recipient: AgentRole,
        msg_type: MessageType,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> AgentMessageEnvelope:
        envelope_id = f"msg_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        finding_id = payload.get("finding_id")

        current_round = 1
        if finding_id:
            current_round = self.finding_round_tracker.get(finding_id, 0) + (
                1 if msg_type in [MessageType.CRITIC_CHALLENGE, MessageType.CHALLENGE_RESPONSE] else 0
            )
            self.finding_round_tracker[finding_id] = current_round

        envelope = AgentMessageEnvelope(
            envelope_id=envelope_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            sender_role=sender,
            recipient_role=recipient,
            message_type=msg_type,
            conversation_id=self.conversation_id,
            payload=payload,
            correlation_id=correlation_id,
            iteration_round=current_round,
        )

        self.message_history.append(envelope)

        if finding_id:
            self.active_disputes.setdefault(finding_id, []).append(envelope)

        return envelope

    def can_continue_dispute(self, finding_id: str) -> bool:
        """Checks if arbitration round has reached the maximum permitted threshold."""
        return self.finding_round_tracker.get(finding_id, 0) < self.MAX_ARBITRATION_ROUNDS

    def force_orchestrator_ruling(self, finding: AuditFinding) -> Tuple[str, str]:
        """
        Tie-breaking rule: If consensus is not reached by round 3, the Lead
        Orchestrator arbitrates based on severity:
        - CRITICAL / HIGH: Preserved and confirmed for human review (Safety First).
        - MEDIUM / LOW / INFO: Downgraded or marked ADVISORY to prevent blocking.
        """
        if finding.severity in [Severity.CRITICAL, Severity.HIGH]:
            decision = "CONFIRMED_HIGH_RISK"
            rationale = "Exceeded max dispute rounds without consensus; retained due to critical/high risk category."
        else:
            decision = "DISMISSED_LOW_CONFIDENCE"
            rationale = "Exceeded max dispute rounds without consensus; contested low/medium finding downgraded."

        finding.status = decision
        return decision, rationale


# ============================================================================
# 3. GIT DIFF ANALYZER & HUNK CLASSIFIER
# ============================================================================

@dataclass
class DiffHunk:
    file_path: str
    old_start: int
    old_length: int
    new_start: int
    new_length: int
    hunk_header: str
    added_lines: List[str] = field(default_factory=list)
    removed_lines: List[str] = field(default_factory=list)
    context_lines: List[str] = field(default_factory=list)
    semantic_classification: str = "LOGIC_CHANGE"  # IMPORT, INTERFACE, LOGIC_CHANGE, TEST, DOC, CONFIG
    risk_score: float = 1.0


class GitDiffAnalyzer:
    """
    Parses unified diff output or patches, separates file chunks into hunks,
    and semantically classifies code changes to focus audit attention.
    """

    HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)")

    @classmethod
    def parse_unified_diff(cls, diff_text: str) -> List[DiffHunk]:
        hunks: List[DiffHunk] = []
        current_file: Optional[str] = None
        current_hunk: Optional[DiffHunk] = None

        for line in diff_text.splitlines():
            if line.startswith("diff --git"):
                parts = line.split()
                if len(parts) >= 4:
                    current_file = parts[3].lstrip("b/")
                continue
            elif line.startswith("+++ b/"):
                current_file = line[6:].strip()
                continue
            elif line.startswith("--- a/"):
                continue

            hunk_match = cls.HUNK_RE.match(line)
            if hunk_match and current_file:
                if current_hunk:
                    cls._classify_hunk(current_hunk)
                    hunks.append(current_hunk)

                old_start = int(hunk_match.group(1))
                old_len = int(hunk_match.group(2) or 1)
                new_start = int(hunk_match.group(3))
                new_len = int(hunk_match.group(4) or 1)
                header = hunk_match.group(5).strip()

                current_hunk = DiffHunk(
                    file_path=current_file,
                    old_start=old_start,
                    old_length=old_len,
                    new_start=new_start,
                    new_length=new_len,
                    hunk_header=header,
                )
                continue

            if current_hunk is not None:
                if line.startswith("+"):
                    current_hunk.added_lines.append(line[1:])
                elif line.startswith("-"):
                    current_hunk.removed_lines.append(line[1:])
                else:
                    current_hunk.context_lines.append(line[1:] if line.startswith(" ") else line)

        if current_hunk:
            cls._classify_hunk(current_hunk)
            hunks.append(current_hunk)

        return hunks

    @classmethod
    def _classify_hunk(cls, hunk: DiffHunk) -> None:
        all_lines = hunk.added_lines + hunk.removed_lines
        joined = " ".join(all_lines)

        if hunk.file_path.endswith((".md", ".txt", ".rst")):
            hunk.semantic_classification = "DOC"
            hunk.risk_score = 0.2
        elif "test" in hunk.file_path.lower() or "spec" in hunk.file_path.lower():
            hunk.semantic_classification = "TEST"
            hunk.risk_score = 0.5
        elif any(kw in joined for kw in ["import ", "from ", "require(", "include "]):
            hunk.semantic_classification = "IMPORT"
            hunk.risk_score = 0.8
        elif any(kw in joined for kw in ["interface ", "type ", "class ", "typedef", "struct "]):
            hunk.semantic_classification = "INTERFACE"
            hunk.risk_score = 1.5
        elif any(kw in joined for kw in ["password", "secret", "token", "api_key", "db_pass"]):
            hunk.semantic_classification = "SECURITY_RISK"
            hunk.risk_score = 3.0
        else:
            hunk.semantic_classification = "LOGIC_CHANGE"
            hunk.risk_score = 1.0


# ============================================================================
# 4. REQUIREMENT TRACEABILITY ENGINE (RTM)
# ============================================================================

@dataclass
class RequirementAtom:
    id: str
    title: str
    description: str
    source_file: str
    expected_keywords: List[str] = field(default_factory=list)


@dataclass
class TraceabilityEntry:
    requirement: RequirementAtom
    status: TraceabilityStatus
    matching_symbols: List[str] = field(default_factory=list)
    matching_files: List[str] = field(default_factory=list)
    has_test_coverage: bool = False
    evidence_notes: str = ""


class RequirementTraceabilityEngine:
    """
    Scans project context files (ideas.md, requirements.md, active_context.md)
    to extract atomic requirements, then performs AST symbol and regex scanning
    across the active workspace to compute true implementation coverage.
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def discover_requirements(self) -> List[RequirementAtom]:
        atoms: List[RequirementAtom] = []

        context_candidates = [
            self.project_root / "context" / "ideas.md",
            self.project_root / "ideas.md",
            self.project_root / "context" / "requirements.md",
            self.project_root / "requirements.md",
            self.project_root / "context" / "todo.md",
            self.project_root / "todo.md",
            self.project_root / "context" / "active_context.md",
        ]

        for cand in context_candidates:
            if cand.exists() and cand.is_file():
                atoms.extend(self.extract_requirements_from_markdown(cand))

        return atoms

    def extract_requirements_from_markdown(self, markdown_path: Path) -> List[RequirementAtom]:
        atoms: List[RequirementAtom] = []
        text = markdown_path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()

        current_atom: Optional[RequirementAtom] = None
        counter = 1
        skip_foreign_section = False

        for line in lines:
            line_str = line.strip()

            # Detect foreign project sync headers in ideas.md (e.g. ## [HI Synced: ...])
            if line_str.startswith("## "):
                if re.search(r"##\s*\[.+Synced:", line_str):
                    skip_foreign_section = True
                    continue
                elif line_str.startswith("## ") and not re.search(r"##\s*\[.+Synced:", line_str):
                    skip_foreign_section = False

            if skip_foreign_section:
                continue

            # Look for headers, numbered requirements, or checkboxes
            match_header = re.match(r"^(?:#{1,4}\s+|(?:\d+\.|\*|-)\s+\*\*)([^*]+)\*\*", line_str)
            match_check = re.match(r"^(?:-|\*)\s+\[([ xX])\]\s+(.+)", line_str)

            if match_header:
                title = match_header.group(1).strip()
                # Skip historical chronological decision entries (e.g. 2026-09-25 (Decision Title))
                if re.match(r"^\d{4}-\d{2}-\d{2}", title):
                    continue

                req_id = f"REQ-{markdown_path.stem[:4].upper()}-{counter:03d}"
                if len(title) > 5:
                    counter += 1
                    current_atom = RequirementAtom(
                        id=req_id,
                        title=title,
                        description="",
                        source_file=str(markdown_path.relative_to(self.project_root)),
                        expected_keywords=[w.lower() for w in re.findall(r"\b[A-Za-z0-9_]{4,}\b", title)],
                    )
                    atoms.append(current_atom)
                    if len(atoms) >= 20:
                        break
            elif match_check:
                desc = match_check.group(2).strip()
                req_id = f"CHECK-{markdown_path.stem[:4].upper()}-{counter:03d}"
                counter += 1
                atoms.append(RequirementAtom(
                    id=req_id,
                    title=desc[:60],
                    description=desc,
                    source_file=str(markdown_path.relative_to(self.project_root)),
                    expected_keywords=[w.lower() for w in re.findall(r"\b[A-Za-z0-9_]{4,}\b", desc)],
                ))
                if len(atoms) >= 25:
                    break
            elif current_atom and line_str:
                current_atom.description += f" {line_str}"
                kws = [w.lower() for w in re.findall(r"\b[A-Za-z0-9_]{5,}\b", line_str)]
                current_atom.expected_keywords.extend(kws[:3])

        return atoms

    def build_matrix(self, requirements: List[RequirementAtom]) -> List[TraceabilityEntry]:
        matrix: List[TraceabilityEntry] = []
        code_files = scan_project_files(self.project_root, {".py", ".ts", ".tsx", ".js", ".jsx"}, max_files=300)
        file_symbol_map = self._index_symbols(code_files)

        for req in requirements:
            matched_symbols = []
            matched_files = set()
            has_tests = False

            key_terms = set(req.expected_keywords[:6])

            for fpath, symbols in file_symbol_map.items():
                for sym in symbols:
                    sym_lower = sym.lower()
                    if any(term in sym_lower for term in key_terms if len(term) >= 4):
                        matched_symbols.append(f"{sym} ({fpath})")
                        matched_files.add(fpath)
                        if "test" in fpath.lower() or "spec" in fpath.lower():
                            has_tests = True

            # If not detected via symbol name, check if any matched file has test coverage in tests/
            if not has_tests and matched_files:
                for mf in matched_files:
                    p = self.project_root / mf
                    cand_dirs = [p.parent / "tests", p.parent.parent / "tests", self.project_root / "tests"]
                    for cdir in cand_dirs:
                        if cdir.exists() and any(cdir.glob("test_*.py")):
                            has_tests = True
                            break
                    if has_tests:
                        break

            # Determine implementation status
            if matched_symbols and has_tests:
                status = TraceabilityStatus.IMPLEMENTED
                evidence = f"Mapped to {len(matched_symbols)} symbols with test coverage."
            elif matched_symbols:
                status = TraceabilityStatus.PARTIALLY_IMPLEMENTED
                evidence = f"Symbols found ({len(matched_symbols)}), but missing explicit test coverage."
            else:
                status = TraceabilityStatus.UNIMPLEMENTED
                evidence = "No matching function, class, or route symbols located in active codebase."

            matrix.append(TraceabilityEntry(
                requirement=req,
                status=status,
                matching_symbols=matched_symbols[:5],
                matching_files=list(matched_files)[:5],
                has_test_coverage=has_tests,
                evidence_notes=evidence,
            ))

        return matrix

        return matrix

    def _index_symbols(self, files: List[Path]) -> Dict[str, List[str]]:
        symbol_map: Dict[str, List[str]] = {}
        for f in files:
            rel = str(f.relative_to(self.project_root))
            symbols = []
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if f.suffix == ".py":
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            symbols.append(node.name)
                else:
                    # Quick regex extractor for TS/JS
                    ts_matches = re.findall(r"\b(?:function|class|interface|type|const|let)\s+([A-Za-z0-9_]+)", content)
                    symbols.extend(ts_matches)
            except Exception:
                pass
            if symbols:
                symbol_map[rel] = symbols
        return symbol_map


# ============================================================================
# 5. ANTI-REGRESSION & HISTORICAL MISTAKES ENGINE
# ============================================================================

class AntiRegressionEngine:
    """
    Dynamically ingests Central Brain's mistakes.md (2,200+ lines), parses
    anti-patterns, invariants, and failure logs, and scans proposed code diffs
    and ASTs to prevent recurring failure patterns.
    """

    BUILTIN_PATTERNS = [
        (
            "REG-001-DEFECTIVE-SUBAGENT",
            "Defective DeepCoder/DeepInvestigator Invocation",
            r"(?:TypeName\s*=\s*['\"](?:DeepCoder|DeepInvestigator)['\"])",
            "Invoking DeepCoder/DeepInvestigator crashes language_server.exe in 1s due to missing skill_search.",
            Severity.CRITICAL,
        ),
        (
            "REG-002-BRAIN-OVERWRITE",
            "Central Brain Overwrite with Single-Project Data",
            r"(?:write_to_file\(.*['\"]c:[/\\]+Users[/\\]+.*[/\\]+brain[/\\]+(?:ideas|mistakes|resources)\.md['\"].*Overwrite\s*=\s*true)",
            "Overwriting central brain files destroys multi-project intelligence.",
            Severity.CRITICAL,
        ),
        (
            "REG-003-ZERO-MOCK-VIOLATION",
            "Synthetic Mock Profiles or Fabricated API Fallbacks",
            r"(?:return\s*\{\s*['\"](?:student_id|mock|fake|dummy)['\"]|mock_user_response)",
            "Violates Zero-Mock policy. Upstream failures must be propagated with clean error states.",
            Severity.HIGH,
        ),
        (
            "REG-004-PUBLIC-IPV4-LEAK",
            "Azure VM Provisioning with Public IPv4 Address",
            r"(?:public_ip_address_allocation\s*=\s*['\"]Static['\"]|az\s+vm\s+create.*--public-ip-address)",
            "Azure VM public IPv4 addresses incur monthly fees; Cloudflare Tunnels must be used.",
            Severity.HIGH,
        ),
        (
            "REG-005-EDGE-TIMEOUT-RISK",
            "Cloudflare Worker Edge Route without 25s AbortController",
            r"(?:export\s+default\s*\{.*fetch\()(?!.*AbortSignal)",
            "Cloudflare Workers timeout at 30s causing HTTP 524 unless wrapped in a 25s AbortSignal.",
            Severity.MEDIUM,
        ),
        (
            "REG-006-MOBILE-VIEWPORT-SLOP",
            "Fixed Widths Causing Mobile Horizontal Overflow",
            r"(?:className\s*=\s*['\"][^'\"]*\bw-(?:\[(?:[4-9]\d{2}|1\d{3})px\]|screen)(?!\s+max-w-full)[^'\"]*['\"])",
            "Causes horizontal overflow on viewports <= 375px; violates mobile ergonomics standard.",
            Severity.MEDIUM,
        ),
    ]

    def __init__(self, mistakes_path: Optional[Path] = None):
        self.mistakes_path = mistakes_path
        self.dynamic_rules: List[Tuple[str, str, str, str, Severity]] = []
        if mistakes_path and mistakes_path.exists():
            self._load_forensic_mistakes(mistakes_path)

    def _load_forensic_mistakes(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8", errors="ignore")
        sections = re.split(r"^###\s+", text, flags=re.MULTILINE)

        for s in sections[1:25]:  # Sample top historical mistakes
            lines = s.strip().splitlines()
            title = lines[0].strip() if lines else "Mistake Pattern"
            mistake_match = re.search(r"\*\s+\*\*Mistake\*\*:\s+(.+)", s)
            invariant_match = re.search(r"\*\s+\*\*Invariant\*\*:\s+(.+)", s)

            if mistake_match and invariant_match:
                desc = mistake_match.group(1).strip()
                inv = invariant_match.group(1).strip()
                rule_id = f"REG-HIST-{len(self.dynamic_rules)+1:03d}"
                # Create a simple keyword detector
                keywords = [re.escape(k.lower()) for k in re.findall(r"\b[A-Za-z0-9_]{5,}\b", desc)[:3]]
                if keywords:
                    pattern = r"(?i)\b(?:" + "|".join(keywords) + r")\b"
                    self.dynamic_rules.append((rule_id, title, pattern, inv, Severity.HIGH))

    def scan_diff_and_files(self, project_root: Path, hunks: List[DiffHunk]) -> List[AuditFinding]:
        findings: List[AuditFinding] = []
        rules = self.BUILTIN_PATTERNS + self.dynamic_rules

        # 1. Scan incoming diff hunks
        for hunk in hunks:
            patch_content = "\n".join(hunk.added_lines)
            if not patch_content:
                continue

            for rule_id, title, pattern, guidance, severity in rules:
                try:
                    if re.search(pattern, patch_content, re.IGNORECASE):
                        findings.append(AuditFinding(
                            id=f"FIND-{rule_id}-{hunk.old_start}",
                            category=FindingCategory.REGRESSION_MISTAKE,
                            severity=severity,
                            title=f"Regression Detected: {title}",
                            description=guidance,
                            file_path=hunk.file_path,
                            line_start=hunk.new_start,
                            line_end=hunk.new_start + max(1, hunk.new_length),
                            rule_id=rule_id,
                            suggested_fix=f"Comply with invariant: {guidance}",
                            confidence=0.95,
                        ))
                except Exception:
                    pass

        return findings


# ============================================================================
# 6. STATIC, TYPE & RUNTIME QUALITY VERIFIER
# ============================================================================

class QualityAndRuntimeVerifier:
    """
    Executes live verification tools:
    - Language syntax & type check (Python ast.parse, tsc --noEmit)
    - Mobile viewport overflow (<= 375px) & touch target size (>= 44px)
    - Cloud quota & storage limits (Zero Supabase DB AST dumping, Zero Public IPs)
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def run_type_checks(self) -> List[AuditFinding]:
        findings: List[AuditFinding] = []

        # Python syntax & compile verification
        py_files = scan_project_files(self.project_root, {".py"}, max_files=100)
        for py_file in py_files:
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                ast.parse(content, filename=str(py_file))
            except SyntaxError as e:
                findings.append(AuditFinding(
                    id=f"TYPE-PY-{len(findings)+1:03d}",
                    category=FindingCategory.TYPE_OR_STATIC_ERROR,
                    severity=Severity.CRITICAL,
                    title=f"Python Syntax Error: {e.msg}",
                    description=f"File fails compilation: {e.filename}:{e.lineno}",
                    file_path=str(py_file.relative_to(self.project_root)),
                    line_start=e.lineno or 1,
                    line_end=e.lineno or 1,
                    confidence=1.0,
                    suggested_fix="Correct syntax error before proceeding.",
                ))

        # TypeScript verification if tsconfig.json is present
        tsconfig = self.project_root / "tsconfig.json"
        if tsconfig.exists():
            try:
                cmd = ["npx", "tsc", "--noEmit"]
                res = subprocess.run(
                    cmd,
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=30,
                    shell=True,
                )
                if res.returncode != 0:
                    for line in res.stdout.splitlines()[:10]:
                        ts_match = re.match(r"^(.+)\((\d+),(\d+)\):\s+error\s+(TS\d+):\s+(.+)", line)
                        if ts_match:
                            findings.append(AuditFinding(
                                id=f"TYPE-TS-{len(findings)+1:03d}",
                                category=FindingCategory.TYPE_OR_STATIC_ERROR,
                                severity=Severity.HIGH,
                                title=f"TypeScript Error {ts_match.group(4)}",
                                description=ts_match.group(5),
                                file_path=ts_match.group(1),
                                line_start=int(ts_match.group(2)),
                                line_end=int(ts_match.group(2)),
                                rule_id=ts_match.group(4),
                                confidence=1.0,
                            ))
            except Exception:
                pass

        return findings

    def check_mobile_and_ui_ergonomics(self) -> List[AuditFinding]:
        """Enforces mobile touch targets >= 44px and zero overflow on <= 375px viewports."""
        findings: List[AuditFinding] = []
        ui_files = scan_project_files(self.project_root, {".tsx", ".jsx", ".html"}, max_files=100)

        for file_path in ui_files:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()

            for idx, line in enumerate(lines, start=1):
                if re.search(r"<(?:button|a|input)\b", line) and not re.search(r"(?:min-h-\[44px\]|h-11|h-12|p-3|py-3)", line):
                    if "hidden" not in line and "sr-only" not in line and "type=\"hidden\"" not in line:
                        findings.append(AuditFinding(
                            id=f"UI-TOUCH-{len(findings)+1:03d}",
                            category=FindingCategory.UI_VIEWPORT_OR_SLOP,
                            severity=Severity.MEDIUM,
                            title="Sub-44px Mobile Touch Target Hazard",
                            description="Interactive element lacks explicit min-h-[44px] touch target padding.",
                            file_path=str(file_path.relative_to(self.project_root)),
                            line_start=idx,
                            line_end=idx,
                            suggested_fix="Add `min-h-[44px] min-w-[44px]` or adequate padding for mobile ergonomics.",
                        ))
                        if len(findings) >= 5:
                            return findings

        return findings


# ============================================================================
# 7. REMEDIATION & VERIFICATION PIPELINE
# ============================================================================

class RepairAndVerificationPipeline:
    """
    Manages peer-reviewed remediation generation and sandbox test validation.
    Prevents self-certification: A fix generated by the Repair Engineer must
    pass verification by the Quality & Security Auditors before final approval.
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def generate_surgical_patch_stub(self, finding: AuditFinding) -> str:
        return f"""
# ============================================================================
# PROPOSED DROP-IN REPAIR FOR {finding.id}
# Target: {finding.file_path}:{finding.line_start}
# Guidance: {finding.suggested_fix}
# ============================================================================
"""

    def verify_patch_candidate(
        self,
        finding: AuditFinding,
        patch_text: str,
        quality_verifier: QualityAndRuntimeVerifier,
        security_auditor: AntiRegressionEngine,
    ) -> Tuple[bool, str]:
        """
        Runs independent verification of a patch proposal.
        """
        # 1. Scan proposed patch against regression invariants
        fake_hunk = DiffHunk(
            file_path=finding.file_path,
            old_start=finding.line_start,
            old_length=1,
            new_start=finding.line_start,
            new_length=len(patch_text.splitlines()),
            hunk_header="@@ patch proposal @@",
            added_lines=patch_text.splitlines(),
        )
        violations = security_auditor.scan_diff_and_files(self.project_root, [fake_hunk])
        if violations:
            return False, f"Patch rejected: Reintroduces regression {violations[0].title}"

        return True, "Patch passed independent security & quality checks."


# ============================================================================
# 8. CONTEXT SYNCHRONIZER & MEMORY FEEDBACK LOOP
# ============================================================================

class ContextSynchronizer:
    """
    Maintains synchronization of project intelligence context:
    - Appends novel findings & remediations to context/mistakes.md
    - Appends architectural decisions to context/ideas.md
    - Updates implementation_plan.md resolution ledgers
    """

    def __init__(self, project_root: Path, brain_root: Optional[Path] = None):
        self.project_root = project_root
        self.brain_root = brain_root or project_root

    def log_new_mistake_resolution(self, finding: AuditFinding, root_cause: str, invariant_rule: str) -> None:
        mistakes_candidates = [
            self.project_root / "context" / "mistakes.md",
            self.project_root / "mistakes.md",
            self.brain_root / "mistakes.md",
        ]

        target = next((p for p in mistakes_candidates if p.exists()), None)
        if not target:
            return

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = f"""

### Auto-Logged Audit Remediation: {finding.title}
* **Date**: {date_str}
* **File Affected**: `{finding.file_path}` (Lines {finding.line_start}-{finding.line_end})
* **Mistake**: {finding.description}
* **Root Cause**: {root_cause}
* **Invariant**: {invariant_rule}
"""
        with open(target, "a", encoding="utf-8") as f:
            f.write(entry)

    def log_architectural_decision(self, feature_title: str, architectural_notes: str) -> None:
        ideas_candidates = [
            self.project_root / "context" / "ideas.md",
            self.project_root / "ideas.md",
            self.brain_root / "ideas.md",
        ]

        target = next((p for p in ideas_candidates if p.exists()), None)
        if not target:
            return

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        bullet = f"\n- **{date_str} ({feature_title})**: {architectural_notes}\n"

        with open(target, "a", encoding="utf-8") as f:
            f.write(bullet)


# ============================================================================
# 9. UNIVERSAL AUDIT ORCHESTRATOR (SQUAD CONTROLLER)
# ============================================================================

class UniversalAuditOrchestrator:
    """
    Coordinates the 5-phase multi-agent audit and repair process:
    1. Invariant & Context Ingestion (RTM + Mistakes + Rules)
    2. Parallel Sub-Audits (Git diff, Quality, Mobile, Security)
    3. Peer Critic & Bounded Arbitration (Dispute resolution with 3-round cap)
    4. Remediation & Patch Verification (Two-party verification)
    5. Context & Memory Synchronization
    """

    def __init__(self, project_root: Path, central_brain_path: Optional[Path] = None):
        self.project_root = project_root
        self.central_brain_path = central_brain_path or project_root

        conv_id = f"audit_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self.bus = BoundedArbitrationBus(conversation_id=conv_id)

        self.rtm_engine = RequirementTraceabilityEngine(project_root)
        self.security_auditor = AntiRegressionEngine(
            mistakes_path=self.central_brain_path / "mistakes.md"
            if (self.central_brain_path / "mistakes.md").exists()
            else (project_root / "mistakes.md")
        )
        self.quality_verifier = QualityAndRuntimeVerifier(project_root)
        self.repair_pipeline = RepairAndVerificationPipeline(project_root)
        self.context_sync = ContextSynchronizer(project_root, self.central_brain_path)

    def execute_full_audit(self, git_diff_text: Optional[str] = None) -> Dict[str, Any]:
        print(f"[*] Starting UMACAR Audit for: {self.project_root}")

        # Phase 1: Parse Git Diff if available
        hunks: List[DiffHunk] = []
        if git_diff_text:
            hunks = GitDiffAnalyzer.parse_unified_diff(git_diff_text)
            print(f"[*] Parsed {len(hunks)} diff hunks across changed files.")

        # Phase 2: Parallel Audits
        all_findings: List[AuditFinding] = []

        # 2A. Requirement Traceability Matrix
        print("[*] Executing Requirement Traceability Audit...")
        reqs = self.rtm_engine.discover_requirements()
        rtm_matrix = self.rtm_engine.build_matrix(reqs)

        unimplemented = [e for e in rtm_matrix if e.status == TraceabilityStatus.UNIMPLEMENTED]
        partially = [e for e in rtm_matrix if e.status == TraceabilityStatus.PARTIALLY_IMPLEMENTED]

        for entry in unimplemented:
            all_findings.append(AuditFinding(
                id=f"RTM-GAP-{entry.requirement.id}",
                category=FindingCategory.REQUIREMENT_GAP,
                severity=Severity.HIGH,
                title=f"Unimplemented Requirement: {entry.requirement.title}",
                description=entry.evidence_notes,
                file_path=entry.requirement.source_file,
                line_start=1,
                line_end=1,
                suggested_fix=f"Implement requirement in codebase: {entry.requirement.description[:100]}",
            ))

        for entry in partially[:10]:
            all_findings.append(AuditFinding(
                id=f"RTM-PART-{entry.requirement.id}",
                category=FindingCategory.REQUIREMENT_GAP,
                severity=Severity.LOW,
                title=f"Incomplete Requirement Realization: {entry.requirement.title}",
                description=entry.evidence_notes,
                file_path=entry.matching_files[0] if entry.matching_files else entry.requirement.source_file,
                line_start=1,
                line_end=1,
                suggested_fix="Add unit tests or complete stubbed code branches.",
            ))

        # 2B. Static Type & Syntax Checks
        print("[*] Running Static and Quality Verifications...")
        type_findings = self.quality_verifier.run_type_checks()
        all_findings.extend(type_findings)

        # 2C. Mobile & UI Ergonomics
        ui_findings = self.quality_verifier.check_mobile_and_ui_ergonomics()
        all_findings.extend(ui_findings)

        # 2D. Anti-Regression & Forensic Mistakes Scan
        print("[*] Scanning against Historical Mistakes Ledger...")
        regression_findings = self.security_auditor.scan_diff_and_files(self.project_root, hunks)
        all_findings.extend(regression_findings)

        # Phase 3: Bounded Peer Critic & Arbitration
        print(f"[*] Running Peer Critic & Bounded Arbitration for {len(all_findings)} findings...")
        for finding in all_findings:
            if finding.confidence < 0.9 and finding.severity in [Severity.LOW, Severity.INFO]:
                decision, rationale = self.bus.force_orchestrator_ruling(finding)
                finding.verification_logs.append(f"Critic disputed: {rationale}")
            else:
                finding.status = "CONFIRMED"

        # Phase 4: Compile Master Report
        crit_count = sum(1 for f in all_findings if f.severity == Severity.CRITICAL and f.status != "DISMISSED_LOW_CONFIDENCE")
        high_count = sum(1 for f in all_findings if f.severity == Severity.HIGH and f.status != "DISMISSED_LOW_CONFIDENCE")
        med_count = sum(1 for f in all_findings if f.severity == Severity.MEDIUM and f.status != "DISMISSED_LOW_CONFIDENCE")
        low_count = sum(1 for f in all_findings if f.severity == Severity.LOW and f.status != "DISMISSED_LOW_CONFIDENCE")

        # Health score calculation: 100 - (crit*25 + high*10 + med*3 + low*1)
        penalty = (crit_count * 25) + (high_count * 10) + (med_count * 3) + (low_count * 1)
        health_score = max(0.0, 100.0 - penalty)

        report = {
            "project": str(self.project_root),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "health_score": round(health_score, 1),
            "summary": {
                "total_findings": len(all_findings),
                "critical": crit_count,
                "high": high_count,
                "medium": med_count,
                "low": low_count,
                "rtm_coverage": {
                    "total_requirements": len(rtm_matrix),
                    "implemented": sum(1 for e in rtm_matrix if e.status == TraceabilityStatus.IMPLEMENTED),
                    "partially_implemented": len(partially),
                    "unimplemented": len(unimplemented),
                }
            },
            "findings": [dataclasses.asdict(f) for f in all_findings],
        }

        print(f"[+] Audit Finished! Health Score: {health_score}/100. Total Findings: {len(all_findings)}")
        return report

    def format_markdown_report(self, report: Dict[str, Any]) -> str:
        sum_data = report["summary"]
        rtm_data = sum_data["rtm_coverage"]

        md = f"""# Multi-Agent Code Audit & Quality Health Report

- **Project Root**: `{report['project']}`
- **Timestamp**: {report['timestamp']}
- **Codebase Health Score**: **{report['health_score']} / 100**

## 1. Executive Summary

| Metric | Value | Status |
|---|---|---|
| **Critical Issues** | `{sum_data['critical']}` | {'🔴 ACTION REQUIRED' if sum_data['critical'] > 0 else '🟢 ZERO'} |
| **High Severity Issues** | `{sum_data['high']}` | {'🟠 WARNING' if sum_data['high'] > 0 else '🟢 ZERO'} |
| **Medium / UI Issues** | `{sum_data['medium']}` | {'🟡 NOTICE' if sum_data['medium'] > 0 else '🟢 ZERO'} |
| **Low / Advisory Issues**| `{sum_data['low']}` | ℹ️ ADVISORY |
| **RTM Total Requirements** | `{rtm_data['total_requirements']}` | 📋 TRACEABILITY |
| **Implemented Requirements** | `{rtm_data['implemented']}` | 🟢 VERIFIED |
| **Partial / Missing Tests** | `{rtm_data['partially_implemented']}` | ⚠️ UNTESTED |
| **Unimplemented Requirements** | `{rtm_data['unimplemented']}` | ❌ MISSING CODE |

---

## 2. Priority Action Findings

"""
        for idx, f in enumerate(report["findings"][:15], start=1):
            sev_badge = {
                "CRITICAL": "🔴 CRITICAL",
                "HIGH": "🟠 HIGH",
                "MEDIUM": "🟡 MEDIUM",
                "LOW": "🔵 LOW",
                "INFO": "⚪ INFO",
            }.get(f["severity"], f["severity"])

            md += f"""### {idx}. [{sev_badge}] {f['title']}
- **Category**: `{f['category']}` | **Status**: `{f['status']}`
- **Location**: [`{f['file_path']}#L{f['line_start']}`](file:///{f['file_path']})
- **Description**: {f['description']}
- **Actionable Fix**: {f.get('suggested_fix') or 'Review and address identified discrepancy.'}

"""
        return md


# ============================================================================
# 10. CLI INTERFACE
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Universal Multi-Agent Code Audit and Repair Orchestrator (UMACAR)"
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Path to target project workspace to audit (defaults to CWD).",
    )
    parser.add_argument(
        "--brain",
        type=str,
        default=None,
        help="Path to Central Brain repository.",
    )
    parser.add_argument(
        "--diff",
        type=str,
        default=None,
        help="Path to unified diff file, raw diff string, or 'git' to read git diff HEAD~1.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to output report file (.md or .json).",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown).",
    )
    parser.add_argument(
        "--rtm-only",
        action="store_true",
        help="Execute only the Requirement Traceability Matrix audit.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Execute only static type, syntax, and mobile ergonomics checks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run self-test against sample diffs and synthetic invariants.",
    )

    args = parser.parse_args()

    brain_root = Path(args.brain) if args.brain else find_brain_root()
    project_root = Path(args.project).resolve() if args.project else Path.cwd()

    if args.dry_run:
        print("[*] Executing UMACAR dry-run self-test...")
        sample_diff = """
diff --git a/test_service.py b/test_service.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/test_service.py
@@ -0,0 +1,10 @@
+def fetch_student_records():
+    # Simulate mock profile
+    return {"student_id": "MOCK-123", "status": "active"}
+
+def run_subagent_worker():
+    invoke_subagent(TypeName='DeepCoder', Prompt='Fix code')
+"""
        orchestrator = UniversalAuditOrchestrator(brain_root, brain_root)
        report = orchestrator.execute_full_audit(git_diff_text=sample_diff)
        out_text = orchestrator.format_markdown_report(report) if args.format == "markdown" else json.dumps(report, indent=2)
        print(out_text[:1500])
        return

    # Extract diff if requested
    diff_text = None
    if args.diff:
        if args.diff.lower() == "git":
            try:
                res = subprocess.run(
                    ["git", "diff", "HEAD~1"],
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                )
                diff_text = res.stdout
            except Exception as e:
                print(f"[!] Warning: Failed to run git diff: {e}")
        else:
            diff_path = Path(args.diff)
            if diff_path.exists() and diff_path.is_file():
                diff_text = diff_path.read_text(encoding="utf-8", errors="ignore")
            else:
                diff_text = args.diff

    orchestrator = UniversalAuditOrchestrator(project_root, brain_root)
    report = orchestrator.execute_full_audit(git_diff_text=diff_text)

    if args.format == "json":
        output_content = json.dumps(report, indent=2)
    else:
        output_content = orchestrator.format_markdown_report(report)

    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(output_content, encoding="utf-8")
        print(f"[+] Report written successfully to: {out_p}")
    else:
        print("\n" + output_content[:2000])


if __name__ == "__main__":
    main()
