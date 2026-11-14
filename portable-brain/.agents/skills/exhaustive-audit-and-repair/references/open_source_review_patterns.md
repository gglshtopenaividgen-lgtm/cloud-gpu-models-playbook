# Open-Source Code Review & Audit Architectural Patterns

> **Synthesized Intelligence from CodeRabbit, Qodo PR-Agent, Open-Code-Review, ast-grep, Semgrep, and Aider.**

---

## 1. Executive Taxonomy of AI Code Review Architectures

| Dimension | Naive LLM Review | Modern Hybrid Engine (CodeRabbit/PR-Agent) | UMACAR Multi-Agent Squad |
|---|---|---|---|
| **Input Ingestion** | Raw git diff dumped into single prompt | Asymmetric AST context + Token-budgeted hunk chunking | Context-Aware Hunk Parsing + RTM Spec Ingestion |
| **Static Verification** | Zero (hallucinates types and imports) | Sandboxed linters (Ruff, Biome, ast-grep) | Multi-Language Compiler (`tsc`, `ast.parse`, linters) |
| **Security & Regressions** | Generic advice ("sanitize inputs") | Semgrep OWASP rulesets | Dynamic Forensic Ledger (`mistakes.md` AST scan) |
| **Requirement Verification** | None (evaluates syntax only) | None (evaluates PR description vs diff only) | **Requirement Traceability Matrix (RTM)** across specs |
| **Remediation** | Advisory comments only | GitHub Suggestion blocks | **Two-Party Verified Drop-In Replacement Patches** |
| **Deliberation Topology** | Single-shot prompt | Single-call per command (`/review`, `/improve`) | **Bounded Multi-Agent Arbitration (Orchestrator + Critic)** |

---

## 2. Key Architectural Invariants Adopted from Top Frameworks

### A. Asymmetric Diff Context & Hunk Chunking (from Qodo PR-Agent)
- **Problem**: Passing large diffs causes context degradation, truncating critical enclosing scopes.
- **Solution**:
  - Auto-exclude lockfiles, minified bundles, and generated code (`*.generated.*`, `*.d.ts`).
  - Scan upward from modified hunks to capture the enclosing function or class header (`async function processPayment(...)`), giving the model scope awareness.
  - Partition massive PRs (>500 lines) into logical file clusters, run parallel audits, and run an aggregation/deduplication pass.

### B. Structural AST Filtering without Token Burn (from `ast-grep` & Semgrep)
- **Problem**: LLMs cost tokens and latency for deterministic checks.
- **Solution**:
  - Run regex and AST scans locally (0 tokens, sub-second execution).
  - Target known anti-patterns (e.g. `DeepCoder` invocations, zero-mock violations, missing timeouts on Cloudflare Workers, hardcoded secrets).
  - Only feed ambiguous or complex architectural findings to LLM reasoning subagents.

### C. Tree-Sitter Repo-Map & Symbol Indexing (from Aider `repomap.py`)
- **Problem**: The auditor needs whole-codebase awareness without ingesting the entire codebase.
- **Solution**:
  - Index function signatures, class interfaces, and exported types across all project files.
  - When reviewing a diff, automatically extract the signatures of all referenced callers and types.

### D. Multi-Persona Critic & Debate Protocol (from Spencer Marx's `open-code-review`)
- **Problem**: Single agents suffer from confirmation bias and self-certify flawed code.
- **Solution**:
  - Decompose into distinct personas:
    - *Security Auditor*: Focuses strictly on OWASP Top 10, secrets, injection, and authorization.
    - *Quality / Performance Auditor*: Focuses on type accuracy, memory leaks, N+1 queries, mobile viewports.
    - *Requirement Traceability Auditor*: Compares user request vs code AST.
    - *Peer Critic*: Actively challenges high-false-positive findings.
  - Bounded to 3 rounds of structured debate, arbitrated by the Lead Orchestrator.

### E. Two-Party Verification before Patch Application (from Aider Self-Correction)
- **Problem**: Fixer agents generate patches that fail compilation.
- **Solution**:
  - Propose patch $\rightarrow$ Apply to temporary buffer $\rightarrow$ Execute `npx tsc --noEmit` or `python -m py_compile` $\rightarrow$ Feed compiler `stderr` back if failed $\rightarrow$ Only sign off when 0 errors occur.
