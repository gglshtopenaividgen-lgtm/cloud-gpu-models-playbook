# Gemini Notebooks / NotebookLM Pro Project RAG Bucket Playbook

Automates `https://gemini.google.com/notebook/<UUID>` as a project-scoped RAG bucket via `argon_bridge/notebook_driver.py` over the local Argon Bridge (`http://127.0.0.1:9229/command`).

## Guardrails & Invariants
- **Profile Leasing**: Every browser operation acquires a surface-scoped lease (`surface="notebook"`, `bucket="notebooklm"`) via `profile_lock_manager.py`, isolating NotebookLM quota from `gemini_web_neon` and `aistudio_*`.
- **Popup Defense**: Runs `popup_healer.dismiss_blocking_popups(..., surface="notebook")` before UI interactions.
- **2-Layer Secret Redaction**:
  1. **Exact `.env*` Literal Scrubbing**: Loads values (`len >= 8`) in memory from `.env*` files under `--project` and replaces every occurrence with `[REDACTED_ENV_SECRET]`.
  2. **Regex Redaction**: Scrubs `sk-...`, `AIza...`, `Bearer ...`, `password`/`secret`/`api_key` assignments, and URL credentials.
- **300-Slot Discipline**: `pack` consolidates context (`mistakes.md`, `ideas.md`, `constraints.md`) and source files into `<= 12` Markdown bundles inside `<project>/temp_read/nb_bundles/`, leaving 280+ slots free for `discover-web`. Skips `.git`, `node_modules`, `.venv`, `__pycache__`, `.env*`, and binaries.
- **4 Neon High & Failover**: `query` enforces `4 Neon` High thinking in the notebook UI. On quota exhaustion, it marks `notebooklm` cooldown and emits `share-clone` failover guidance.

## CLI Workflow

```powershell
$DRV = "./.agents\skills\browser-operator\argon_bridge\notebook_driver.py"
$PROJ = "C:\path\to\project"

# 1. Scrub & pack repo/context into <= 12 Markdown bundles
python $DRV pack --project $PROJ --max-bundles 12

# 2. Create notebook & initialize <project>/temp_read/notebook_ledger.json
python $DRV create --title "Project RAG" --project $PROJ

# 3. Upload packed bundles via CDP DOM.setFileInputFiles
python $DRV add-sources --notebook <UUID> --bundles "$PROJ\temp_read\nb_bundles" --project $PROJ

# 4. Optional: add live web sources (280+ free slots remaining)
python $DRV discover-web --notebook <UUID> --query "Next.js 16 caching docs" --project $PROJ

# 5. Query with 4 Neon High thinking & harvest citations
python $DRV query --notebook <UUID> "Summarize architecture risks with citations" -o "$PROJ\temp_read\nb_answer.md" --project $PROJ

# 6. Share & clone to another Pro profile (verifies source_count parity)
python $DRV share-clone --notebook <UUID> --target-profile "Profile 13" --project $PROJ

# 7. Cleanup owner + all cloned notebooks and mark ledger DELETED
python $DRV cleanup --project $PROJ
# (or: python $DRV --cleanup-notebooks --project $PROJ)
```

## Ledger Schema (`<project>/temp_read/notebook_ledger.json`)
Each entry under `notebooks[<notebook_id>]` tracks:
- `notebook_id`, `url` (`https://gemini.google.com/notebook/<UUID>`), `notebooklm_url`
- `title`, `owner_profile`, `source_count`, `created_at`, `status` (`"ACTIVE"` | `"DELETED"`)
- `clones`: list of cloned notebook records (`notebook_id`, `url`, `profile`, `source_count`, `cloned_from`, `status`)
