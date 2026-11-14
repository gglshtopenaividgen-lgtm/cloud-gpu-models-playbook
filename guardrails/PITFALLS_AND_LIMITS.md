# Cloud GPU Pitfalls, Quotas & Hardware Limits

> Verified runtime failures and architectural invariants across Kaggle, Google Colab, Modal, Hugging Face, `llama.cpp`, `ik_llama.cpp`, `vLLM`, `Diffusers`, and TPU XLA.

---

## 1. Platform Quotas & Disk Traps

| Platform | Compute Limit | Real Disk Trap | Required Fix |
|---|---|---|---|
| **Kaggle GPU (Dual T4)** | 30 hrs/wk (45 hrs/wk if Colab Pro linked); 12h max run; resets Sat 00:00 UTC | `/kaggle/working/` has a hard **19.52 GB** cap | Route `HF_HOME`, `HF_HUB_CACHE`, `TORCH_HOME`, and GGUF downloads to `/tmp/models` (**50–80+ GB** ephemeral space) |
| **Kaggle TPU v3-8** | 30 hrs/wk; 9h max run | Only 16 GB host RAM in some shapes + XLA compiles static shapes | Power-of-two sequence bucketing `[1024, 2048, 4096, 8192]` + JAX/Pallas `ep=8` |
| **Colab Free (T4)** | Dynamic ephemeral idle cutoff (~12h max); **12.7 GB Host RAM** | Multi-part SafeTensors reconstruction (`29+ GB`) triggers Linux OOM `SIGKILL (Exit 137)` | Stream pre-quantized single-file GGUFs directly to `/tmp/models` |
| **Colab Pro** | Billed in CCU/hr (`T4 ~1.07–1.60`, `L4 4.13`, `A100 6.9–11.8`, `H100 25.0`, `High-RAM CPU 0.24`) | Port `8080` is permanently owned by Google Datalab supervisor | Bind user servers to `7860`, `7890`, `8000`, or `8081`—**never** `8080` or `8082` |
| **Modal Serverless** | $30/mo starter credit; per-second billing; 1024 GiB persistent Volume | Uncapped `@modal.web_server` spins up parallel GPUs on queue depth + `3600s` idle burn | **Always** enforce `max_containers=1`, `scaledown_window=60`, and `--no-mmap` |
| **Cloud Run L4** | Pay-per-second L4 + 15-min default idle timeout | Containers idle-bill after interactive tests | Enforce a hard session TTL + instant `--min-instances=0` / `--no-traffic` teardown |

---

## 2. Kaggle & Colab Anti-Ban / AUP Guardrails

1. **Zero Reverse Tunnels on Kaggle**: Never launch `cloudflared`, `ngrok`, `bore`, `localtunnel`, or SSH tunnels inside Kaggle notebooks. Use offline batch pipelines or Kaggle's official Jupyter Server Proxy (`*.jupyter-proxy.kaggle.net`).
2. **Zero Third-Party Tunnels on Colab Free Interactive Sessions**: Use `google.colab.output.eval_js("google.colab.kernel.proxyPort(7860)")` or `demo.launch(share=True)`.
3. **Never Kill Arbitrary System Processes or Allocate Huge Swapfiles on Colab Free**: Triggers instant runtime disconnect (`SIGKILL`).
4. **Never Attempt Biometric Re-Verification After Account Bans**: Keep verified sessions phone-verified cleanly; never attempt multi-account evasion.

---

## 3. `llama.cpp`, `ik_llama.cpp` & `vLLM` Runtime Pitfalls

1. **GGUF Magic Byte Verification (`b"GGUF"`)**:
   - Wrong HF slugs or gated repos return an HTTP 404/401 HTML page. Naive downloads save HTML as `.gguf`, crashing `llama-server` with `invalid magic characters: 'Repo', expected 'GGUF'`.
   - Always assert `f.read(4) == b"GGUF"` and `size > 100 MB` before loading, and support `fallback_repo` / `fallback_file` mirrors.
2. **2x Cache Duplication on Download**:
   - Downloading via `hf_hub_download()` into `~/.cache/huggingface` and then copying to `/kaggle/working` wastes 2x disk. Always pass `local_dir="/tmp/models"`.
3. **FP16 KV Cache OOM on Long Contexts**:
   - On 24 GB Modal L4 (`~22.5 GB` usable), `32B IQ4_XS` (17.69 GB) + `q8_0` 32K KV cache (`4.25 GB`) + CUDA buffer = **22.74 GB -> OOM!**
   - Pass `-ctk q4_0 -ctv q4_0` (2.25 GB KV cache at 32K ctx) to stay safely under 21 GB.
4. **Modern `llama-server` Boolean `-fa` vs T4 Assert**:
   - In modern `llama-server` (b12000+), `-fa` is a **boolean flag** (`--flash-attn on` can fail CLI arg parsing in mainline builds; `ik_llama.cpp` uses `-fa on`).
   - Older `llama-cpp-python` CUDA wheels assert `k->type == GGML_TYPE_F16` on Tesla T4 (`sm_75`) when combining `flash_attn=True` with `q4_0` KV cache (`type_k=2`). Always fall back to `flash_attn=False` if T4 asserts.
5. **Modal `--no-mmap` Requirement**:
   - Modal Volumes mount over virtual FUSE; `mmap()` stalls or faults CUDA transfers. Always pass `--no-mmap`.
6. **Pip `--prefer-binary` for `llama-cpp-python`**:
   - Without `--prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124` (with `cu122` / `cu121` fallback), pip downloads source `.tar.gz` and compiles CUDA C++, spiking CPU/RAM to 100% for 15 minutes until Colab OOM-kills the VM.
7. **vLLM Traps**:
   - Remove deprecated `--disable-log-requests` on `vllm>=0.32`.
   - Omit `--quantization awq` on `compressed-tensors` Neural Magic checkpoints (`config.json` mismatch).
   - Never force `VLLM_ATTENTION_BACKEND=FLASHINFER` on Tesla T4 (FA2 requires compute capability `>= 8.0`; T4 is `7.5` -> let vLLM auto-select `TRITON_ATTN`).
8. **CPU Prompt-Eval Watchdog Suicide**:
   - During 2.5K+ token repo-map prompt prefill on 8 vCPUs, `llama-server` saturates CPU for 40–80s and HTTP `/health` times out. **Never** kill a living subprocess (`proc.poll() is None`) on `/health` timeouts.
9. **Missing `HAVE_FANCY_SIMD` in `ik_llama.cpp`**:
   - Cloud Xeon hypervisors mask AVX-512 CPUID bits under bare `-DGGML_NATIVE=ON`. Explicitly pass `-DGGML_AVX512=ON -DGGML_AVX512_VNNI=ON -DGGML_ARCH_FLAGS="-D__AVX512F__ -D__AVX512VNNI__ -D__AVX512VL__ -D__AVX512BW__ -D__AVX512DQ__"`.

---

## 4. PyTorch, `transformers`, `accelerate` & `diffusers` Pitfalls

1. **Quadratic Eager Attention OOM on T4**:
   - Without `attn_implementation="sdpa"`, Transformers allocates `[batch, heads, seq, seq]` (~18.12 GiB at 15.6K tokens on 14B!). Always set `attn_implementation="sdpa"`.
2. **Accelerate `device_map="auto"` Greedy GPU 0 Packing**:
   - Packs `cuda:0` to 14+ GiB before spilling to `cuda:1`, causing OOM on activations. Always pass `max_memory={0: "8500MB", 1: "8500MB"}` on Dual-T4 and route inputs via `next(model.parameters()).device`.
3. **Deprecated `torch_dtype` & Old `bitsandbytes`**:
   - Use `dtype=torch.float16` (or `bfloat16` on L4/A100/H100—T4 lacks native bf16!).
   - On Colab Python 3.13, install `bitsandbytes>=0.46.1` (`<0.43.3` fails Diffusers version gate).
4. **Kaggle Outdated `torchao 0.10.0` (`FqnToConfig` ImportError)**:
   - Run `pip uninstall -y torchao` before importing `diffusers`, or set `diffusers.utils.import_utils._torchao_available = False`.
5. **SDXL Black NaN Frames & `enable_attention_slicing()` Trap**:
   - Load `madebyollin/sdxl-vae-fp16-fix` to prevent FP16 VAE overflow (>65,504) black outputs.
   - **Never** call `pipe.enable_attention_slicing()` on PyTorch 2.x (it disables native SDPA and cuts speed by ~3x); use `pipe.enable_vae_tiling()` and `enable_vae_slicing()` instead.
6. **FLUX / Chroma Checkpoints in Diffusers**:
   - `BitsAndBytesConfig(load_in_4bit=True)` throws `NotImplementedError` on `FluxTransformer2DModel`.
   - Avoid unmerged PEFT/LoRA dumps with `lora_A`/`base_layer` keys (`Cannot copy out of meta tensor`).
   - Use verified pre-quantized GGUFs (`t8star/flux.1-dev-abliterated-V2-GGUF` via `FluxPipeline` + `FluxTransformer2DModel.from_single_file(..., quantization_config=GGUFQuantizationConfig(...))`, or `silveroxides/Chroma1-HD-gguf` via `ChromaPipeline` + `ChromaTransformer2DModel` on `diffusers>=0.35.1`).
7. **Linux `glibc` Heap Retention on Hot-Swap**:
   - After `del pipe; gc.collect(); torch.cuda.empty_cache()`, call `ctypes.CDLL("libc.so.6").malloc_trim(0)` so Linux reclaims freed host RAM arenas.
8. **Chroma Keying Without `onnxruntime`/`rembg`**:
   - `rembg` can invoke `sys.exit(1)` or `SIGILL` inside interactive Jupyter kernels. Use [`../recipes/chroma_key_numpy.py`](../recipes/chroma_key_numpy.py) (`<15ms` pure NumPy).

---

## 5. Interactive Notebook & Python Hazards

1. **`psutil 5.9.x` in Colab**: `Process.net_connections()` does not exist; use `getattr(proc, "net_connections", None) or getattr(proc, "connections", None)`.
2. **Jupyter `tqdm` Output Freeze**: Set `HF_HUB_DISABLE_PROGRESS_BARS=1` and `TQDM_DISABLE=1` so weight loading doesn't spam 700+ lines and crash the browser tab.
3. **NumPy 2.x Breakage**: Pin `numpy<2.0.0` when installing extra packages in Kaggle/Colab (`pip install ...`).
4. **Gradio Route Overwriting & `streamer.end()` Deadlocks**:
   - Call `gr.close_all()` before relaunching; mount FastAPI custom routes via `gr.mount_gradio_app(fastapi_app, demo, path="/")` *after* building `demo`, or `demo.launch()` overwrites custom routes.
   - Always wrap `TextIteratorStreamer` generation threads in `try ... finally: streamer.end()` so exceptions don't hang SSE clients forever.
5. **Jupyter `asyncio.run()` Collision**: Apply `nest_asyncio.apply()` before running async bridges inside IPython cells.
6. **Abliteration Geometry Invariant**: Apply orthogonal projection `I - r r^T` strictly to `mlp.down_proj` on mid-to-late layers, **never** to `self_attn.o_proj` (which destroys syntax/code coherence).
