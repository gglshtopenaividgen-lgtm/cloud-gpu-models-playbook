# 🔬 FRONTIER AI RESEARCH ARCHIVE & KNOWLEDGE BASE

> **Master Directory for Cloud GPU, Unconventional Models, Agentic Architectures & Ephemeral Computing**  
> **Locations**: `<WORKSPACE_ROOT>\research\` & `<BRAIN_ROOT>\research\hi_frontier_research\`

---

## Modular Research Index

| # | Topic & Document | Key Theoretical & Practical Scope | Primary Compute Target |
|---|---|---|---|
| **01** | [`01_sub2bit_ternary_and_activation_steering.md`](01_sub2bit_ternary_and_activation_steering.md) | Sub-2-bit ternary quantization ({−1,0,+1}), BitNet b1.58, PrismML Ternary Bonsai 2 27B, runtime refusal vector subtraction $y' = y - \alpha(y \cdot r)r$ via PyTorch hooks across 129 residual sites. | Colab / Kaggle T4 (15GB), Mobile / Edge |
| **02** | [`02_tpu_jax_pallas_moe_serving.md`](02_tpu_jax_pallas_moe_serving.md) | Serving GLM-5.3-Flash 320B MoE on free Kaggle TPU v3-8 at 64 tok/s, 262k context window, JAX/Pallas 3-bit codebook kernels, power-of-two compilation bucketing. | Kaggle TPU VM v3-8 (128GB HBM) |
| **03** | [`03_expressive_voice_and_avatar_animation.md`](03_expressive_voice_and_avatar_animation.md) | Studio-grade Kokoro-82M TTS (<500MB RAM, 20x RT on CPU), F5-TTS non-autoregressive flow matching, LivePortrait real-time facial reenactment from audio stream. | Colab T4, Kaggle Dual-T4, Local CPU |
| **04** | [`04_deassistantized_humanlike_chat_models.md`](04_deassistantized_humanlike_chat_models.md) | Anti-assistant dataset filtering, DPO/KTO alignment unlearning, LessThanThreeAI 27B Humanlike Chat, Magnum v2.5 12B KTO, Min-P (0.05) anti-sycophant sampling profiles. | Kaggle Dual-T4, Colab T4 |
| **05** | [`05_sub60ms_flow_diffusion_and_chroma_keying.md`](05_sub60ms_flow_diffusion_and_chroma_keying.md) | 35–60ms continuous latent generation via DiffusionGemma-Jev & SD-Turbo ADD, Qwen-Image-2.1 modular LoRAs, pure NumPy vectorized Euclidean chroma keyer (15ms, zero-crash). | Colab T4, Kaggle Dual-T4 |
| **06** | [`06_production_loop_engineering_agents.md`](06_production_loop_engineering_agents.md) | Paradigm shift from prompt engineering to Loop Engineering (Vikas Gupta / smolagents), 3-node Evaluator-Optimizer closed loops, error signature cycle detection, self-healing code harnesses. | Ephemeral Notebooks, Background Swarms |
| **07** | [`07_sovereign_agent_memory_walrus_vs_fts5.md`](07_sovereign_agent_memory_walrus_vs_fts5.md) | Walrus Protocol decentralized portable memory vs SQLite FTS5 (BM25) local memory, ContextEngine compaction, 0.2ms symbol precision, AST skeleton preservation. | Central Brain & Hermes Memory |
| **08** | [`08_frontier_abliterated_models_catalog.md`](08_frontier_abliterated_models_catalog.md) | Discovery matrix of Top 10 unconventional open-weight models (Qwen 3.8 35B APEX, Bonsai 2 27B, Magnum 12B), single-cell copy-paste recipes for Kaggle Dual-T4 and Colab T4, exact hyper-parameters. | Kaggle Dual-T4, Colab T4 |
| **09** | [`09_cpu_extreme_inference_ik_llama_and_80b_moe.md`](09_cpu_extreme_inference_ik_llama_and_80b_moe.md) | `ik_llama.cpp` AVX-512 `HAVE_FANCY_SIMD` compilation, `-rtr` row-interleaved tensor repacking (3.63x prefill, 1.67x TG), fused Gated DeltaNet & MoE kernels (`-fmoe -muge -ser`), `IQ4_XS` imatrix quantization, and 30B–109B MoE/Dense scaling (`Qwen3-Coder-Next-80B-A3B` @ 18-26 tok/s) in 51 GB RAM. | Colab High-RAM CPU (51GB), Kaggle CPU (30GB) |

---

## Clean Root Invariant

Per system invariants, raw monolithic text dumps (`readthis.md`, `readthis1.md`) in project root are cleanly indexed here. Consult the specific research document above for implementation details.


### Cross-Platform Cloud Compute & Agent Memory Research
- [cloud_compute_platforms.md](./cloud_compute_platforms.md) — Free-tier quotas, reset schedules & limits across Kaggle, Colab, Modal, and Cloud Run
- [open_source_skills_memory_research.md](./open_source_skills_memory_research.md) — Portable agent skill & FTS5 memory benchmarks
