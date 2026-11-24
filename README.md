# Cloud GPU & Open-Weight Models Playbook (`cloud-gpu-models-playbook`)

> Self-contained, agent-ready knowledge base for deploying LLMs, VLMs, TTS, Diffusion, and 3D/Video generators on **Kaggle (Dual-T4 & TPU v3-8)**, **Google Colab (Free & Pro)**, **Modal Serverless**, and **AVX-512 High-RAM CPU**—bundled with a refreshed, path-independent **Portable Brain** (`.agents/` universal skills & rules).

---

## Fast Agent Quickstart (Read This First)

1. **Kaggle Disk Quota Rule (`/tmp` vs `/kaggle/working`)**:
   - `/kaggle/working/` has a hard **19.52 GB** cap. **Always** set `HF_HOME=/tmp/hf_cache`, `HF_HUB_CACHE=/tmp/hf_cache/hub`, `TORCH_HOME=/tmp/torch_cache`, and download GGUFs to `/tmp/models/` (50–80+ GB free).
2. **Kaggle Zero-Tunnel Rule**:
   - Never run `cloudflared`, `ngrok`, `bore`, or SSH reverse tunnels on Kaggle. Run batch pipelines or use Kaggle's official Jupyter proxy.
3. **Colab Reserved Port Rule**:
   - Port `8080` is reserved by Google Datalab. Bind user servers to `7860`, `7890`, `8000`, or `8081`.
4. **GGUF Magic Byte Check & Single-Pass Download**:
   - Always validate `f.read(4) == b"GGUF"` and `size > 100 MB` before launching inference (invalid HF slugs silently download HTTP 404 HTML pages). Set `HF_TOKEN` via environment variables (`os.environ.get("HF_TOKEN", "")`).
5. **Dual-T4 / Modal L4 KV Cache Flags**:
   - Pair 24B–35B models with **4-bit KV cache** (`-ctk q4_0 -ctv q4_0`) so 32K–65K context fits in 22.5 GB usable L4 VRAM (`20.74 GB` for 32B `IQ4_XS` @ 32K ctx) or 30.72 GB Dual-T4 VRAM (`--split-mode layer --tensor-split 1,1`).
   - On `llama-server` (b12000+), pass boolean `-fa` (not `--flash-attn on`). On older Turing (`sm_75`) `llama-cpp-python` wheels, fall back to `flash_attn=False` if `q4_0` KV asserts.
6. **Modal Zero-Waste Billing Guard**:
   - Always set `max_containers=1`, `scaledown_window=60`, `--no-mmap` (FUSE Volume compatibility), and active `/health` polling inside `@modal.web_server`.
7. **Colab High-RAM CPU (`51 GB`, `0.24 CCU/hr`)**:
   - Compile `ikawrakow/ik_llama.cpp` with explicit AVX-512 flags (`HAVE_FANCY_SIMD`) and run `-rtr -fmoe -muge -ser 1,6` + `IQ4_XS`/`IQ3_M` to get **18–42 tok/s** on 30B–80B sparse MoE models.

---

## Repository Map

| Directory / File | Contents |
|---|---|
| [`catalog/models.json`](./catalog/models.json) | Structured catalog of **74 verified models** (Text/Coding/MoE/Ternary, VLM, Draft, Voice, Image/3D/Video), 28 hardware profiles, exact KV geometry, sampling hyperparameters, and quant BPW tables |
| [`catalog/MODELS.md`](./catalog/MODELS.md) | Agent-readable Markdown catalog tables and exact KV cache memory equation |
| [`recipes/kaggle-dual-t4.md`](./recipes/kaggle-dual-t4.md) | Kaggle Dual Tesla T4 (`30.72 GB`) split vs GPU-isolated LLM+Diffusion recipe |
| [`recipes/kaggle-tpu-v3.md`](./recipes/kaggle-tpu-v3.md) | Kaggle TPU v3-8 (`128 GB HBM`) JAX + Pallas MoE & power-of-two XLA bucketing |
| [`recipes/colab-free-pro.md`](./recipes/colab-free-pro.md) | Colab Free (16 GB T4 / 12.7 GB RAM) & Pro (L4/A100/G4/H100) invariants |
| [`recipes/modal-serverless.md`](./recipes/modal-serverless.md) | Modal Serverless billing guards, L4 VRAM math, `vllm` & `llama-server` flags |
| [`recipes/cpu-avx512-ik-llama.md`](./recipes/cpu-avx512-ik-llama.md) | `ik_llama.cpp` AVX-512 build & runtime repacking guide for 30B–109B MoEs |
| [`recipes/serve_gguf_dual_t4.py`](./recipes/serve_gguf_dual_t4.py) | Parameterized GGUF downloader + OpenAI `/v1` `llama-server` launcher |
| [`recipes/pre_flight_check.py`](./recipes/pre_flight_check.py) | Reusable GPU, `/tmp` disk, `psutil 5.9/6.0` port reclaim, GGUF magic & `malloc_trim` guard |
| [`recipes/chroma_key_numpy.py`](./recipes/chroma_key_numpy.py) | `<15ms` pure NumPy Euclidean alpha chroma keyer (zero `rembg`/`onnxruntime` crash) |
| [`recipes/modal_llama_template.py`](./recipes/modal_llama_template.py) | Production `@modal.web_server` deployment template |
| [`guardrails/PITFALLS_AND_LIMITS.md`](./guardrails/PITFALLS_AND_LIMITS.md) | Distilled hardware limits, OOM fixes, Diffusers/torchao/bnb shields, and AUP rules |
| [`research/`](./research/INDEX.md) | Deep architectural dossiers (sub-2-bit ternary, steering, TPU Pallas, audio/avatar, humanlike chat, flow diffusion, loop agents, sovereign memory, `ik_llama.cpp` CPU MoEs, platform quotas) |
| [`portable-brain/`](./portable-brain/README.md) | Sanitized, path-independent **Portable Brain** (`brain_cli.py`, 13 universal `.agents/skills/`, universal `.agents/rules/`, UI anti-slop guide, external harness rules) |

---

## Quick Usage

```bash
# 1. Check local/cloud GPU & /tmp disk budget
python recipes/pre_flight_check.py

# 2. Launch a Dual-T4 GGUF OpenAI server (set HF_TOKEN if pulling gated repos)
export HF_TOKEN="<YOUR_HF_TOKEN>"
python recipes/serve_gguf_dual_t4.py \
  --repo bartowski/Qwen2.5-Coder-32B-Instruct-abliterated-GGUF \
  --file Qwen2.5-Coder-32B-Instruct-abliterated-IQ4_XS.gguf \
  --ctx 32768 --tensor-split 1,1 --kv-type q4_0

# 3. Query Portable Brain skill selector
python portable-brain/brain_cli.py select "cloud gpu" --universal
```
