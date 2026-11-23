---
name: external-resource
description: "Orchestrate external compute and frontier AI assets: Google Flow batch asset generation (images, music, video), multi-account Gemini Pro Deep Research, Gemini Spark high-density reasoning, and ephemeral Cloud GPU/TPU deployments (Google Colab, Kaggle Dual-T4/TPU, Modal serverless) for custom 3D mesh, video, and audio pipelines."
---

# External Resource Orchestrator & Frontier AI Compute Engine

> **Step-0 Project Overlay**: Before executing, check if `<active-project>/.agents/skill_overlays/external-resource.md` exists (via `python .agents/skills/auto-skill/scripts/resolve_skill_overlay.py --project <root> --skill external-resource`).

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE**: Scripts in `scripts/` are executable software tools, NOT documentation. Never ask the user to run them or read them passively. Execute immediately via shell commands. When invoking Windows binaries from WSL, append `< /dev/null`.

---

## 1. Modality Routing Decision Matrix

| Asset / Task Modality | Target Infrastructure | Execution Tool / CLI | Safety & Cost Invariant |
|:---|:---|:---|:---|
| **2D Art, Sprites, Music, Video Loops** | **Google Flow Batch Studio** | Browser bridge (`127.0.0.1:9229`) | Max 1 active Flow tab; rotate account workspaces |
| **Deep Research & Grounded Specs** | **Gemini Pro Deep Research** | `search_engine.py deep-search` | High ROI: 1 alt run yields full 20+ source dossier |
| **Spark High-Density Reasoning** | **Google Spark Prompt Engine** | `synthesize_prompt.py` | Zero-token local generation of self-contained prompts |
| **Fast 3D Mesh / Serverless GPU** | **Modal Labs Serverless** | `modal run ...` | Scale-to-zero containers, pre-warmed weights ($30/mo free) |
| **Air-Gapped Batch GPU/TPU** | **Kaggle Notebooks** | `scripts/kaggle_gui_client.py` | 30 GPU-h/wk (Dual T4 30.7GB VRAM / TPU v3-8) |
| **Interactive Prototyping GPU** | **Google Colab (Pro/Free)** | Headless `colab exec` / UI | Rapid single-image to 3D model validation |

---

## 2. Resource Discipline & Execution Invariants

- **Google Flow Memory Invariant**: Enforce strictly **MAX 1 active tab** for Google Flow sessions to avoid host RAM exhaustion.
- **Trademark / Brand Filter**: Never include copyrighted IP names in prompt manifests. Rely on descriptive style prefixes configured via project overlays.
- **Artifact Isolation**: Downloaded ZIP archives and assets must be extracted into `<active-project>/temp_read/` or uploaded to Cloudflare R2 before project integration.

---

## 3. Core CLI Commands

```bash
# 1. Run batch asset manifest generator
python .agents/skills/external-resource/scripts/manifest_generator.py --spec temp_read/asset_spec.json

# 2. Check Kaggle GPU session status
python .agents/skills/external-resource/scripts/kaggle_gui_client.py status

# 3. Monitor Kaggle remote terminal logs
python .agents/skills/external-resource/scripts/kaggle_gui_client.py tail --lines 50

# 4. Deploy serverless 3D inference to Modal
modal run .agents/skills/external-resource/scripts/modal_mesh_worker.py --image input.png
```

---

## 4. References & Platform Guides

- [Flow Batch Studios & Ephemeral GPU Recipes](references/flow_and_gpu_recipes.md) — Detailed instructions for Flow manifests, TripoSR/InstantMesh, and Kaggle automation.
- [Platform Cheat Sheet](references/platform_cheat_sheet.md) — GPU instance limits, VRAM capacities, and credit allocation rules.
- [Manifest Templates](references/manifest_templates.md) — Reusable batch prompt manifest templates.
- [Flow Tool Registry JSON](references/flow_tool_registry.json) — Schema and tool definitions for Google Flow automation.