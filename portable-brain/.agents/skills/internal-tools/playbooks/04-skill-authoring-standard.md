# Playbook 04: Custom Skill Authoring & Quality Standard

> **Authority on Skill Design, Branching-Hub Architecture, Token Budget Optimization, and Scope Isolation.**

---

## 1. Universal vs. Project-Specific Isolation Invariant

| Tier | Location | Scope & Rules |
|---|---|---|
| **Universal Skills** | `<BRAIN_ROOT>\.agents\skills/<skill-name>/` | • 100% project-agnostic powerhouses.<br>• Allowed to be invoked from ANY project.<br>• Exactly 12 master powerhouses. |
| **Project-Specific Skills** | `<project>/.agents/skills/<skill-name>/` | • Authorized ONLY within the active project workspace.<br>• Backup copy stored in `brain/project_skills/<project>/<skill-name>/`.<br>• NEVER placed in `brain/.agents/skills/`. |

---

## 2. The Branching-Hub Pattern (Preventing Skill Bloat)

> [!IMPORTANT]
> **The Antigravity Discovery Root Rule**:
> Antigravity indexes skills by scanning for `SKILL.md` files. Installing dozens of micro-skills clogs the system prompt with hundreds of redundant skill descriptions.
> **The Hub Architecture**: Consolidate capabilities into unified powerhouse skills:
> - All thinking & architecture $\rightarrow$ `deep-thinking`
> - All document manipulation $\rightarrow$ `document-forge`
> - All UI design & anti-slop $\rightarrow$ `ui-design-engine`
> - All search & crawling $\rightarrow$ `web-search-orchestrator`
> - All internal tool, MCP & extension authoring $\rightarrow$ `internal-tools`

---

## 3. Directory Layout & Critical Guardrails

```text
<skill-name>/
├── SKILL.md                 # Root router with YAML frontmatter (<120 lines)
├── playbooks/               # Detailed domain playbooks (read on demand via progressive disclosure)
├── templates/               # Reusable code scaffolds (named *.template to prevent indexing!)
└── scripts/                 # Executable CLI automation tools
```

### Critical Rules:
1. **The Single-`SKILL.md` Invariant**: Exactly **one** `SKILL.md` may exist at the root of the skill folder.
2. **Template File Naming**: Any template markdown files inside `templates/` MUST be named `SKILL.template.md` (NEVER `SKILL.md`), otherwise Antigravity will index the template as a broken live skill.
3. **Execution-First Mandate**: Every skill containing scripts MUST declare the Execution-First banner:
   ```markdown
   > [!IMPORTANT]
   > ⛔ **EXECUTION-FIRST MANDATE (ZERO-PASSIVE-READING)**:
   > Bundled scripts in `scripts/` are **executable software tools**, NOT reading material.
   > When this skill is triggered, **EXECUTE the relevant script immediately** via `run_command`.
   ```
4. **Deliverables Location**: All generated code, scripts, or outputs must go strictly to `<active-project>/temp_read/`. Never write project files to `brain/` root or foreign projects.
