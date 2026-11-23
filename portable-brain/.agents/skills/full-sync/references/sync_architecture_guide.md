# Full-Sync: Architecture, Vault Mirroring & Context Promotion Guide

Detailed guide to the 5 pillars of Full-Sync, Merkle tree hashing, and sovereign vault mirroring.

---

## 1. Synchronization Architecture

1. **Pillar 1: Bi-directional Skill Sync (`skill_reconciler.py`)**:
   - Compares skill contents via Merkle tree SHA-256 hashes (normalizing line endings).
   - Syncs project skills to Brain backups (`brain/project_skills/<project>/`).
   - Automatically triggers `auto-skill/scripts/sync_catalog.py`.
2. **Pillar 2: Universal Context Synthesis (`conversation_distiller.py` & `context_promoter.py`)**:
   - Parses session transcripts using incremental watermarks.
   - Extracts durable lessons, mistakes, constraints, and architecture ideas.
   - Promotes cross-project invariants to Central Brain root context files.
3. **Pillar 3: Sovereign Vault Mirroring (`sync_to_d_agentic.py`)**:
   - Mirrors all skills, context files, and project archives to `<AGENTIC_VAULT>`.
   - Never populates or pollutes `~/.gemini/` directories without explicit opt-in.
4. **Pillar 4: Autonomous Bootstrapper (`bootstrap_project.py`)**:
   - Hydrates new projects with local Hermes memory databases and agent rules.
5. **Pillar 5: Offload Message Boards**:
   - Ensures project-scoped `offload/` directories are initialized cleanly.

---

## 2. CLI Execution Examples

```bash
# Dry run sync to preview changes
python .agents/skills/full-sync/scripts/full_sync.py --project "<project_path>" --dry-run

# Full synchronization across all pillars
python .agents/skills/full-sync/scripts/full_sync.py --project "<project_path>"

# Distill conversation history into context updates
python .agents/skills/full-sync/scripts/conversation_distiller.py --project "<project_path>"
```
