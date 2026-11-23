# Offload V3: Multi-Agent Roster & Workflows Guide

Comprehensive manual for the Offload V3 multi-agent collaboration mesh, peer messaging bus, and task lifecycle.

---

## 1. Roster Topology & Roles

- **`main-1`**: Orchestrator / Lead Agent. Owns task decomposition, dispatching, arbitration, and final delivery.
- **`worker-1..N`**: Execution agents. Claim specific tasks, run verification tests, report progress, and submit completions.
- **`collab-1..N`**: Peer collaborators. Engage in consultation, code review, and cross-model validation.

---

## 2. Task Lifecycle Protocol

1. **Dispatch**: `main-1` dispatches task to `offload/tasks/TASK-<id>.json` with complete instructions and context links.
2. **Listen & Claim**: Worker listens via `worker-listen`, claims task atomically, and updates `status.json`.
3. **Execution**: Worker performs work, runs unit tests, and compiles deliverables.
4. **Clarification**: If blocked, worker calls `worker-ask --wait` to consult `main-1`.
5. **Completion**: Worker writes deliverable to `<project>/temp_read/result_<task_id>.md` and calls `worker-complete --claim-id <id>`.

---

## 3. Co-Folder Workspace Disambiguation Invariant

When Central Brain is attached as a co-folder in IDE workspaces (`<project>` + `brain`), always pass `--project <project_path>` or `--workspaces "<ws1>;<ws2>"` to ensure commands target the active project board rather than Central Brain.
