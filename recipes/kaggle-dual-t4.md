# Kaggle Dual Tesla T4 Playbook (30.72 GB VRAM)

> **Hardware**: 2 × NVIDIA Tesla T4 (`sm_75`, Turing, 15.36 GB GDDR6 each = **30.72 GB total VRAM**), 30 GB Host RAM, 4 vCPUs  
> **Quota**: 30 hrs/week (up to 45 hrs/week if Colab Pro linked); resets Saturday 00:00 UTC  
> **Max Continuous Run**: 12 hours per session  

---

## 1. Critical Storage & Network Invariants

1. **Disk Quota Trap (`/tmp` vs `/kaggle/working`)**:
   - `/kaggle/working/` has a hard **19.52 GB** quota. Downloading a 17–20 GB GGUF there triggers `OSError: [Errno 28] No space left on device`.
   - `/tmp/` sits on the ephemeral overlay with **50–80+ GB** free. **ALWAYS** point `HF_HOME`, `HF_HUB_CACHE`, `TORCH_HOME`, and GGUF downloads to `/tmp/models` or `/tmp/hf_cache`:
     ```python
     import os
     os.environ["HF_HOME"] = "/tmp/hf_cache"
     os.environ["HF_HUB_CACHE"] = "/tmp/hf_cache/hub"
     os.environ["TORCH_HOME"] = "/tmp/torch_cache"
     os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
     os.environ["TQDM_DISABLE"] = "1"
     os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
     ```
2. **Single-Pass GGUF Download (No 2x Cache Duplication)**:
   - Never download via `hf_hub_download()` into default `~/.cache` and then copy to `/kaggle/working/`. Use `local_dir="/tmp/models"` and verify `file.read(4) == b"GGUF"` + `size > 100 MB`.
3. **Zero Reverse Tunnels (Kaggle ToS / AUP Safety)**:
   - **NEVER** spawn `cloudflared`, `ngrok`, `bore`, `localtunnel`, or SSH reverse tunnels in Kaggle notebooks—automated scanners flag them as unauthorized proxy/tunnel abuse.
   - Use **batch-only offline jobs** (`inputs.json -> outputs.json` / `.png`), Kaggle's **official Jupyter Server Proxy** (`*.jupyter-proxy.kaggle.net`), or Colab/Modal for public APIs.

---

## 2. Dual-T4 Parallelism: Split vs Isolated Modes

Kaggle's two T4s communicate over **PCIe 3.0** (no NVLink). Never use tensor parallelism (`tp=2`) over PCIe; use **layer-wise pipeline splitting**:

### Mode A: Single Large LLM (24B–35B, `<= 21.5 GB` weights)
- Split layers 50/50 across GPU 0 and GPU 1:
  - `llama-server`: `--split-mode layer --tensor-split 1,1 --n-gpu-layers 99`
  - `llama-cpp-python`: `Llama(..., tensor_split=[0.5, 0.5], n_gpu_layers=-1)`
- **KV Cache Quantization**: Quantize KV cache from FP16 to 4-bit (`-ctk q4_0 -ctv q4_0` or `type_k=2, type_v=2` in `llama_cpp`) to save ~75% KV RAM and fit 32K–65K context.
- **Turing FlashAttention Caution**:
  - In `llama-server` b12000+, `-fa` is a **boolean flag** (pass `-fa`, NOT `--flash-attn on`).
  - Older `llama-cpp-python` CUDA wheels assert `k->type == GGML_TYPE_F16` if `flash_attn=True` is combined with quantized KV cache (`type_k=2`) on Turing (`sm_75`). Always support fallback to `flash_attn=False` if the kernel aborts.

### Mode B: LLM + Diffusion Co-Residency (GPU 0 = LLM, GPU 1 = Diffusers)
- Pin LLM exclusively to GPU 0 (`tensor_split=[1.0, 0.0]`, max ~10.5 GB weights) and pin SDXL / SD-Turbo / Chroma1-HD to `cuda:1` (`pipe.to("cuda:1")`).
- Prevents CUDA allocator fragmentation and cross-card OOM spikes.

### Mode C: Native Hugging Face `transformers` Multi-GPU Sharding (e.g., Training / Activation Steering)
- Never use `device_map="auto"` blindly on Dual-T4—Accelerate greedily fills `cuda:0` to 14+ GiB first, leaving `cuda:1` empty and OOMing on activations!
- Explicitly cap per-GPU budgets and route tensors to the first parameter device:
  ```python
  import os, torch
  os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
  model = AutoModelForCausalLM.from_pretrained(
      repo_id,
      dtype=torch.float16,          # Note: torch_dtype is deprecated; T4 has no native bf16!
      attn_implementation="sdpa",   # Mandatory: avoids quadratic eager attention OOM
      device_map="auto",
      max_memory={0: "8500MB", 1: "8500MB"},
  )
  first_device = next(model.parameters()).device
  inputs = tokenizer(prompt, return_tensors="pt").to(first_device)
  ```
- **Uninstall Pre-installed `torchao 0.10.0`**: Kaggle bundles an incompatible `torchao 0.10.0` that crashes modern `diffusers`/`peft`. Run `pip uninstall -y torchao` before importing `diffusers` or set `diffusers.utils.import_utils._torchao_available = False`.
- **Pin `numpy<2.0.0`**: Dynamic `pip install` upgrades can pull NumPy 2.x and break pre-compiled `scipy`/`sklearn` C-extensions.

---

## 3. Recommended Verified Models for Kaggle Dual-T4

| Model | Quant / File | Size | Expected Context | Notes |
|---|---|---|---|---|
| `Qwen/Qwen2.5-Coder-32B-Instruct-abliterated` (`bartowski`) | `IQ4_XS` | 17.69 GB | 32K (`q4_0` KV) | Coding flagship; fits 50/50 split cleanly |
| `IsValorum/Qwen3.8-35B-A3B-Distill-MTP-APEX-I-MiniPlus-V2.1-Abliterated-GGUF` | Surgical GGUF | 13.7–16.1 GB | 64K (`q4_0` KV) | Sparse MoE (3.8B active); very fast TPS |
| `LessThanThreeAI/Qwen3.8-27B-Humanlike-Chat-GGUF` | `IQ4_XS` | 14.50 GB | 16K–32K | De-assistantized natural prose (`T=0.85, min_p=0.07`) |
| `mradermacher/Mistral-Small-24B-Instruct-2501-abliterated-GGUF` | `Q4_K_M` | 14.30 GB | 64K (`q4_0` KV) | Strong 24B general reasoning |
| `bartowski/Llama-3.3-70B-Instruct-GGUF` | `IQ3_M` / `Q2_K` | 26.3–30.5 GB | 8K–16K | Hybrid GPU+CPU RAM offload (~32 layers GPU) |

See [`serve_gguf_dual_t4.py`](./serve_gguf_dual_t4.py) and [`pre_flight_check.py`](./pre_flight_check.py) for production-ready code.
