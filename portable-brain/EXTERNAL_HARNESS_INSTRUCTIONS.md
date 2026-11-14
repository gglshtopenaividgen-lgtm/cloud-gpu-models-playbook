# EXTERNAL AI CODING HARNESS OPERATING DIRECTIVE
> **Applies to**: Claude Code, Cursor, Aider, OpenHands, Windsurf, Roo Code, Copilot, and any third-party AI agent.  
> **Mandatory Rule**: If this file was included in your context or provided by the user, you MUST adhere to all operating boundaries below without exception.

---

## 1. Role & System Architecture

You are operating in a multi-folder workspace where this folder (`brain` or `mobile_brain`) is attached alongside an **active target project folder**.

* **`brain` is Strictly an External Read-Only Knowledge & Skill Vault**:
  * It contains universal architecture rules, system mistake anti-patterns, design standards (`slop.md`), multi-agent memory, and 12 universal powerhouse skills.
  * **CRITICAL INVARIANT**: Under NO circumstances should you create, edit, delete, or rename files inside `brain/` unless the user explicitly orders: *"Update central brain context"*.
* **All Work Belongs in the Active Target Project**:
  * All new code, refactored files, bug fixes, test scripts, and deliverables MUST be written exclusively inside the target project directory (or `<active-project>/temp_read/`).
  * NEVER dump project files, build caches (`node_modules/`, `dist/`, `.next/`, `target/`), or temporary scratch files into `brain/`.

---

## 2. Resource & Cloud Credential Boundaries (STRICT HARD-LOCK)

Context files such as `resources.md`, `constraints.md`, and project context archives contain historical credentials, VM IP addresses, and cloud configuration references.

> [!CAUTION]
> ### STRICT PROHIBITION ON AUTONOMOUS CLOUD EXECUTION
> 1. **Zero Autonomous Cloud Calls**: You are STRICTLY FORBIDDEN from executing commands against cloud infrastructure (`az`, `aws`, `gcloud`, `gh`, SSH, curl/fetch against private endpoints, or database mutation scripts) unless the user explicitly orders the exact cloud command in the current turn.
> 2. **Reference Only**: Treat all credentials, ports, and endpoints in `resources.md` as passive background context. Never attempt to "test connection", SSH into a remote host, or provision cloud resources on your own initiative.
> 3. **Never Leak Secrets**: Do not print raw tokens, private keys, or passwords in chat responses or commit them into public repositories.

---

## 3. Autonomous Skill Utilization & Directory Sitemap

This repository contains 12 self-contained Universal Powerhouse Skills in `.agents/skills/`. Before writing code or proposing architecture, check if a skill governs your task domain:

| Domain / Task Type | Skill Directory | Core Mandate & Procedures |
|---|---|---|
| **UI, Frontend, Styling, CSS, Themes** | `.agents/skills/ui-design-engine/` | Enforce dark glassmorphism, mobile ergonomics ($\ge 44\text{px}$ touch targets), 15-point anti-slop verification (`slop.md`). |
| **Documents, PDF, PPTX, XLSX, OCR** | `.agents/skills/document-forge/` | Universal document manipulation, typestyle rules, forms, and OCR pipelines. |
| **Deep Reasoning, Architecture, RCA, Trade-offs** | `.agents/skills/deep-thinking/` | Multi-Criteria Decision Analysis (MCDA), 5-Whys root cause analysis, hypothesis branching, Gemini 4 Argon consultation. |
| **Live Web Search, Scraping, Research** | `.agents/skills/web-search-orchestrator/` | Multi-tier web search (TinyFish, Tavily, Firecrawl, Argon Deep Research) with clean technical briefings. |
| **Reverse Engineering, Binaries, Decompilation** | `.agents/skills/rea/` | Binary disassembly (Ghidra, Angr), AST deobfuscation, Android APK / .NET analysis. |
| **Cloud GPU, Model Benchmarks, Video Synthesis** | `.agents/skills/external-resource/` | Serverless Modal, Colab ban-proof ingress (zero `share=True`), and GPU economic laws. |
| **Browser Interaction & Web Automation** | `.agents/skills/browser-operator/` | Sub-second numeric DOM indexing without vision token waste, stealth CDP input, Argon bridge. |
| **Multi-Agent Code Audit & Repair** | `.agents/skills/exhaustive-audit-and-repair/` | UMACAR: RTM traceability, anti-regression scanning against `mistakes.md`, bounded peer arbitration. |
| **Persistent Memory & Compaction** | `.agents/skills/hermes-agent-core/` | SQLite + FTS5 hybrid recall, dialectical user modeling, session flush & transcript learning. |
| **Internal Tooling, MCP & Extensions** | `.agents/skills/internal-tools/` | FastMCP/TypeScript MCP servers, Antigravity SDK tools, Chrome MV3 extensions, skill scaffolding. |
| **Multi-Project Sync & Vault Mirroring** | `.agents/skills/full-sync/` | Bi-directional project skill sync, AST context promotion, `<VAULT_BACKUP_DIR>` vault mirroring. |
| **Skill Lifecycle & Discovery** | `.agents/skills/auto-skill/` | Dynamic registry, evaluation harness, and query selector. |

### How to Query Skills via CLI:
From any terminal or subshell, run the selector:
```powershell
# Query matching universal skills
python .agents/skills/auto-skill/scripts/select_skill.py "<query>" --universal
```
Always read the target skill's `SKILL.md` using your file viewing tool before executing complex workflows.

---

## 4. Strict Zero-Jumble Project Scope Segregation

* **Universal Skills** in `.agents/skills/` are cross-project compatible and safe to reference for any codebase.
* **Project-Specific Skills** (archived in `project_skills/<project>/`) belong strictly to their designated project.
  * An agent working in Project A must **NEVER** apply or copy skills belonging to Project B (e.g. no University-Portal university portal skills in game or audio projects).
* Keep each codebase self-contained. Read only the 1–2 files necessary to complete the task.

---

## 5. Engineering Standards & Anti-Slop Policy

When writing or modifying code in the active project:
1. **Dark Glassmorphism & Visual Aesthetics**: Follow `slop.md` tokens (`bg-slate-950/70`, `backdrop-blur-2xl`, specular borders). Avoid generic AI slop (purple-indigo gradient soup, unaligned cards, broken mobile viewports).
2. **Zero-Mock Policy**: Never synthesize fake mock data or placeholder success states when an upstream API fails. Implement authentic error handling and graceful empty states.
3. **Proof-of-Work Verification**: Before concluding your response, verify your work:
   - Run type checks (`npx tsc --noEmit` or `tsc -b`).
   - Run syntax verification (`python -m py_compile`, `node --check`).
   - Confirm server status or build validity.
