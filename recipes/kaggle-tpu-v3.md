# Kaggle TPU v3-8 & Colab Trillium TPU Playbook

> **Kaggle TPU v3-8**: 4 dual-core chips = **8 physical TPU cores**, **128 GB total HBM** (16 GB HBM per core; 2D torus ICI interconnect), **30 hrs/week free quota** (max 9h continuous).  
> **Colab Pro TPUs**: `v5e1` (16 GB HBM, ~2.5 CCU/hr), `v6e1` Trillium (32 GB HBM + 175 GB host RAM, ~4.2 CCU/hr).

---

## 1. The Golden Rule: Never Run Dynamic MoE / Variable Contexts in Naive PyTorch/XLA

TPU XLA compiles computation graphs for **exact static tensor shapes** `[batch, seq_len]`.
- If every user prompt has a different token length (e.g. 412, 413, 419 tokens), XLA triggers a **20–120 second graph recompilation freeze on every single request**, exhausting host RAM and timing out connections.
- For Sparse Mixture-of-Experts (MoE) on PyTorch/XLA, padding dynamic expert routing to worst-case shapes wastes up to **85% of MXU compute**.

---

## 2. Mandatory Architecture: JAX + Pallas + Power-of-Two Bucketing

1. **Install JAX TPU Stack & Keep XLA Cache on `/tmp`**:
   ```python
   import os
   os.environ["XLA_PYTHON_CLIENT_PREALLOCATE"] = "false"
   os.environ["XLA_PYTHON_CLIENT_MEM_FRACTION"] = "0.85"
   os.environ["HF_HOME"] = "/tmp/hf_cache"
   ```
   ```bash
   pip install -q "jax[tpu]" -f https://storage.googleapis.com/jax-releases/libtpu_releases.html
   pip install -q vllm-tpu flax optax safetensors huggingface_hub
   ```
   *(Verify discovery before loading weights: `import jax; assert len(jax.devices()) == 8` on Kaggle TPU v3-8.)*

2. **Power-of-Two XLA Sequence Bucketing**:
   Pad every incoming prompt strictly up to the nearest pre-compiled bucket ceiling so XLA compiles only **4 graphs total**:
   ```python
   BUCKETS = [1024, 2048, 4096, 8192]

   def pad_to_bucket(token_ids: list[int], pad_token_id: int) -> tuple[list[int], int]:
       orig_len = len(token_ids)
       target = next((b for b in BUCKETS if b >= orig_len), BUCKETS[-1])
       if orig_len > target:
           token_ids = token_ids[-target:]
           orig_len = target
       padded = token_ids + [pad_token_id] * (target - orig_len)
       return padded, orig_len
   ```
   Run 1 dummy forward pass per bucket (`1024`, `2048`, `4096`, `8192`) during startup warm-up so real inference hits compiled XLA HLO caches instantly.

3. **JAX + Pallas Fused MoE (`ep=8`) for Massive MoEs (64B–320B)**:
   - On TPU v3-8 (128 GB HBM), sharding sparse MoEs (`zai-org/GLM-4.5`, `Qwen3-Next-80B-A3B`, `Qwen3-Coder-Next-80B`) across all 8 cores with **Expert Parallelism (`ep=8`)** and **Pallas MegaBlocks Grouped Matrix Multiplications (GMM)** operates inside each core's local **64 MiB VMEM** and distributes across ICI links without materializing zero-padded tensors in HBM—sustaining up to **82% peak MXU throughput**.
   - **NEVER run GGUF files on TPU without CPU offload**: `.gguf` quantized formats (`Q4_K_M`, `IQ4_XS`) are CUDA/AVX-512 kernels and cannot execute natively on TPU MXUs. Use native **BF16 / INT8 / 4-bit JAX/Flax or SafeTensors** checkpoints on TPU.

---

## 3. Recommended TPU Models

| Model | Repo | Format | Footprint | Hardware Target |
|---|---|---|---|---|
| **GLM 320B MoE (4-bit JAX)** | `zai-org/GLM-4.5` | JAX / SafeTensors | ~58 GB | Kaggle TPU v3-8 (128 GB HBM) |
| **Qwen 2.5 32B / 72B Instruct** | `Qwen/Qwen2.5-32B-Instruct` | BF16 / INT8 | 32–64 GB | Kaggle TPU v3-8 (`vllm-tpu` `tensor_parallel_size=8`) |
| **DeepSeek-R1-Distill-Qwen-32B** | `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` | BF16 | ~64 GB | Kaggle TPU v3-8 or Colab Pro `v6e1` (with host offload) |

See [`../research/02_tpu_jax_pallas_moe_serving.md`](../research/02_tpu_jax_pallas_moe_serving.md) for the complete JetStream / SGLang-JAX / Pallas architecture reference.
