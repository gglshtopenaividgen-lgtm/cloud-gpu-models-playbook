# Cloud AI Provider Model Health & Latency Registry

> **LOCATION**: `context/model_benchmarks.md` & `benchmarks/`  
> **UPDATED**: August 2026 (Universe Benchmark: 59/84 Online, Avg Latency: 1418ms)

---

## 1. Benchmark Execution Guide

### Local Benchmark (Node.js — Paced & Complete Catalog)
```bash
node benchmarks/test_full_universe.mjs
```

### Fast Local Health Check (Node.js)
```bash
node benchmarks/benchmark_local.mjs
```

---

## 2. Live Measured Latency Rankings & Fallback Tiers

### 🟢 Tier 1 — Ultra-Fast Sub-600ms Pool (Interactive UI & Card Generation)
| Provider | Model Slug | Latency | HTTP | Recommended Use Case |
|---|---|---|---|---|
| **Groq** | `openai/gpt-oss-120b` | **145 ms** | 200 | Flagship fast generalist & reasoning |
| **Groq** | `openai/gpt-oss-20b` | **149 ms** | 200 | Instant classification & intent detection |
| **Groq** | `qwen/qwen3.6-27b` | **195 ms** | 200 | Fast MoE reasoning |
| **OpenRouter (Free)** | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | **228 ms** | 200 | Free high-speed reasoning |
| **OpenRouter (Free)** | `nvidia/nemotron-3-super-120b-a12b:free` | **237 ms** | 200 | Super fast 120B model |
| **Groq** | `qwen/qwen3.8-27b` | **373 ms** | 200 | Alibaba 27B dense flagship on Groq |
| **OpenRouter (Free)** | `nvidia/nemotron-3-ultra-550b-a55b:free` | **380 ms** | 200 | 550B MoE giant (1M context) |
| **Cloudflare Workers AI** | `@cf/meta/llama-3.2-3b-instruct` | **418 ms** | 200 | Edge-native micro model |
| **Mistral AI** | `ministral-3b-2512` | **451 ms** | 200 | Ultra-fast lightweight generalist |
| **Mistral AI** | `codestral-2508` | **459 ms** | 200 | Code generation & syntax fixing |
| **Cohere (v2)** | `command-r7b-12-2024` | **471 ms** | 200 | Fast conversational chat |
| **Mistral AI** | `ministral-14b-2512` | **494 ms** | 200 | Compact high-intelligence agent |
| **Mistral AI** | `devstral-2512` | **524 ms** | 200 | Autonomous software engineering |
| **Mistral AI** | `ministral-8b-2512` | **530 ms** | 200 | Balanced 8B edge assistant |
| **Mistral AI** | `mistral-medium-3-5` | **548 ms** | 200 | Frontier multimodal reasoning |
| **Mistral AI** | `mistral-small-latest` | **563 ms** | 200 | Small general flagship |
| **Mistral AI** | `mistral-medium-latest` | **567 ms** | 200 | Medium general flagship |

### 🟡 Tier 2 — Balanced Inference (600ms – 1,800ms)
| Provider | Model Slug | Latency | HTTP | Recommended Use Case |
|---|---|---|---|---|
| **Mistral AI** | `codestral-latest` | **601 ms** | 200 | Flagship code generation |
| **Mistral AI** | `mistral-small-2603` | **601 ms** | 200 | Mistral small 2603 revision |
| **Cloudflare Workers AI** | `@cf/meta/llama-3.2-1b-instruct` | **608 ms** | 200 | 1B micro model |
| **Cerebras** | `gemma-4-31b` | **614 ms** | 200 | Dense multimodal 31B fast engine |
| **Mistral AI** | `mistral-large-latest` | **633 ms** | 200 | 675B MoE generalist flagship |
| **Google AI Studio** | `gemini-flash-lite-latest` | **640 ms** | 200 | Gemini flash lite flagship |
| **Cerebras** | `gpt-oss-120b` | **751 ms** | 200 | 120B MoE reasoning engine |
| **Hugging Face** | `Qwen/Qwen3.8-27B` | **763 ms** | 200 | Serverless dense Qwen 3.8 |
| **Cloudflare Workers AI** | `@cf/meta/llama-3.1-8b-instruct` | **780 ms** | 200 | 8B edge model |
| **Dahl Inference** | `moonshotai/Kimi-K2.6` | **792 ms** | 200 | Decentralized Kimi 2.6 |
| **Google AI Studio** | `gemini-3.5-flash-lite` | **796 ms** | 200 | Gemini 3.5 lightweight |
| **Cloudflare Workers AI** | `@cf/meta/llama-3.1-70b-instruct` | **851 ms** | 200 | 70B edge model |
| **LLM7.io** | `codestral-latest` | **905 ms** | 200 | Codestral proxy |
| **Cohere (v2)** | `command-r-plus-08-2024` | **928 ms** | 200 | High-reasoning enterprise chat |
| **Google AI Studio** | `gemini-3-flash-preview` | **975 ms** | 200 | Gemini 3.0 flash preview |
| **Mistral AI** | `mistral-large-2512` | **1011 ms** | 200 | Enterprise MoE flagship |
| **Cloudflare Workers AI** | `@cf/deepseek-ai/deepseek-r1-distill-qwen-32b` | **1034 ms** | 200 | Distilled reasoning model |
| **Cohere (v2)** | `command-r-08-2024` | **1041 ms** | 200 | Command R standard |
| **IAMHC** | `step-explore` | **1081 ms** | 200 | StepFun 1M internal (Claude format, ⚠️ ¥21.9/req) |
| **Google AI Studio** | `gemini-flash-latest` | **1120 ms** | 200 | Standard Gemini flash |
| **Bluesminds** | `deepseek-v4-pro` | **621 ms** | 200 | Fast MoE reasoning ($3.48/$12.11) |
| **B.AI** | `deepseek-v4-flash-vision-exp` | **990 ms** | 200 | Multimodal flash vision |
| **Bluesminds** | `gpt-5.3-codex` | **1000 ms** | 200 | High TPS Codex model (101 TPS, $3.5/$24.5) |
| **B.AI** | `qwen3.8-flash` | **1150 ms** | 200 | Qwen 3.8 Flash (limited-time free) |
| **B.AI** | `glm-5.3-flash` | **1180 ms** | 200 | GLM 5.3 Flash (limited-time free) |
| **Google AI Studio** | `gemini-3.1-flash-lite-preview` | **1141 ms** | 200 | Gemini 3.1 flash lite |
| **Google AI Studio** | `gemma-4-26b-a4b-it` | **1148 ms** | 200 | Open Gemma 4 26B |
| **Google AI Studio** | `gemma-4-31b-it` | **1195 ms** | 200 | Open Gemma 4 31B |
| **Dahl Inference** | `MiniMaxAI/MiniMax-M2.7` | **1229 ms** | 200 | MiniMax 2.7 generalist |
| **Bynara** | `deepseek-v4-flash` | **1378 ms** | 200 | Bynara DeepSeek proxy |
| **Hugging Face** | `deepseek-ai/DeepSeek-V4-Flash` | **1464 ms** | 200 | Fast serverless DeepSeek MoE |
| **B.AI** | `hy3` | **1580 ms** | 200 | Tencent Hy3, clean direct outputs |
| **Hugging Face** | `zai-org/GLM-5.3-Flash` | **1664 ms** | 200 | GLM 5.3 Flash |
| **Bluesminds** | `gpt-5.2-chat` | **1700 ms** | 200 | Generalist chat ($2.5/$12.5) |
| **Google AI Studio** | `gemini-3.7-flash` | **1760 ms** | 200 | **Next-Gen Flagship Gemini 3.7** |

### 🟠 Tier 3 — High Quota, MoE Cold Starts & Background Tasks (> 1,800ms)
| Provider | Model Slug | Latency | HTTP | Recommended Use Case & Notes |
|---|---|---|---|---|
| **IAMHC** | `step-router-v1` | **2026 ms** | 200 | StepFun router (⚠️ ¥73/1M token drain) |
| **Bynara** | `agnes-2.5-flash` | **2118 ms** | 200 | Agnes 2.5 agent |
| **IAMHC** | `kat-coder-pro-v2.5` | **2566 ms** | 200 | **⚡ BEST IAMHC VALUE**: ¥0.1825/req (~109k calls on 20k balance) |
| **B.AI** | `mimo-v2.5` | **2500 ms** | 200 | Xiaomi MoE reasoning (limited-time free) |
| **Hugging Face** | `deepseek-ai/DeepSeek-V4-Flash-0731` | **2625 ms** | 200 | DeepSeek Flash checkpoint |
| **OpenRouter (Free)** | `minimax/minimax-m3:free` | **2627 ms** | 200 | MiniMax M3 free tier |
| **IAMHC** | `sensenova-6.8-flash-lite` | **2656 ms** | 200 | SenseTime flash lite (¥21.9/1M tokens) |
| **Bynara** | `agnes-2.0-flash` | **2720 ms** | 200 | Agnes 2.0 agent |
| **LLM7.io** | `deepseek-v4-flash` | **3150 ms** | 200 | DeepSeek proxy |
| **Bluesminds** | `gpt-5.6-terra` | **3200 ms** | 200 | GPT-5.6 series ($1.5/$15 per 1M) |
| **Bluesminds** | `gpt-5.6-luna` | **3800 ms** | 200 | Codex variant ($5/$30 per 1M) |
| **Google AI Studio** | `gemini-3.6-flash` | **3181 ms** | 200 | Gemini 3.6 flash engine |
| **Groq** | `groq/compound` | **1642 ms** | 200 | Multi-agent compound router |
| **Groq** | `allam-2-7b` | **3699 ms** | 200 | Multilingual specialized |
| **OpenRouter (Free)** | `poolside/laguna-s-2.1:free` | **4883 ms** | 200 | Coding specialist (262k context) |
| **TokenFaucet** | `gpt-5.6-luna` | **5045 ms** | 200 | Synthetic free endpoint |
| **Bynara** | `mistral-large` | **10474 ms** | 200 | Slow proxy route |
| **IAMHC** | `MiniMax-M3` | **26 s** (MoE) | - | SWE-Bench 59% (¥1.46/req) |
| **IAMHC** | `mimo-v2.5` | **37 s** (MoE) | - | Xiaomi 1T MoE (¥0.365/req) |
| **IAMHC** | `Qwen3.8-27B` | **48 s** (MoE) | - | Alibaba 27B Dense (¥3.431/req) |
| **IAMHC** | `DeepSeek-V4-Flash` | **52 s** (MoE) | - | 284B MoE (¥3.285/req) |
| **IAMHC** | `auto` | **75 s** (Router) | - | Auto router (¥8.76/1M tokens) |
| **IAMHC** | `kimi-k3` | **73 s** (3T) | - | ⚠️ 3T Multimodal (¥18.98/req — wipes 20k balance in ~1,053 calls!) |
| **IAMHC** | `step-3.7-flash` | **115 s** (MoE) | - | ⚠️ High latency & ¥87.6/1M tokens |
| **IAMHC** | `step-image-edit-2` | **6 s** (Image) | - | 🛑 ¥160.6/1M/img (Calling ~124 times wipes 20k balance!) |

---

## 3. Model Routing & Datacenter ASN Rules

1. **Edge-Native Inference (Cloudflare Workers)**:
   - Next.js Edge routes dispatch directly to **Groq** (`openai/gpt-oss-120b`, `qwen/qwen3.6-27b`, `qwen/qwen3.8-27b`) and **Cerebras** (`gpt-oss-120b`, `gemma-4-31b`).
   - Cloudflare residential/anycast IP egress ensures **0% WAF blocking rate**.

2. **Server-Side VM Gateway (Azure VM-1 `litellm-gateway-vm`)**:
   - VM-1 Gateway (`custom_gateway.py`) routes strictly through **Datacenter-Safe Providers**:
     - `Mistral AI` (`ministral-3b-2512`, `codestral-2508`, `mistral-small-latest`, `mistral-medium-3-5`, `mistral-large-latest`)
     - `Google Gemini` (`gemini-flash-lite-latest`, `gemini-flash-latest`, `gemini-3.7-flash`)
     - `Cohere v2` (`command-r7b-12-2024`, `command-r-plus-08-2024`)
     - `Hugging Face` (`Qwen/Qwen3.8-27B`, `deepseek-ai/DeepSeek-V4-Flash`)
     - `Bynara` (`deepseek-v4-flash`, `agnes-2.5-flash`)
     - `OpenRouter Free Pool` (`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`, `nvidia/nemotron-3-ultra-550b-a55b:free`)
     - `IAMHC` (`kat-coder-pro-v2.5`, `mimo-v2.5`, `sensenova-u1.5-lite`)
     - `Cloudflare Workers AI` (`@cf/meta/llama-3.2-3b-instruct`, `@cf/meta/llama-3.1-70b-instruct`)
