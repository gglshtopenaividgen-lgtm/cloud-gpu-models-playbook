# Exhaustive Audit & Repair: Deep Audit Playbook & RTM Protocol

Comprehensive operational playbook for the Universal Multi-Agent Code Audit & Architectural Repair System (UMACAR).

---

## 1. Requirement Traceability Matrix (RTM) Protocol

1. **Extraction**: Parse user prompt, `ideas.md`, `requirements.md`, and task specs into discrete atomic requirements `REQ-001`, `REQ-002`, ...
2. **Code Mapping**: For each requirement, map symbol references, functions, types, and UI components.
3. **Status Classification**:
   - `FULL`: Complete implementation with verified tests.
   - `PARTIAL`: Incomplete implementation or stubbed functions.
   - `MISSING`: No implementation detected in codebase AST.
   - `REGRESSION`: Previously working code broken by recent edits.

---

## 2. Anti-Regression Scanning Against `mistakes.md`

- Every audit run scans modified diff hunks against patterns recorded in Central Brain's `mistakes.md`.
- Flag common traps: unhandled exceptions, dangling subprocess handles, missing `< /dev/null` on Windows binaries from WSL, unconstrained database queries, or unverified type assumptions.

---

## 3. CLI Runner Recipes

Execute the automated audit runner:
```bash
python .agents/skills/exhaustive-audit-and-repair/scripts/audit_orchestrator.py \
  --project "<project_path>" \
  --mode "full" \
  --out temp_read/audit_report.md
```
