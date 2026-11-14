# Extreme x86 AVX-512 CPU Inference: `ik_llama.cpp`, Runtime Tensor Repacking (`-rtr`), Fused Gated DeltaNet, and 30B–109B MoE Scaling on 51 GB High-RAM CPU

> **Focus**: Breaking the DDR4/DDR5 Memory Bandwidth Wall on 8-vCPU Intel Xeon AVX-512 Instances (`colab_pro_highram_cpu` • 51.0 GB RAM @ 0.24 CCU/hr)  
> **Source**: Cross-Referenced Archive Audit (`01_sub2bit...`, `02_tpu_jax...`, `08_frontier_abliterated...`) + Live `ik_llama.cpp` & Hugging Face `HfApi` Verification (October 2026)  
> **Hardware Target**: Google Colab Pro High-RAM CPU (8 Xeon vCPUs, 51.0 GB RAM), Kaggle CPU (30.0 GB RAM), Local x86 Workstations  

---

## 1. Executive Summary: Why Standard `llama.cpp` Underperforms on CPU

In standard autoregressive decoding on mainline `llama.cpp` with `Q4_K_M` weights, CPU inference suffers from three compounding bottlenecks:
1. **Unaligned Cache-Line Striding**: Standard GGUF tensors store weights row-by-row. During multi-threaded matrix-vector multiplication (`GEMV`), threads read non-contiguous memory blocks across rows, wasting L1/L2 cache lines and stalling on memory controller prefetcher misses.
2. **6-Bit Asymmetric Unpacking Overhead in `Q4_K_M`**: `Q4_K` super-blocks pack 8 sub-block scales and 8 minimums into bit-packed 6-bit integers across byte boundaries. On CPU without a GPU's massive register file, unpacking these 6-bit scales and subtracting asymmetric minimums consumes valuable SIMD instructions before `vpdpbusd` (AVX-512 VNNI dot-product) can execute.
3. **Unfused Gated DeltaNet & MoE Dispatch**: Modern hybrid architectures (`Qwen3-Next-80B-A3B`, `Qwen3.6-35B-A3B`) interleave Gated DeltaNet linear recurrence with sparse Mixture-of-Experts (128 to 256 experts). Mainline `llama.cpp` executes separate `ffn_up`, `ffn_gate`, and `DeltaNet` passes (Issue #19480), bottlenecking `Qwen3-Next-80B-A3B` to ~7.7 tok/s.

---

## 2. The `ik_llama.cpp` CPU Acceleration Stack (`ikawrakow/ik_llama.cpp`)

Iwan Kawrakow's `ik_llama.cpp` resolves all three bottlenecks through specialized AVX-512 SIMD microkernels (`iqk_mul_mat`):

### 2.1 Explicit Compile-Time AVX-512 Gate (`HAVE_FANCY_SIMD`)
Virtualized cloud hypervisors (such as GCP N1/N2 Xeon vCPUs in Google Colab) frequently mask CPUID sub-leaves when `-march=native` (`-DGGML_NATIVE=ON`) is invoked alone, causing the compiler to silently omit one of the 5 mandatory macros (`__AVX512F__`, `__AVX512VNNI__`, `__AVX512VL__`, `__AVX512BW__`, `__AVX512DQ__`) and fall back to slow AVX2 code.

**Mandatory CMake Build Invocation (Takes ~85s on 8 Colab vCPUs with `-DGGML_CUDA=OFF`)**:
```bash
git clone --depth 1 https://github.com/ikawrakow/ik_llama.cpp /content/ik_llama.cpp
cmake -B /content/ik_llama.cpp/build -S /content/ik_llama.cpp \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_CUDA=OFF \
  -DGGML_NATIVE=ON \
  -DGGML_AVX512=ON \
  -DGGML_AVX512_VBMI=ON \
  -DGGML_AVX512_VNNI=ON \
  -DGGML_AVX512_BF16=ON \
  -DGGML_ARCH_FLAGS="-D__AVX512F__ -D__AVX512VNNI__ -D__AVX512VL__ -D__AVX512BW__ -D__AVX512DQ__"
cmake --build /content/ik_llama.cpp/build --config Release --target llama-server -j$(nproc)
```
- **Verification Invariant**: `objdump -d build/bin/llama-server | grep -c vpdpbusd` must return >100 instructions, and server startup must print `HAVE_FANCY_SIMD is defined`.

### 2.2 Core Runtime Optimization Flags
| Flag | Mechanism | Empirical Speedup on Xeon AVX-512 |
|---|---|---|
| **`-rtr` (`--run-time-repack`)** | Repacks all RAM-resident tensors into 4-row or 8-row interleaved SIMD memory layouts (`_R4` / `_R8`) during model load (PR #147). | **3.63x faster prompt prefill (`pp512`)** and **1.67x faster token generation (`tg128`)** on `IQ4_XS`. |
| **`-fmoe` (`--fused-moe`)** | Fuses `ffn_up` and `ffn_gate` matrix multiplications + SiLU/SwiGLU activation for sparse MoE layers (PR #229). | **+15% to +25% TG speedup** on MoE topologies by halving expert memory barrier passes. |
| **`-muge` (`--merge-up-gate-experts`)** | Physically merges `ffn_up_exps` and `ffn_gate_exps` tensors in RAM (PR #1137 / #1413) into contiguous single-pass GEMV buffers. | Eliminates split-pointer expert gathers across 128–256 experts. |
| **`-ser Kmin,t` (`--smart-expert-reduction`)** | Dynamically prunes low-weight active experts per token (PR #239). E.g. `-ser 1,6` evaluates top 6 instead of 8 experts. | **+20% to +25% TG speedup** with <0.3% perplexity delta. |
| **Fused Gated DeltaNet Kernels** | Native SIMD fused recurrence kernels for `Qwen3-Next` and `Qwen3.6` hybrid linear attention (PR #1315, #1333, #1362, #1373). | **2.4x speedup** on `Qwen3-Next-80B-A3B` (from ~7.7 tok/s to **18–25+ tok/s**). |
| **`-fa on -ctk q8_0 -ctv q8_0`** | Native CPU SIMD Flash Attention with quantized `q8_0` (or `q4_0` + `-khad -vhad` Hadamard rotation) KV cache. | Cuts KV cache RAM and attention bandwidth by **50% to 75%**. |
| **`--spec-type ngram-mod:n_max=48,n_min=2,ngram_size_n=8`** | Zero-RAM self-speculative N-gram lookup decoding built directly into the C++ token loop (PR #1261 / #1646). | **1.4x to 2.1x speedup** on code generation and refactoring with **0 MB extra RAM**. |

---

## 3. Why `IQ4_XS` (Imatrix 4.25 bpw) Beats `Q4_K_M` (4.85 bpw) on CPU

| Quantization | Bits Per Weight (bpw) | 30B Model Size | `pp512` Speed (`ik_llama.cpp -rtr` vs Mainline) | `tg128` Speed (`ik_llama.cpp -rtr` vs Mainline) | Architectural Reason |
|---|---|---|---|---|---|
| **`IQ4_XS` (`i1` imatrix)** | **4.25 bpw** | **16.37 GB** | **269.9 tok/s** vs 74.4 tok/s (**3.63x**) | **13.58 tok/s** vs 8.15 tok/s (**1.67x**) | Even-bit scales + 16-entry non-linear lookup table decoded in 1 instruction via `_mm512_shuffle_epi8` (`vpshufb`); 12% smaller bus footprint than `Q4_K_M`. |
| **`Q4_0` (repacked)** | **4.50 bpw** | **17.38 GB** | **273.5 tok/s** vs 153.5 tok/s (**1.78x**) | **12.92 tok/s** vs 11.23 tok/s (**1.15x**) | Symmetric 4-bit nibbles with zero min-offset math; slightly higher perplexity than `IQ4_XS`. |
| **`Q4_K_M`** | **4.85 bpw** | **18.56 GB** | **269.6 tok/s** vs 108.4 tok/s (**2.49x**) | **13.48 tok/s** vs 9.57 tok/s (**1.41x**) | Asymmetric 6-bit scale/min bit-packing requires extra unpacking shifts and larger memory transfer. |
| **`IQ3_M` (`i1` imatrix)** | **3.52 bpw** | **13.51 GB** | **~245 tok/s** (**4.5x**) | **~15.2 tok/s** (**1.45x**) | Transfers 27% fewer bytes over DDR4/DDR5 RAM bus; essential for fitting 80B–109B models in 51 GB RAM. |

---

## 4. Complete Verified Catalog: Running 30B to 109B Abliterated Models in 51.0 GB RAM

All repositories and exact filenames below were verified live against the Hugging Face Hub API (`HfApi`) to guarantee byte sizes $\le 46.5\text{ GB}$ (fitting inside 51.0 GB RAM with zero swap thrashing):

### Tier 1: 80B–109B Colossal Sparse MoE (Maximum Intelligence + High Speed on 51 GB CPU)
| Model & Architecture | Verified Hugging Face Repo | Exact Filename | File Size | Total / Active Params | Free RAM Left (of 51 GB) | Expected CPU Speed (`ik_llama.cpp`) |
|---|---|---|---|---|---|---|
| **`Qwen3-Coder-Next-80B-A3B` (Abliterated Coding Flagship)** | `mradermacher/Huihui-Qwen3-Coder-Next-abliterated-i1-GGUF` | `Huihui-Qwen3-Coder-Next-abliterated.i1-IQ3_M.gguf`<br>`Huihui-Qwen3-Coder-Next-abliterated.i1-IQ4_XS.gguf` | **35.07 GB**<br>**42.60 GB** | **80.0B Total**<br>**3.0B Active** (3.75%) | **15.9 GB** (32K+ ctx)<br>**8.4 GB** (16K ctx) | **18 – 26+ tok/s** *(Reads only ~1.8 GB/token!)* |
| **`Qwen3-Next-80B-A3B-Instruct` (Abliterated General/Reasoning)** | `mradermacher/Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated-i1-GGUF` | `Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.i1-IQ3_M.gguf`<br>`Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.i1-IQ4_XS.gguf` | **34.99 GB**<br>**42.60 GB** | **80.0B Total**<br>**3.0B Active** (3.75%) | **16.0 GB** (32K+ ctx)<br>**8.4 GB** (16K ctx) | **18 – 26+ tok/s** |
| **`Llama-4-Scout-17B-16E` (109B Multimodal/Text MoE)** | `mradermacher/Llama-4-Scout-17B-16E-Instruct-abliterated-v2-i1-GGUF` | `Llama-4-Scout-17B-16E-Instruct-abliterated-v2.i1-IQ3_XXS.gguf`<br>`Llama-4-Scout-17B-16E-Instruct-abliterated-v2.i1-IQ3_XS.gguf` | **41.66 GB**<br>**44.30 GB** | **109.0B Total**<br>**17.0B Active** | **9.3 GB**<br>**6.7 GB** | **4.8 – 7.2 tok/s** |
| **`GLM-4.5-Air-106B-A12B` (106B Agentic MoE)** | `mradermacher/Huihui-GLM-4.5-Air-abliterated-lossytensors-i1-GGUF` | `Huihui-GLM-4.5-Air-abliterated-lossytensors.i1-Q2_K.gguf` | **44.97 GB** | **106.0B Total**<br>**12.0B Active** | **6.0 GB** | **6.5 – 9.5 tok/s** |

### Tier 2: 30B–35B High-Velocity Sparse MoE (Fastest Interactive Speed + 128K Context)
| Model & Architecture | Verified Hugging Face Repo | Exact Filename | File Size | Total / Active Params | Free RAM Left (of 51 GB) | Expected CPU Speed (`ik_llama.cpp`) |
|---|---|---|---|---|---|---|
| **`Qwen3.6-35B-A3B` (Latest 35B Hybrid MoE)** | `mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-i1-GGUF` | `Huihui-Qwen3.6-35B-A3B-abliterated.i1-IQ4_XS.gguf`<br>`Huihui-Qwen3.6-35B-A3B-abliterated.i1-Q6_K.gguf`<br>`Huihui-Qwen3.6-35B-A3B-abliterated.i1-Q8_0.gguf` | **18.73 GB**<br>**28.51 GB**<br>**37.80 GB** | **35.0B Total**<br>**3.0B Active** | **32.2 GB** (128K ctx)<br>**22.5 GB** (64K ctx)<br>**13.2 GB** (32K ctx) | **24 – 38+ tok/s** *(Even `Q6_K`/`Q8_0` near-FP16 fits!)* |
| **`Qwen3-Coder-30B-A3B-Instruct` (Dedicated Coding MoE)** | `mradermacher/Huihui-Qwen3-Coder-30B-A3B-Instruct-abliterated-i1-GGUF` | `Huihui-Qwen3-Coder-30B-A3B-Instruct-abliterated.i1-IQ4_XS.gguf` | **16.37 GB** | **30.5B Total**<br>**3.3B Active** | **34.6 GB** (128K ctx) | **25 – 42+ tok/s** |
| **`Qwen3.8-35B-A3B-Distill-MTP-APEX-I` (Surgical Quant + MTP)** | `IsValorum/Qwen3.8-35B-A3B-Distill-MTP-APEX-I-MiniPlus-V2.1-Abliterated-GGUF` | Surgical Heterogeneous GGUF (`IQ2_S` interior / `Q4_K` boundary) | **16.10 GB** | **35.2B Total**<br>**3.8B Active** | **34.9 GB** (128K ctx) | **25 – 40+ tok/s** |

### Tier 3: 27B–72B Dense Models (100% Active Parameters per Token)
| Model & Architecture | Verified Hugging Face Repo | Exact Filename | File Size | Total / Active Params | Free RAM Left (of 51 GB) | Expected CPU Speed (`ik_llama.cpp`) |
|---|---|---|---|---|---|---|
| **`Ternary-Bonsai-2-27B` / `OrcaBonsai-27B` (Sub-2-Bit Ternary)** | `prism-ml/Ternary-Bonsai-2-27B-gguf` / `chimingw/Qwen3.8-27B-Uncensored-OrcaRouter-GGUF` | `PQ2_0` / `PTQ1_0` Native Ternary (1.71 bpw) | **5.93 GB** | **27.0B Dense**<br>(100% active) | **45.0 GB** (128K+ ctx) | **10 – 16 tok/s** *(3.2x smaller than 4-bit; 98.2% reasoning retention)* |
| **`Qwen2.5-Coder-32B-Instruct` (Dense 32B Coding)** | `bartowski/Qwen2.5-Coder-32B-Instruct-abliterated-GGUF` | `Qwen2.5-Coder-32B-Instruct-abliterated-IQ4_XS.gguf` (+ `1.5B` Draft) | **17.69 GB** (+1.1 GB) | **32.8B Dense**<br>(100% active) | **32.2 GB** (64K ctx) | **6.5 – 9.5 tok/s** *(with 1.5B Draft + `-rtr`)* |
| **`Qwen2.5-72B-Instruct` (Dense 72B Flagship)** | `mradermacher/Qwen2.5-72B-Instruct-abliterated-i1-GGUF` | `Qwen2.5-72B-Instruct-abliterated.i1-IQ3_M.gguf`<br>`Qwen2.5-72B-Instruct-abliterated.i1-IQ4_XS.gguf` | **35.50 GB**<br>**39.71 GB** | **72.7B Dense**<br>(100% active) | **15.5 GB** (16K ctx)<br>**11.3 GB** (8K ctx) | **2.8 – 4.2 tok/s** *(with 1.5B Draft + `-rtr` + `ngram-mod`)* |
| **`Llama-3.3-70B-Instruct` (Dense 70B Flagship)** | `bartowski/Llama-3.3-70B-Instruct-abliterated-GGUF` | `Llama-3.3-70B-Instruct-abliterated-IQ3_M.gguf`<br>`Llama-3.3-70B-Instruct-abliterated-IQ4_XS.gguf` | **31.94 GB**<br>**37.90 GB** | **70.6B Dense**<br>(100% active) | **19.0 GB** (16K ctx)<br>**13.1 GB** (16K ctx) | **3.0 – 4.5 tok/s** *(with `Llama-3.2-1B` Draft + `-rtr`)* |
