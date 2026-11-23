# External Resource: Flow Batch Studios & Ephemeral GPU Recipes

Detailed execution guides for Google Flow asset batching, 3D mesh synthesis, and ephemeral Cloud GPU/TPU deployments.

---

## 1. Google Flow Batch Asset Studio

- **Manifest Format**: Uses delimited batch manifests (`ID | Prompt | Style | Negative`).
- **Resource Discipline**: Enforce MAX 1 active browser tab for Google Flow to prevent memory pressure.
- **Family-Aware Generation**: Rotate character seeds or scene descriptors to maintain stylistic cohesion without trademarked brand terms.
- **CLI Automation**: Run `python3 scripts/flow_driver.py --manifest <file> --preset <game|characters|comics|scenes|video> [--modality image|video] [--concurrency 4] [--profile <Profile>] [--export] [--dry-run]` to dispatch automated batch runs with automatic lease acquisition, `postMessage` synchronization, and guaranteed tab cleanup.

---

## 2. Ephemeral Cloud GPU Environments

### Modal Serverless
- Pay-per-second serverless execution with `$30/mo` free tier.
- Best for single-image to 3D (TripoSR, InstantMesh), FLUX image synthesis, or audio inference.

### Kaggle GPU/TPU
- 30 GPU-hours/week (Dual Tesla T4) & TPU v3-8 in batch air-gapped mode.
- Use `scripts/kaggle_gui_client.py` for status and batch job monitoring.

### Google Colab Pro & Free
- Interactive prototyping and fast model validation with T4/L4/A100 instances.
