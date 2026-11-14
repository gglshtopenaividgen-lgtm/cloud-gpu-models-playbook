# Google Colab Free & Pro Playbook

> **Colab Free**: Single Tesla T4 (15.36 GB VRAM, 12.7 GB host RAM, ephemeral; **no** guaranteed idle session).  
> **Colab Pro**: Unlockable tiers billed in Compute Units (CCU/hr):
> - **T4 Standard / High-RAM**: 16 GB VRAM + **51–52 GB RAM** (1.07–1.60 CCU/hr)
> - **NVIDIA L4**: 24 GB VRAM (`Ada Lovelace`, **native `bf16` + `FP8`**, 4.13 CCU/hr)
> - **NVIDIA V100**: 16 GB VRAM + 51 GB RAM (5.40 CCU/hr)
> - **NVIDIA A100**: 40 GB or 80 GB HBM2e (`Ampere`, 6.9–11.8 CCU/hr)
> - **NVIDIA G4 (RTX PRO 6000 Blackwell)**: **96 GB VRAM** (frontier single-card)
> - **NVIDIA H100**: 80 GB HBM3 (25.0 CCU/hr)
> - **High-RAM CPU (8 Intel Xeon AVX-512 vCPUs, 51 GB RAM)**: **0.24 CCU/hr** (see [`cpu-avx512-ik-llama.md`](./cpu-avx512-ik-llama.md))

---

## 1. Strict Colab Runtime Invariants

1. **Port `8080` Is Reserved by Google Datalab**:
   - **NEVER** bind `llama-server`, `uvicorn`, or `gradio` to port `8080` or `8082` in Colab—it collides with Colab's supervisor daemon and causes random 502 resets or runtime disconnects.
   - Use **Port `7860`** (Gradio / Web UI) or **Port `7890` / `8000` / `8081`** (OpenAI `/v1` API).
2. **Never Kill Arbitrary Processes or Enable Swapfiles**:
   - Never run aggressive swapfile allocations on Colab Free's small disk or kill system supervisor processes on port `8080`; Colab's watchdog disconnects the entire container (`SIGKILL`).
3. **Zero Third-Party Reverse Tunnels When First-Party Proxy Works**:
   - Never spawn `cloudflared` / `ngrok` background daemons during interactive Colab Free web sessions—they trigger Colab anti-abuse disconnect popups.
   - Use **Google Colab's built-in loopback proxy** (`google.colab.output.eval_js("google.colab.kernel.proxyPort(7860)")`) or `demo.launch(share=True)` (official Gradio relay) for interactive UIs. Reserve headless API tunnels or public endpoints for **Modal** or **Colab Pro**.
4. **`psutil 5.9.x` Compatibility**:
   - Colab ships `psutil 5.9.x`, which lacks `Process.net_connections()` (added in 6.0). Always use:
     ```python
     conn_fn = getattr(proc, "net_connections", None) or getattr(proc, "connections", None)
     ```
5. **Prevent Source Compilation Spikes (`--prefer-binary`)**:
   - Never run `pip install llama-cpp-python` without pre-built CUDA wheel indexes (`--prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124` with `cu122` / `cu121` fallback). Building `llama.cpp` CUDA from source spikes CPU/RAM to 100% for 15 minutes and triggers Colab's OOM killer (`Exit 137`).
6. **Direct Single-File GGUF Streaming (No Multi-Part Weight Reconstruction)**:
   - On Colab Free (**12.7 GB Host RAM**), reconstructing sharded 14B/32B SafeTensors (`~29.5 GB`) before 4-bit quantization triggers `SIGKILL (Exit 137)`. Always download pre-quantized single-file GGUFs directly to `/tmp/models/`.
7. **Python 3.13 + `bitsandbytes` + `torchao` + `dtype`**:
   - Pass `dtype=torch.float16` (or `torch.bfloat16` on L4/A100/H100), **never** deprecated `torch_dtype`.
   - For Diffusers 4-bit / GGUF (FLUX, Chroma): ensure `diffusers>=0.35.1`, `bitsandbytes>=0.46.1`, and neutralize stale `torchao` (`_torchao_available = False`) before importing pipelines.
   - **Never** use BitsAndBytes on `FluxTransformer2DModel` (`NotImplementedError`); use pre-quantized GGUF checkpoints (`t8star/flux.1-dev-abliterated-V2-GGUF` or `silveroxides/Chroma1-HD-gguf`) with `GGUFQuantizationConfig(compute_dtype=torch.float16)` + `enable_model_cpu_offload()`.

---

## 2. Single Tesla T4 (16 GB) Safe Envelope

- Keep static LLM weights **`<= 10.5 GB`** (0.8 GB CUDA context + <=10.5 GB weights + ~4.7 GB KV cache).
- **Fits cleanly**:
  - **7B–14B `Q4_K_M`** (`Qwen2.5-Coder-7B` 4.7 GB, `L3-8B-Stheno-v3.2` 5.2 GB, `MN-12B-Celeste-V1.9` 7.5 GB, `magnum-v2.5-12b-kto` 7.8 GB, `Qwen2.5-Coder-14B` 9.4 GB @ 8K–16K ctx).
  - **27B Sub-2-Bit Ternary** (`prism-ml/Ternary-Bonsai-2-27B-gguf`, `PQ2_0` **5.8 GB**, requires PrismML `llama.cpp` fork).
  - **Diffusion**: `stabilityai/sd-turbo` (3.8 GB), `RealVisXL_V5.0` / `Animagine XL 3.1` with **`madebyollin/sdxl-vae-fp16-fix`** (prevents black NaN frames) and `enable_vae_tiling()` (NEVER `enable_attention_slicing()` on PyTorch 2.x!).

## 3. Colab Pro L4 (24 GB) & A100 (40/80 GB)

- **NVIDIA L4 (24 GB VRAM)**: Native `bf16` + `FP8`. Ideal for `Qwen2.5-Coder-32B-abliterated-IQ4_XS.gguf` (17.69 GB) with **`-ctk q4_0 -ctv q4_0 -fa`** (20.74 GB total at 32K ctx) and **FLUX.1 / Wan2.1 / TRELLIS** where T4 stalls on FP16/CPU offload.
- **NVIDIA A100 (40/80 GB)**: Runs 70B `Q4_K_M` / `AWQ` or unquantized 32B models, `FLUX.1-dev` FP16/BF16, and `Wan2.1-T2V-14B` without PCIe offload bottlenecks.
- Always run `ctypes.CDLL("libc.so.6").malloc_trim(0)` after `del pipe; gc.collect(); torch.cuda.empty_cache()` when hot-swapping pipelines on Linux host RAM.
