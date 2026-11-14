# Modal Serverless GPU Playbook

> **Billing**: Per-second millisecond billing ($30/mo free starter tier), zero idle charges once scaled to zero, **1024 GiB persistent `@modal.Volume` storage**.  
> **Hardware Rates**: T4 (`$0.59/hr`, 16GB), L4 (`$0.80/hr`, 24GB), A10G (`$1.10/hr`, 24GB), A100-40 (`$2.10/hr`), A100-80 (`$2.50/hr`), H100 (`$3.95/hr`), H200 Eco (`$4.85/hr`, 141GB), H200 Std (`$7.21/hr`, 141GB), B200 (`$6.25/hr`, 192GB), CPU (`$0.0473/core/hr`).

---

## 1. Critical Billing & Stability Invariants

1. **Always Set `max_containers=1` on Single-Model LLM/Diffusion Endpoints**:
   - Without `max_containers=1`, incoming queued requests during a cold start cause Modal's autoscaler to spawn **multiple GPU containers simultaneously**, multiplying GPU credit burn!
2. **Enforce Short `scaledown_window=60` (or `30`–`120`s), NEVER `3600`**:
   - Model weights are cached on a persistent `@modal.Volume` (cold boots from volume take ~10–25 seconds). Setting `scaledown_window=3600` burns an entire hour of GPU billing after every idle chat!
3. **Pass `--no-mmap` to `llama-server` on Modal**:
   - Modal mounts persistent volumes over a distributed virtual FUSE filesystem where POSIX `mmap()` faulting stalls model initialization or crashes CUDA transfers. Always pass `--no-mmap` so weights read sequentially into GPU VRAM.
4. **Non-Blocking `@modal.web_server` Launch + Active Liveness Probe**:
   - **NEVER** call `proc.wait()` inside a `@modal.web_server` function—Modal expects the decorated function to spawn the HTTP server (`subprocess.Popen`) and **return** once the port is healthy so Modal's router can forward traffic.
   - Conversely, never return immediately without checking health: redirect stdout/stderr to `/tmp/llama_server.log` and poll `http://127.0.0.1:8000/health` in a loop while checking `proc.poll()` so any binary crash surfaces within seconds instead of hanging the full 900s `startup_timeout`!
5. **Pre-Verify Scripts Before Deploying**:
   - Run `python -m py_compile` locally before `modal deploy` so broken endpoints never spin up idle GPU containers.

---

## 2. Modal NVIDIA L4 (24 GB, ~22.5 GB Usable) Exact VRAM Math

For **`Qwen2.5-Coder-32B-Instruct-abliterated-IQ4_XS.gguf`** (`17.69 GB` weights, `64` layers, `8` KV heads, `128` head dim):
- With **`q8_0` KV cache** at `32768` ctx:
  $$\text{KV} = \frac{2 \times 64 \times 8 \times 128 \times 1.0625 \times 32768}{1024^3} \approx 4.25\text{ GB}$$
  Total = `17.69 + 4.25 + 0.8 CUDA ≈ 22.74 GB` -> **OOM on L4 (22.5 GB usable)!**
- With **`-ctk q4_0 -ctv q4_0 -fa`** at `32768` ctx:
  $$\text{KV} = \frac{2 \times 64 \times 8 \times 128 \times 0.5625 \times 32768}{1024^3} \approx 2.25\text{ GB}$$
  Total = `17.69 + 2.25 + 0.8 ≈ 20.74 GB` -> **Fits with ~1.8–2.1 GB safety headroom!**

---

## 3. Modern `llama-server` & `vllm` CLI Flags

- **Modern `llama-server` (b12000+)**:
  - Pass `-fa` (boolean flag). Passing `--flash-attn on` can be misparsed by older/newer builds—check `llama-server --help` or stick to `-fa` in `llama.cpp` mainline vs `-fa on` in `ik_llama.cpp`.
- **vLLM 0.32+**:
  - **DO NOT pass `--disable-log-requests`** (removed in modern vLLM -> `unrecognized arguments` crash).
  - **DO NOT force `--quantization awq`** on Neural Magic / Compressed-Tensors models (`quant_method` in `config.json`); omit `--quantization` so vLLM auto-detects Marlin/Compressed-Tensors.
  - **DO NOT set `VLLM_ATTENTION_BACKEND=FLASHINFER` on Tesla T4**: FlashAttention-2 requires Compute Capability `>= 8.0` (L4/A100/H100). On T4 (`CC 7.5`), let vLLM auto-select `TRITON_ATTN`.

See [`modal_llama_template.py`](./modal_llama_template.py) for a drop-in production script.
