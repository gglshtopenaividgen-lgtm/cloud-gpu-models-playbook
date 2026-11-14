# Universal Cloud GPU & Notebook Guardrails Reference

> **Forensic Guardrails Against Platform Bans, Disk Starvation, Socket Conflicts, and Failed Notebook Runs**  
> **Source**: `<BRAIN_ROOT>\.agents\skills\external-resource\references\cloud_gpu_guardrails.md`

---

## 1. Platform Hardware & Storage Truth Table

Before downloading a single byte or importing a framework, know the physical constraints:

| Platform | Accelerator & VRAM | Host RAM | Scratch Disk Capacity | Strict Output Limit | Primary Network Policy |
|:---|:---|:---|:---|:---|:---|
| **Kaggle GPU** | 2x Tesla T4 (30.72 GB total • 15.36 GB each) | 30.0 GB | **`/tmp/` (57.6+ GB to 1 TB)** | **`/kaggle/working/` (19.52 GB strict!)** | 🛑 **ZERO TUNNELS**. No `cloudflared`, `ngrok`, `share=True`. |
| **Kaggle CPU** | 4-vCPU Fair-Share (0 GPU Quota) | 30.0 GB | **`/tmp/` (57.6+ GB)** | **`/kaggle/working/` (19.52 GB strict!)** | 🛑 **ZERO TUNNELS**. Dedicated Storage Vault & AVX2 C++ inference. |
| **Colab Free** | 1x Tesla T4 (15.36 GB VRAM) | 12.7 GB (+ swap) | **`/tmp/` & `/content/` (~70-100 GB)** | Session ephemeral | ⚠️ **IN-NOTEBOOK ONLY**. Use `serve_kernel_port_as_iframe` / `share=False`. |
| **Colab Pro** | T4, L4 (24GB), A100 (40/80GB), H100 (80GB) | 25.0 – 85.0 GB | **`/tmp/` & `/content/` (~150-200 GB)** | Ephemeral CCU billing | 🛡️ **OUTBOUND RELAY / IFRAME / BATCH**. No proxy daemons on primary accounts. |
| **Modal.com** | A100-80GB, A10G, L4, T4 | Configurable | Ephemeral container | Persistent `modal.Volume` (`/models`) | ✅ **NATIVE HTTPS**. Official `@modal.web_server` endpoint (`*.modal.run`). |
| **Cloud Run GPU** | NVIDIA L4 (24GB VRAM) | Configurable | Ephemeral container / GCS FUSE | Scaled to 0 when idle | ✅ **NATIVE HTTPS**. Official Google Cloud Run serverless endpoint. |

---

## 2. The 16 Inviolable Laws of Cloud GPU Notebooks

1. **Law 1: Disk Quota Sizing (`/tmp` vs `/kaggle/working`)**: Download models, cache, and weights directly to **`/tmp/models/`**. The `/tmp` filesystem has 57.6+ GB to 1 TB capacity; `/kaggle/working/` has a strict 19.52 GB ceiling.
2. **Law 2: Kaggle Strict Anti-Tunnel Invariant (Zero-Ban Guarantee)**: NEVER run `cloudflared`, `ngrok`, `playit.gg`, or `demo.launch(share=True)` on Kaggle. It triggers container network audits and account termination. Use headless offline batch mode or in-notebook UI only.
3. **Law 3: Secret Ingestion Pre-Flight & Graceful Diagnostics**: Wrap secret retrieval in resilient fallbacks (Kaggle secrets -> Colab `userdata.get` -> `os.environ`).
4. **Law 4: GGUF Magic Byte Validation (`b'GGUF'`)**: Assert file size > 100 MB and first 4 bytes are `b'GGUF'` before initializing llama.cpp to catch silent HTML error pages.
5. **Law 5: Elimination of Duplicate Download Caching**: Stream weights directly via single-pass chunk streaming (`download_file_direct`), avoiding standard `huggingface_hub` 2x caching.
6. **Law 6: Jupyter Progress Bar Flooding Suppression**: Disable progress bars (`HF_HUB_DISABLE_PROGRESS_BARS=1`, `TQDM_DISABLE=1`, `TRANSFORMERS_VERBOSITY=error`) to prevent browser freezes.
7. **Law 7: In-Process Socket Reclamation**: Reclaim open file descriptors on ports 7860/8000 via `psutil` before restarting Uvicorn/FastAPI.
8. **Law 8: Never Kill or Bind to Colab Port 8080/8081**: Colab's Datalab bridge runs on 8080. Bind application servers strictly to port `7860`.
9. **Law 9: PyTorch Ghost Allocations After CUDA OOM**: Always run `gc.collect()`, `torch.cuda.empty_cache()`, and `torch.cuda.ipc_collect()` before model initialization.
10. **Law 10: Pre-Compiled Wheels for `llama-cpp-python`**: Use pre-compiled CUDA wheels (`https://abetlen.github.io/llama-cpp-python/whl/cu124`) to avoid 15-minute cmake compilation timeouts.
11. **Law 11: Linux Subprocess SIGHUP Invariant (`start_new_session=True`)**: Detach child processes using `start_new_session=True` so they survive ephemeral shell terminations.
12. **Law 12: Diffusers `torchao 0.10.0` Conflict on Kaggle**: Run `pip uninstall -y torchao` or load weights via `safetensors.torch.load_file()`.
13. **Law 13: Pure NumPy Color Keying**: Avoid toxic dependencies like `rembg` by using pure NumPy Euclidean color keyers.
14. **Law 14: No `__file__` in Global Notebook Scope**: Guard notebook path lookups with `Path(__file__).parent if "__file__" in globals() else Path("/tmp/workspace")`.
15. **Law 15: Speculative Decoding Purge**: Strip speculative draft decoding models when generating structured code or JSON to prevent syntax corruption.
16. **Law 16: Safe Auto-Stop & Credit Conservation**: Always trigger `runtime.unassign()` (Colab), `scaledown_window=30` (Modal), or `sys.exit(0)` (Kaggle) on task completion.

---

## 3. Four Ban-Proof Inference Architectures

* **Architecture A: Outbound Relay Worker Pattern (Ban-Proof Real-Time API)**: External client posts prompt to Upstash Redis / Cloudflare Queue; Colab/Kaggle worker polls outbound (`redis.blpop`), computes on GPU, and posts outbound response. Zero listening ports or inbound tunnels.
* **Architecture B: High-Density Batch Manifest Pipeline (Highest CCU Value)**: Run headless batch tasks from offline manifests, write results to zip, upload, and invoke `runtime.unassign()`.
* **Architecture C: Native In-Notebook Studio**: Render UI directly inside Colab via `serve_kernel_port_as_iframe(7860)` over Google's internal WebSocket bridge.
* **Architecture D: Colab VS Code Remote Kernel**: Connect desktop VS Code directly to remote GPU runtime via official Google Colab extension and OAuth.

---

## 4. Universal Self-Healing Pre-Flight Verification Cell

```python
# UNIVERSAL CLOUD GPU PRE-FLIGHT INITIALIZER
import os, sys, gc, psutil, time
from pathlib import Path

print("🛡️ [Pre-Flight] Running environment diagnostics and memory cleanup...")
IS_COLAB = "google.colab" in sys.modules or os.path.exists("/content")
IS_KAGGLE = os.path.exists("/kaggle")
SCRATCH_DIR = Path("/tmp/models")
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

if IS_KAGGLE:
    print("📍 Platform: Kaggle Dual-T4. Enforcing /tmp storage and ZERO-TUNNEL policy.")
    assert not os.path.exists("/usr/local/bin/cloudflared"), "Banned reverse tunnel detected on Kaggle!"
elif IS_COLAB:
    print("📍 Platform: Google Colab. Initializing safe runtime environment.")

os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TQDM_DISABLE"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["DIFFUSERS_VERBOSITY"] = "error"

try:
    current_proc = psutil.Process()
    for conn in current_proc.net_connections(kind='inet'):
        if conn.laddr.port in [7860, 8000] and conn.fd != -1:
            try: os.close(conn.fd)
            except Exception: pass
except Exception: pass

try:
    import torch
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            torch.cuda.set_device(i)
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        print(f"✅ VRAM Purged: {torch.cuda.device_count()} GPU(s) active. GPU 0: {torch.cuda.get_device_name(0)}")
except ImportError:
    pass
print("🚀 [Pre-Flight Complete] Environment verified.")
```
