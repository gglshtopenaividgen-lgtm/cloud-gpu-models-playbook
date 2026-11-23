---
name: offload
description: "Cross-instance Antigravity task offloading via per-project offload/ message boards, two-way Orchestrator to CLI Worker status bars, co-folder disambiguation, frictionless SKILL.md + auto-skill injection, and subagent/swarm delegation."
---

# Offload V3: Multi-Agent Collaboration Mesh & Task Offloading

> **Step-0 Project Overlay**: Before executing, check if `<active-project>/.agents/skill_overlays/offload.md` exists (via `python .agents/skills/auto-skill/scripts/resolve_skill_overlay.py --project <root> --skill offload`).

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE**: Scripts in `scripts/` are executable software tools, NOT documentation. Never ask the user to run them or read them passively. Execute immediately via shell commands. When invoking Windows binaries from WSL, append `< /dev/null`.

Offload V3 manages asynchronous task dispatching, peer-to-peer agent messaging, and worker orchestration across Antigravity IDE, CLI, and Codex instances.

---

## 1. Multi-Agent Roster Roles

- **`main-1`**: Lead Orchestrator. Decomposes tasks, dispatches to boards, reviews completions, arbitrates disputes.
- **`worker-1..N`**: Execution Workers. Auto-numbered (`worker-1`, `worker-2`, ...). Claim tasks, run verification tests, report deliverables.
- **`collab-1..N`**: Peer Collaborators. Engage in consultation, code review, and multi-model verification.

---

## 2. Co-Folder Disambiguation Invariant (CRITICAL)

Because Central Brain (`brain/`) is frequently attached as a co-folder in multi-root workspaces:
- **ALWAYS** pass `--project "<active_project>"` or `--workspaces "<ws1>;<ws2>"` on **EVERY** `offload_manager.py` command.
- **NEVER** trust relative `offload/BOARD.md` or dispatch tasks into `brain/offload/` unless Brain is the sole workspace.

---

## 3. Cross-Harness Skill Fallback (WSL CLI / Codex)

If a joining worker cannot use IDE slash commands:
1. Run `python .agents/skills/offload/scripts/offload_manager.py skills --project "<active_project>"` to print exact `SKILL.md` paths.
2. Read the canonical `SKILL.md` directly from `.agents/skills/<skill>/SKILL.md`.
3. Execute bundled scripts directly via shell commands. Path translation (`C:\...` <-> `/mnt/c/...`) is automatic.

---

## 4. Core CLI Commands

```bash
# 1. Worker listening loop (auto-numbered worker-1..N)
python .agents/skills/offload/scripts/offload_manager.py worker-listen --project "<active_project>" --role worker

# 2. Orchestrator task dispatch
python .agents/skills/offload/scripts/offload_manager.py dispatch --project "<active_project>" --title "<title>" --prompt-file "<file>" --from main-1 --to worker-2

# 3. Peer collaboration message post
python .agents/skills/offload/scripts/offload_manager.py post --project "<active_project>" --from collab-1 --to worker-2 --message "<note>"

# 4. Worker completion report
python .agents/skills/offload/scripts/offload_manager.py worker-complete --project "<active_project>" --task-id "<task_id>" --claim-id "<claim_id>" --agent-id "<id>" --summary-file "<report_path>"
```

---

## 5. References & Advanced Guides

- [Offload V3 Workflows & Roster Guide](references/offload_v3_guide.md) — Complete protocol documentation, message schemas, and status bar internals.
- [Git Worktree Protocol](references/git_worktree_protocol.md) — Isolated branch and worktree execution guide.