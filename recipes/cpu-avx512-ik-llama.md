# Extreme x86 AVX-512 CPU Inference (`ik_llama.cpp`) Playbook

> **Target Hardware**: Google Colab Pro High-RAM CPU (8 Intel Xeon AVX-512 vCPUs, **51.0 GB RAM** @ **0.24 CCU/hr**), Kaggle CPU (30 GB RAM), or local x86 AVX-512 hosts.  
> **Throughput**: **18–42+ tok/s** on 30B–80B Sparse MoE models (`3B active`); **6.5–16 tok/s** on 27B–32B dense models.

---

## 1. Why `ik_llama.cpp` Destroys Mainline `llama.cpp` on CPU

1. **Runtime Tensor Repacking (`-rtr`)**: Repacks row-major GGUF weights into 4-row/8-row SIMD cache-aligned layouts (`_R4`/`_R8`) on load—delivering **3.63x faster prompt prefill (`pp512`)** and **1.67x faster generation (`tg128`)** on `IQ4_XS`.
2. **`IQ4_XS` (`4.25 bpw`) > `Q4_K_M` (`4.85 bpw`)**: Avoids 6-bit asymmetric min/scale unpacking overhead; decodes 16-entry LUT in a single `_mm512_shuffle_epi8` (`vpshufb`) instruction while reducing DDR4/DDR5 bus traffic by 12%.
3. **Fused Sparse MoE + Gated DeltaNet (`-fmoe -muge -ser`)**:
   - `-fmoe`: Fuses `ffn_up` + `ffn_gate` + SwiGLU.
   - `-muge`: Physically merges `ffn_up_exps` and `ffn_gate_exps` across 128–256 experts.
   - `-ser 1,6`: Smart expert reduction (prunes low-weight active experts per token for +20–25% speedup at `<0.3%` perplexity delta).
   - Native fused Gated DeltaNet SIMD kernels boost `Qwen3-Next-80B-A3B` from ~7.7 tok/s to **18–26+ tok/s**.
4. **Explicit `HAVE_FANCY_SIMD` Build Gate**: Cloud hypervisors often mask CPUID sub-leaves when `-march=native` (`-DGGML_NATIVE=ON`) is used alone, silently falling back to AVX2! Explicitly pass all 5 AVX-512 arch macros:

```bash
git clone --depth 1 https://github.com/ikawrakow/ik_llama.cpp /tmp/ik_llama.cpp
cmake -B /tmp/ik_llama.cpp/build -S /tmp/ik_llama.cpp \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_CUDA=OFF \
  -DGGML_NATIVE=ON \
  -DGGML_AVX512=ON \
  -DGGML_AVX512_VBMI=ON \
  -DGGML_AVX512_VNNI=ON \
  -DGGML_AVX512_BF16=ON \
  -DGGML_ARCH_FLAGS="-D__AVX512F__ -D__AVX512VNNI__ -D__AVX512VL__ -D__AVX512BW__ -D__AVX512DQ__"
cmake --build /tmp/ik_llama.cpp/build --config Release --target llama-server -j$(nproc)

# Verify AVX-512 VNNI instructions were actually emitted:
objdump -d /tmp/ik_llama.cpp/build/bin/llama-server | grep -c vpdpbusd
```

---

## 2. Recommended Launch Flags (8-vCPU / 51 GB RAM)

```bash
/tmp/ik_llama.cpp/build/bin/llama-server \
  -m /tmp/models/Huihui-Qwen3.6-35B-A3B-abliterated.i1-IQ4_XS.gguf \
  --host 127.0.0.1 --port 7890 \
  -t 8 -c 32768 \
  -rtr -fmoe -muge -ser 1,6 \
  -fa -ctk q8_0 -ctv q8_0 \
  --spec-type ngram-mod:n_max=48,n_min=2,ngram_size_n=8
```

- **`--spec-type ngram-mod:...`**: Zero-RAM self-speculative N-gram lookup (**1.4x–2.1x speedup** on coding/refactoring with 0 MB extra RAM).
- **Watchdog Warning**: During heavy 2,500+ token repo-map prompt prefill on CPU, HTTP `/health` can stall for 40–80s while all 8 cores saturate. **Never** kill a living `llama-server` process (`proc.poll() is None`) just because `/health` times out—only restart on real process exit! Also note interactive coding agents with 504 timeouts (`LiteLLM` 60s timeout) should prefer GPU L4/T4 when latency matters.

---

## 3. Verified Models Fitting in 51 GB Host RAM

| Model | Repo | Quant File | Size | Active | Free RAM Left | Est. Speed |
|---|---|---|---|---|---|---|
| **Qwen3-Coder-Next-80B-A3B** | `mradermacher/Huihui-Qwen3-Coder-Next-abliterated-i1-GGUF` | `.i1-IQ3_M.gguf` | 35.07 GB | 3.0B | 15.9 GB | 18–26+ tok/s |
| **Qwen3-Next-80B-A3B** | `mradermacher/Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated-i1-GGUF` | `.i1-IQ3_M.gguf` | 34.99 GB | 3.0B | 16.0 GB | 18–26+ tok/s |
| **Qwen3.6-35B-A3B** | `mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-i1-GGUF` | `.i1-IQ4_XS.gguf` | 18.73 GB | 3.0B | 32.2 GB | 24–38+ tok/s |
| **Qwen3-Coder-30B-A3B** | `mradermacher/Huihui-Qwen3-Coder-30B-A3B-Instruct-abliterated-i1-GGUF` | `.i1-IQ4_XS.gguf` | 16.37 GB | 3.3B | 34.6 GB | 25–42+ tok/s |
| **Llama-4-Scout-17B-16E** | `mradermacher/Llama-4-Scout-17B-16E-Instruct-abliterated-v2-i1-GGUF` | `.i1-IQ3_XXS.gguf` | 41.66 GB | 17.0B | 9.3 GB | 4.8–7.2 tok/s |
| **GLM-4.5-Air-106B** | `mradermacher/Huihui-GLM-4.5-Air-abliterated-lossytensors-i1-GGUF` | `.i1-Q2_K.gguf` | 44.97 GB | 12.0B | 6.0 GB | 6.5–9.5 tok/s |
