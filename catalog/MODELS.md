# Unified Cloud GPU & Open-Weight Model Catalog

> Machine-readable source: [`models.json`](./models.json)

## Quick VRAM & RAM Sizing Rules
- **Single Tesla T4 (16 GB VRAM, Colab Free)**: Keep model weights `<= 10.5 GB` (leaves ~4.5–5.0 GB for CUDA context + KV cache). Fits 3B–14B `Q4_K_M`, 27B sub-2-bit ternary (`PQ2_0` 5.8 GB), SD-Turbo / SDXL (`torch.float16` + VAE tiling), and FLUX GGUF `Q4_K_S` with `enable_model_cpu_offload()`.
- **Dual Tesla T4 (30.72 GB VRAM, Kaggle GPU T4 x2)**: Keep combined weights `<= 21.5 GB` for long context (up to 32K–65K with `-ctk q4_0 -ctv q4_0`). Use `--split-mode layer --tensor-split 1,1` for a single big LLM, or `1,0` / `0,1` when pairing LLM + Diffusion.
- **Modal NVIDIA L4 (24 GB VRAM, ~22.5 GB usable)**: Ideal for 32B `IQ4_XS` (17.69 GB) with **mandatory** `-ctk q4_0 -ctv q4_0 -fa` (20.74 GB total at 32K ctx; `q8_0` OOMs!).
- **Colab Pro High-RAM CPU (51 GB RAM, 8 AVX-512 Xeon vCPUs)**: Use `ik_llama.cpp` (`HAVE_FANCY_SIMD`, `-rtr -fmoe -muge`) + `IQ4_XS` / `IQ3_M` for 30B–109B sparse MoE up to 18–42 tok/s.
- **Kaggle TPU v3-8 (128 GB HBM / 8 cores @ 16 GB HBM each)**: Use JAX + Pallas Grouped Matrix Multiplications (`ep=8`) + power-of-two XLA bucketing (`[1024, 2048, 4096, 8192]`).

## KV Cache Exact Memory Formula
```python
BYTES = {'q4_0': 0.5625, 'q8_0': 1.0625, 'fp16': 2.0}
kv_gb = (2 * layers * kv_heads * head_dim * BYTES[kv_quant] * context_tokens) / (1024 ** 3)
```

## Text & Coding LLMs
| ID | Name | Repo | File / Quant | Size (GB) | Ctx | Recommended For |
|---|---|---|---|---|---|---|
| `llama-3.2-3b-abliterated` | Llama 3.2 3B Instruct Abliterated | `mradermacher/Llama-3.2-3B-Instruct-abliterated-GGUF` | `Llama-3.2-3B-Instruct-abliterated.Q4_K_M.gguf` | 2.1 | 32768 | Fast chat, mobile PWA assistant, and low-latency interactive tasks |
| `qwen2.5-coder-7b` | Qwen 2.5 Coder 7B Instruct Abliterated | `mradermacher/Qwen2.5-Coder-7B-Instruct-abliterated-GGUF` | `Qwen2.5-Coder-7B-Instruct-abliterated.Q4_K_M.gguf` | 4.7 | 32768 | Aider / Cursor CLI coding on Single T4 or 4-vCPU RAM |
| `deepseek-r1-7b` | DeepSeek R1 Distill Qwen 7B | `bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF` | `DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf` | 4.6 | 32768 | Complex algorithmic troubleshooting, math verification, and logic puzzles |
| `stheno-8b-v3.2` | L3 8B Stheno v3.2 (Sao10K Uncensored) | `mradermacher/L3-8B-Stheno-v3.2-GGUF` | `L3-8B-Stheno-v3.2.Q4_K_M.gguf` | 5.2 | 16384 | Immersive storytelling, character simulation, and creative fiction |
| `gemma-2-9b` | Gemma 2 9B IT Abliterated | `bartowski/gemma-2-9b-it-GGUF` | `gemma-2-9b-it-Q4_K_M.gguf` | 5.9 | 8192 | General reasoning, structured analysis, and technical QA |
| `celeste-12b` | Mistral Nemo 12B Celeste v1.9 | `mradermacher/MN-12B-Celeste-V1.9-GGUF` | `MN-12B-Celeste-V1.9.Q4_K_M.gguf` | 7.5 | 128000 | Long-form book analysis, large codebase ingestion, and authentic dialogue |
| `magnum-12b-kto` | Magnum v2.5 12B KTO (Claude-like) | `mradermacher/magnum-v2.5-12b-kto-GGUF` | `magnum-v2.5-12b-kto.Q4_K_M.gguf` | 7.8 | 16384 | Creative essays, nuanced debates, and premium conversational assistants |
| `mistral-nemo-12b` | Mistral Nemo 12B Abliterated (128k) | `mradermacher/Mistral-Nemo-Instruct-2407-abliterated-GGUF` | `Mistral-Nemo-Instruct-2407-abliterated.Q4_K_M.gguf` | 7.5 | 128000 | Full repo audits, research paper synthesis, and massive text parsing |
| `qwen2.5-coder-14b` | Qwen 2.5 Coder 14B Instruct Abliterated | `mradermacher/Qwen2.5-Coder-14B-Instruct-abliterated-GGUF` | `Qwen2.5-Coder-14B-Instruct-abliterated.Q4_K_M.gguf` | 9.4 | 32768 | Primary autonomous software engineering and multi-file refactoring |
| `deepseek-r1-14b` | DeepSeek R1 Distill Qwen 14B Abliterated | `mradermacher/DeepSeek-R1-Distill-Qwen-14B-abliterated-GGUF` | `DeepSeek-R1-Distill-Qwen-14B-abliterated.Q4_K_M.gguf` | 9.4 | 32768 | Complex architectural planning, mathematical proofs, and tricky bug diagnosis |
| `gemma-2-27b` | Gemma 2 27B IT Abliterated | `mradermacher/gemma-2-27b-it-abliterated-GGUF` | `gemma-2-27b-it-abliterated.Q4_K_M.gguf` | 16.2 | 8192 | Heavy reasoning on Kaggle Dual-T4 or Colab with Extend to RAM |
| `qwen2.5-coder-32b` | Qwen 2.5 Coder 32B Instruct Abliterated | `mradermacher/Qwen2.5-Coder-32B-Instruct-abliterated-GGUF` | `Qwen2.5-Coder-32B-Instruct-abliterated.Q4_K_M.gguf` | 19.8 | 32768 | Enterprise-grade codebase generation on Kaggle Dual-T4 |
| `qwen3.8-35b-uncensored` | Qwen 3.8 35B A3B Distill APEX-I Abliterated | `IsValorum/Qwen3.8-35B-A3B-Distill-MTP-APEX-I-MiniPlus-V2.1-Abliterated-GGUF` | `Qwen3.8-35B-A3B-Distill.APEX-I-MiniPlus-V2.1-Abliterated.gguf` | 13.7 | 262144 | High-throughput frontier reasoning on Single T4 or Dual-T4 |
| `qwen3.6-35b-a3b-abliterated` | Qwen 3.6 35B A3B Abliterated (MoE) | `mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-i1-GGUF` | `Huihui-Qwen3.6-35B-A3B-abliterated.i1-IQ4_XS.gguf` | 18.73 | 131072 | Fastest 30B+ interactive coding and long-context analysis on Colab High-RAM CPU |
| `qwen3-coder-next-80b-a3b-abliterated` | Qwen 3 Coder Next 80B A3B Abliterated (MoE) | `mradermacher/Huihui-Qwen3-Coder-Next-abliterated-i1-GGUF` | `Huihui-Qwen3-Coder-Next-abliterated.i1-IQ3_M.gguf` | 35.07 | 65536 | Frontier-class coding and complex refactoring on Colab High-RAM CPU |
| `llama-3.3-70b-instruct` | Llama 3.3 70B Instruct (Q3_K_S) | `mradermacher/Llama-3.3-70B-Instruct-GGUF` | `Llama-3.3-70B-Instruct.Q3_K_S.gguf` | 26.5 | 16384 | Kaggle Dual-T4 maximum intelligence and deep system architecture |
| `mistral-small-24b-abliterated` | Mistral Small 24B Instruct Abliterated | `mradermacher/Mistral-Small-24B-Instruct-2501-abliterated-GGUF` | `Mistral-Small-24B-Instruct-2501-abliterated.Q4_K_M.gguf` | 14.3 | 32768 | Primary fiction engine, visual novel dialogue, and high-complexity agentic coding |
| `clara-24b` | Clara 24B (Sao10K Dataset Fiction Engine) | `mradermacher/Clara-24B-GGUF` | `Clara-24B.Q4_K_M.gguf` | 14.3 | 32768 | Visual novel script writing, mature romance/drama scenes, and complex character roleplay |
| `lunaris-8b` | L3 8B Lunaris v1 (Sao10K Dialogue) | `bartowski/L3-8B-Lunaris-v1-GGUF` | `L3-8B-Lunaris-v1-Q4_K_M.gguf` | 4.9 | 16384 | Real-time game NPC dialogue, lightweight fiction, and responsive chat |
| `euryale-70b` | L3.3 70B Euryale v2.3 (Sao10K Uncensored Flagship) | `bartowski/L3.3-70B-Euryale-v2.3-GGUF` | `L3.3-70B-Euryale-v2.3-Q2_K.gguf` | 26.3 | 32768 | Kaggle Dual-T4 epic visual novel generation, intricate world-building, and high-literature storylines |
| `glm-320b-moe` | GLM 320B MoE (JAX/Pallas) | `zai-org/GLM-4.5` | `model.safetensors.index.json` | 58.0 | 262144 | Kaggle TPU v3-8 high-throughput long context workflows |
| `qwen2.5-72b-abliterated` | Qwen 2.5 72B Instruct Abliterated (FP8 / AWQ) | `mradermacher/Qwen2.5-72B-Instruct-abliterated-GGUF` | `Qwen2.5-72B-Instruct-abliterated.Q4_K_M.gguf` | 42.0 | 32768 | Modal A100-80GB / H100 high-throughput flagship agent workflows and deep system architecture |
| `llama-3.3-70b-abliterated` | Llama 3.3 70B Instruct Abliterated (FP8 / Q4) | `mradermacher/Llama-3.3-70B-Instruct-abliterated-GGUF` | `Llama-3.3-70B-Instruct-abliterated.Q4_K_M.gguf` | 39.5 | 32768 | Modal A100/H100 heavy enterprise development, novel generation, and autonomous agents |
| `command-r-plus-104b` | Command R+ 104B Uncensored (Q3_K_S GGUF) | `mradermacher/c4ai-command-r-plus-08-2024-GGUF` | `c4ai-command-r-plus-08-2024.Q3_K_S.gguf` | 48.0 | 128000 | High-precision agentic retrieval, massive document synthesis, and multi-tool orchestration on Modal |
| `llama-3.1-405b-fp8` | Llama 3.1 405B Instruct FP8 (8x H100 Giant) | `neuralmagic/Meta-Llama-3.1-405B-Instruct-FP8` | `model.safetensors.index.json` | 220.0 | 32768 | Modal 8x H100 high-stakes architectural analysis and benchmark breakthroughs |
| `qwen3.8-27b-humanlike` | Qwen 3.8 27B Humanlike Chat (IQ4_XS / Q4_K_M) | `LessThanThreeAI/Qwen3.8-27B-Humanlike-Chat-GGUF` | `Qwen3.8-27B-Humanlike-Chat-IQ4_XS.gguf` | 14.5 | 32768 | De-assistantized natural conversation on Kaggle Dual-T4 (16K-32K ctx, q4_0 KV) |
| `ternary-bonsai-2-27b` | PrismML Ternary Bonsai 2 27B (PQ2_0 / PTQ1_0) | `prism-ml/Ternary-Bonsai-2-27B-gguf` | `Ternary-Bonsai-2-27B-PQ2_0.gguf` | 5.8 | 32768 | 27B intelligence fitting inside a single 16GB T4 GPU (<6 GB weights) |
| `orcabonsai-27b-uncensored` | OrcaBonsai 27B Uncensored (Runtime Activation Steering) | `chimingw/Qwen3.8-27B-Uncensored-OrcaRouter-GGUF` | `Q4_K_M` | 16.2 | 32768 | Zero weight-damage runtime refusal steering (y' = y - alpha*(y.r)r) |
| `qwen3-next-80b-a3b-abliterated` | Qwen 3 Next 80B-A3B Instruct Abliterated (i1-IQ3_M / IQ4_XS) | `mradermacher/Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated-i1-GGUF` | `Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.i1-IQ3_M.gguf` | 34.99 | 65536 | Colab High-RAM CPU (51 GB RAM) with ik_llama.cpp (-rtr -fmoe -muge) |
| `qwen3-coder-30b-a3b-abliterated` | Qwen 3 Coder 30B-A3B Instruct Abliterated (i1-IQ4_XS) | `mradermacher/Huihui-Qwen3-Coder-30B-A3B-Instruct-abliterated-i1-GGUF` | `Huihui-Qwen3-Coder-30B-A3B-Instruct-abliterated.i1-IQ4_XS.gguf` | 16.37 | 131072 | 25-42 tok/s on 51GB AVX-512 CPU or Dual-T4 GPU |
| `llama-4-scout-17b-16e-abliterated` | Llama 4 Scout 17B-16E Instruct Abliterated v2 (i1-IQ3_XXS) | `mradermacher/Llama-4-Scout-17B-16E-Instruct-abliterated-v2-i1-GGUF` | `Llama-4-Scout-17B-16E-Instruct-abliterated-v2.i1-IQ3_XXS.gguf` | 41.66 | 32768 | Colab High-RAM CPU (51 GB RAM) via ik_llama.cpp -rtr |
| `glm-4.5-air-106b-abliterated` | GLM-4.5-Air 106B-A12B Abliterated (i1-Q2_K) | `mradermacher/Huihui-GLM-4.5-Air-abliterated-lossytensors-i1-GGUF` | `Huihui-GLM-4.5-Air-abliterated-lossytensors.i1-Q2_K.gguf` | 44.97 | 32768 | Colab High-RAM CPU (51 GB RAM) via ik_llama.cpp -rtr |

## Vision-Language Models (VLMs)
| ID | Name | Repo | File / Quant | Size (GB) | Recommended For |
|---|---|---|---|---|---|
| `qwen2.5-vl-7b-abliterated` | Qwen2.5-VL 7B Instruct Abliterated (SOTA Vision) | `huihui-ai/Qwen2.5-VL-7B-Instruct-abliterated` | `Qwen2.5-VL-7B-Instruct-abliterated.Q4_K_M.gguf` | 8.8 | Autonomous visual UI agents, complex document OCR, and unconstrained image inspection |
| `qwen2.5-vl-7b` | Qwen2.5-VL 7B Instruct (Official SOTA VLM) | `Qwen/Qwen2.5-VL-7B-Instruct` | - | 8.8 | High-precision GUI automation, complex document OCR, and visual code generation |
| `qwen2.5-vl-3b-abliterated` | Qwen2.5-VL 3B Instruct Abliterated (Compact SOTA) | `huihui-ai/Qwen2.5-VL-3B-Instruct-abliterated` | `Qwen2.5-VL-3B-Instruct-abliterated.Q4_K_M.gguf` | 5.5 | Low-latency visual QA, rapid screen audits, and dual-model T4 execution |
| `llama-3.2-11b-vision-abliterated` | Llama 3.2 11B Vision Instruct Abliterated | `case01/Llama-3.2-11B-Vision-Instruct-abliterated-gguf` | `llama-3.2-11B-vision_Q8_0.gguf` | 9.2 | Visual novel CG critique, descriptive storytelling from images, and multi-turn visual chat |
| `internvl2.5-8b` | InternVL 2.5 8B (SOTA Dense Vision & OCR) | `OpenGVLab/InternVL2_5-8B` | - | 8.5 | Dense document parsing, full UI layout inspection, and visual novel game audits |
| `moondream2` | Moondream2 (1.86B Ultra-Fast VLM) | `vikhyatk/moondream2` | - | 3.5 | Quick visual inspection, image QA, and real-time captioning |
| `qwen2-vl-2b` | Qwen2-VL 2B Instruct (Dynamic Resolution) | `Qwen/Qwen2-VL-2B-Instruct` | - | 4.5 | GUI automation, document parsing, and agent visual perception |
| `qwen2.5-vl-3b` | Qwen2.5-VL 3B Instruct (SOTA Compact VLM) | `Qwen/Qwen2.5-VL-3B-Instruct` | - | 5.8 | High-precision document extraction, code transcription from UI, and chart analysis |
| `minicpm-v-2_6` | MiniCPM-V 2.6 (8B High-Res Multi-Image SOTA) | `openbmb/MiniCPM-V-2_6` | - | 8.5 | Complex architectural diagrams, high-density blueprints, and dense mathematical OCR |
| `internvl2.5-4b` | InternVL 2.5 4B (SOTA UI Grounding & OCR) | `OpenGVLab/InternVL2_5-4B` | - | 4.5 | Screen inspection, visual novel text box verification, and UI automation |
| `pixtral-12b` | Pixtral 12B (Mistral 128k Multi-Image VLM) | `mistralai/Pixtral-12B-2409` | - | 7.8 | Multi-scene character consistency checking, art book analysis, and complex game asset audits |
| `qwen2.5-vl-72b` | Qwen2.5-VL 72B Instruct (42GB VRAM • Frontier Visual Agent SOTA) | `Qwen/Qwen2.5-VL-72B-Instruct` | - | 42.0 | Modal A100-80GB deep multimodal analysis, full game screen audits, and enterprise document vision |

## Speculative Draft Models
| ID | Name | Repo | File / Quant | Size (GB) |
|---|---|---|---|---|
| `qwen2.5-coder-1.5b` | Qwen 2.5 Coder 1.5B (Speculative Draft) | `Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF` | `qwen2.5-coder-1.5b-instruct-q4_k_m.gguf` | 1.2 |
| `qwen2.5-coder-3b` | Qwen 2.5 Coder 3B (High-Acceptance Draft) | `Qwen/Qwen2.5-Coder-3B-Instruct-GGUF` | `qwen2.5-coder-3b-instruct-q4_k_m.gguf` | 2.2 |
| `llama-3.2-1b` | Llama 3.2 1B (Llama Speculative Draft) | `bartowski/Llama-3.2-1B-Instruct-GGUF` | `Llama-3.2-1B-Instruct-Q4_K_M.gguf` | 0.8 |
| `llama-3.2-3b` | Llama 3.2 3B (Llama High-Acceptance Draft) | `bartowski/Llama-3.2-3B-Instruct-GGUF` | `Llama-3.2-3B-Instruct-Q4_K_M.gguf` | 2.1 |

## Voice & TTS Models
| ID | Name | Repo | Size (GB) | Recommended For |
|---|---|---|---|---|
| `kokoro-82m` | Kokoro-82M (20x Real-Time CPU Voice) | `hexgrad/Kokoro-82M` | 0.45 | Real-time voice chat, conversational agents, and audiobooks |
| `f5-tts` | F5-TTS (DiT Flow Matching Voice Clone) | `SWivid/F5-TTS` | 1.2 | Custom character voices, instant voice cloning, and expressive podcasting |
| `cosyvoice2-0.5b` | CosyVoice 2 (150ms Streaming TTFA Voice) | `FunAudioLLM/CosyVoice2-0.5B` | 1.5 | Live interactive voice assistants and phone call agents |
| `xtts-v2` | Coqui XTTS v2 (17 Languages Voice Clone) | `coqui/XTTS-v2` | 1.8 | International voice translation and multilingual NPCs |
| `bark-small` | Suno Bark Small (Expressive Generative Speech) | `suno/bark-small` | 0.9 | Dramatic narration, expressive audio drama, and lifelike emotional gaming NPCs |

## Image, 3D & Video Diffusion
| ID | Name | Repo | File / Quant | Size (GB) | Recommended For |
|---|---|---|---|---|---|
| `sd-turbo` | SD-Turbo (3.8GB VRAM • 1-step Fast Art) | `stabilityai/sd-turbo` | - | 3.8 | Real-time thumbnail generation, sprite drafting, and instant UI art |
| `sdxl-turbo` | SDXL-Turbo (6.5GB VRAM • SOTA 1024x1024 Art) | `stabilityai/sdxl-turbo` | - | 6.5 | Production illustration, game concept art, and high-resolution backgrounds |
| `sdxl-lightning` | SDXL-Lightning (6.5GB VRAM • 2-4 Step Fast SOTA) | `ByteDance/SDXL-Lightning` | - | 6.5 | Rapid prototyping, game asset rendering, and high-res concept art |
| `animagine-xl-3.1` | Animagine XL 3.1 (6.6GB VRAM • SOTA Anime/Art Uncensored) | `cagliostrolab/animagine-xl-3.1` | - | 6.6 | Game character art, concept design, illustrations, and unconstrained creative workflows |
| `mobius` | Mobius DPO (6.6GB VRAM • SOTA Photorealism Uncensored) | `stablediffusionapi/mobius` | - | 6.6 | Cinematic wallpapers, hyper-detailed fantasy art, and book covers |
| `realvisxl-v4` | RealVisXL V4.0 (6.6GB VRAM • SOTA Cinema/Anatomy Uncensored) | `SG161222/RealVisXL_V4.0` | - | 6.6 | Photorealistic portraits, real-world scenes, and cinematic lighting studies |
| `realvisxl-v5` | RealVisXL V5.0 (6.6GB VRAM • SOTA Photorealism & Cinema) | `SG161222/RealVisXL_V5.0` | - | 6.6 | Photorealistic portraits, real-world scenes, and cinematic lighting |
| `flux-1-schnell` | FLUX.1-schnell (23.8GB VRAM • 12B Giant DiT Kaggle 30GB) | `black-forest-labs/FLUX.1-schnell` | - | 23.8 | Kaggle Dual-T4 maximum image generation, posters with typography, and complex scenes |
| `flux-dev-uncensored` | FLUX.1-dev Abliterated V2 GGUF (10.5GB VRAM • 12B Uncensored Q4_K_M) | `t8star/flux.1-dev-abliterated-V2-GGUF` | `T8-flux.1-dev-abliterated-V2-GGUF-Q4_K_M.gguf` | 10.5 | Unrestricted 12B FLUX generation on Colab T4, L4, or Kaggle Dual-T4 |
| `flux-uncensored-v2` | Chroma1-HD GGUF (10.2GB VRAM • 8.9B Uncensored Apache-2.0) | `silveroxides/Chroma1-HD-gguf` | `Chroma1-HD-Q4_K_S.gguf` | 10.2 | Unrestricted creative & character generation on Colab T4 or Kaggle |
| `illustrious-xl` | Illustrious-XL v2.0 (6.8GB VRAM • SOTA Anime 1536x1536) | `OnomaAIResearch/Illustrious-XL-v2.0` | - | 6.8 | Visual novel character sprites, event CGs, anime illustrations, and game wallpapers |
| `illustrious-xl-v2` | Illustrious-XL v2.0 Diffusers (6.8GB VRAM • Native 1536x1536) | `Jommarn/Illustrious-XL-v2.0` | - | 6.8 | Visual novel character sprites, event CGs, anime illustrations |
| `noobai-xl` | NoobAI-XL V-Pred (7.0GB VRAM • Modern Anime Aesthetic) | `Laxhar/noobai-XL-Vpred-1.0` | - | 7.0 | Dynamic action visual novel scenes, battle sprites, and cover illustrations |
| `noobai-xl-vpred` | NoobAI-XL V-Pred 1.0 (7.0GB VRAM • V-Pred Zero-SNR SOTA Anime) | `Laxhar/noobai-XL-Vpred-1.0` | - | 7.0 | Dynamic action visual novel scenes, battle sprites, and cover illustrations |
| `pony-v6-xl` | Pony Diffusion V6 XL (6.8GB VRAM • Uncensored Character Master) | `stablediffusionapi/Pony-Diffusion-V6-XL` | - | 6.8 | Mature visual novel scenes, intimate character interactions, and customized LoRA workflows |
| `sd-3.5-medium` | SD 3.5 Medium (5.5GB VRAM • 2.5B MMDiT Fast Art) | `stabilityai/stable-diffusion-3.5-medium` | - | 5.5 | Game logos, item icons with text, environmental signs, and UI assets |
| `flux-1-dev` | FLUX.1 [dev] (32GB VRAM • 12B Guidance DiT Modal A100) | `black-forest-labs/FLUX.1-dev` | - | 32.0 | Modal A100-80GB / H100 studio-grade key art, book covers, and high-fidelity concept design |
| `trellis-3d` | Microsoft TRELLIS (24GB VRAM • SOTA Image-to-3D GLB/Gaussian) | `microsoft/TRELLIS-image-large` | - | 24.0 | Modal A10G / A100 instant 3D asset generation, game development, and VR props |
| `hunyuan3d-2` | Tencent Hunyuan3D-2.0 (32GB VRAM • High-Res 3D Mesh Studio) | `tencent/Hunyuan3D-2` | - | 32.0 | Modal A100-80GB game-ready 3D character and environment production |
| `wan2.1-14b-video` | Wan2.1 14B (36GB VRAM • SOTA Flow DiT Video Generator) | `Wan-AI/Wan2.1-T2V-14B` | - | 36.0 | Modal A100-80GB / H100 cinematic video cutscenes, animated character portraits, and trailers |
| `hunyuan-video` | Tencent HunyuanVideo (40GB VRAM • 13B DiT Video SOTA) | `tencent/HunyuanVideo` | - | 40.0 | Modal A100-80GB high-fidelity character animations and cinematic video production |

## Sampling Profiles (De-Assistantized & Sub-2-Bit Models)
| Model ID | Temp | Min-P | Top-K | Repeat Penalty | Tuning Notes |
|---|---|---|---|---|---|
| `qwen3.8-35b-uncensored` | 0.6 | 0.08 | 30 | 1.08 | Reasoning MoE; keep temp low to prevent routing thrashing. |
| `qwen3.8-27b-humanlike` | 0.85 | 0.07 | 40 | 1.12 | De-assistantized humanlike prose; avoid assistant system boilerplate. |
| `ternary-bonsai-2-27b` | 0.7 | 0.08 | 40 | 1.08 | Sub-2-bit ternary (PQ2_0/PTQ1_0); requires Min-P truncation + PrismML fork. |
| `magnum-12b-kto` | 0.75 | 0.1 | 0 | 1.05 | Top-K disabled; rely on Min-P 0.10 for vibrant prose. |
| `celeste-12b` | 0.7 | 0.08 | 50 | 1.06 | Mistral Nemo base; keep T <= 0.75 to avoid delirium. |
| `stheno-8b-v3.2` | 0.8 | 0.05 | 40 | 1.1 | Elevated repeat_penalty prevents multi-turn dialogue loops. |
| `orcabonsai-27b-uncensored` | 0.7 | 0.08 | 40 | 1.08 | Runtime refusal-steering vector; throttle alpha->0.0 for JSON/math. |
| `qwen2.5-coder-32b` | 0.25 | 0.05 | 40 | 1.05 | Low temperature for deterministic coding & diffs. |
| `qwen2.5-coder-14b` | 0.25 | 0.05 | 40 | 1.05 | Low temperature for deterministic coding & diffs. |
| `qwen2.5-coder-7b` | 0.25 | 0.05 | 40 | 1.05 | Low temperature for fast single-T4 coding. |
