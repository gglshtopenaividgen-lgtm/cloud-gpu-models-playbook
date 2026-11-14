---
name: external-resource
description: "Orchestrate external compute, frontier AI, and model testing: Google Flow batch asset generation, Gemini Deep Research, Cloud GPU/TPU pipelines, and multi-provider model benchmarks across 55+ models."
compatibility: Windows 11 PowerShell, Python 3.14+, Modal, Colab, Kaggle, Node.js
metadata:
  version: 2.1.0
  type: universal-resource-orchestrator
  scope: Universal
---
# External Resource Orchestrator & Frontier AI Compute Engine

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE (ZERO-PASSIVE-READING)**:
> Bundled scripts in `scripts/` are **executable software tools**, NOT reading material.
> When this skill is triggered, **EXECUTE the relevant script immediately** via `run_command`.
> **STRICT PROHIBITION**: NEVER call `view_file` on scripts in `scripts/` or explain their source code to the user unless explicitly ordered to edit or debug the script itself.
> Universal scripts can and must be executed from **ANY project workspace** by calling their absolute path:
> `python <BRAIN_ROOT>\.agents\skills\external-resource\scripts\<script_name> ...`


> **Universal Operating Protocol for Gemini Flow Batch Studios, Multi-Account Deep Research, Spark Reasoning, Ephemeral Cloud GPU/TPU Clusters, and Multi-Provider Model Benchmarks**  
> **Master Reference for 2D Art, 3D Meshes, Music/Audio, Video, Frontier Research, and 55+ Model Benchmarks**

---

## 1. Architectural Pillars & Modality Routing

| Pillar | Core Capability | Target Infrastructure | Primary Asset / Output |
|---|---|---|---|
| **Gemini Flow Batch Studio** | Automated batch generation via high-density manifest parsers with regex delimiter pairing, queue throttling, and automatic ZIP bundling. | Google Flow (Multiple Gemini Pro Accounts) | 2D Game Sprites, Concept Art, Music Tracks, Soundscapes, Video Loops |
| **Multi-Account Deep Research** | Deep literature synthesis, competitive benchmarking, source grounding, and multi-perspective verification. | Gemini Pro Deep Research & Google Spark | Architecture Plans, SOTA Landscape Matrices, Grounded Technical Specs |
| **Spark High-Density Reasoning** | Mathematical derivations, algorithm design, tokenizer benchmarks, and multi-agent topology proofs. | Gemini Spark (via structured cognitive prompts) | Dense Algorithmic Blueprints, Token Optimization, Zero-Slop Math Models |
| **Serverless Cloud GPU (Modal)** | Zero-idle millisecond billing ($30/mo free credit), scale-to-zero containers, pre-warmed weights in `@modal.volume`. | Modal Labs (A100-80GB, L4, T4) | FLUX.1 Image Farms, Trellis / InstantMesh 3D Pipelines, CogVideoX Video |
| **Persistent Batch GPU/TPU (Kaggle)** | 30 GPU-hours/week (Dual Tesla T4 30.7GB total VRAM) & TPU v3-8; 12-hour batch run sessions. | Kaggle Notebooks (Air-Gapped Batch Mode) | Bulk Dataset Synthesis, MusicGen Batch Audio, Custom LoRA / Mesh Baking |
| **Rapid Prototyping GPU (Colab)** | Ephemeral T4 GPU (15GB VRAM), rolling 12–72h cool-off, interactive Gradio / UI output. | Google Colab (Free Tier) | TripoSR Single-Image to 3D, Rapid Model Verification, Interactive Testbeds |
| **Google AI Studio Full-Platform** | 2M-token context reasoning, Gemini 4 Argon execution, automated <> Get code SDK harvesting, App Builder with live sandbox, and native Export to Antigravity. | Google AI Studio (`aistudio.google.com` via Argon Bridge) | Full-Stack Web/Android Apps, SDK Code Snippets, 2M-Token Ingestion |
| **Model Benchmark & Health** | Asynchronous multi-provider latency, TTFT, and error diagnostics across 55+ AI models. | Multi-Provider APIs (Groq, Mistral, Gemini, OpenRouter) | Live Latency & Error Rate Reports, Tier Fallback Tables |

```mermaid
flowchart TD
    UserGoal["Asset Generation or Research Goal"] --> ModalityCheck{"Determine Modality & Scope"}
    
    ModalityCheck -->|2D Art, Music, Video, Bulk Prompts| Flow["Gemini Flow Batch Studio<br>(Multi-Account Rotation)"]
    ModalityCheck -->|Deep Research & Architecture| DeepRes["Gemini Pro Deep Research & Spark<br>(High-Density Cognitive Prompt)"]
    ModalityCheck -->|3D Meshes / Specialized Neural Models| CloudGPU{"Select GPU/TPU Platform"}
    
    CloudGPU -->|Interactive / 1-Off 3D| Colab["Google Colab (T4 15GB)<br>TripoSR / Gradio Export"]
    CloudGPU -->|Large Batch / Zero-Cost| Kaggle["Kaggle (2x T4 30.7GB / TPU v3-8)<br>Air-Gapped Batch Pipeline"]
    CloudGPU -->|Production Serverless / Fast API| Modal["Modal Labs (A100-80GB)<br>Scale-to-Zero @modal.web_endpoint"]

    Flow --> ZipOutput["ZIP Bundle Download & Project Integration"]
    DeepRes --> ContextDoc["Ingest into context/ideas.md & constraints.md"]
    Colab & Kaggle & Modal --> MeshOutput["GLB / OBJ / Lossless Audio to R2 Storage"]
```

---

## 2. Gemini Flow Tool Architecture & Batch Asset Studio

### 2.1 The Multi-Account Advantage
When working with Google Flow, leveraging **multiple Gemini Pro accounts** unlocks virtually unlimited high-throughput generation quotas:
- Rotate between account workspaces across generation batches to completely bypass daily rate limits and credit exhaustion.
- Group prompts by category or modality per account session to maintain coherent stylistic latent trajectories.

### 2.2 Dual-Mode Manifest Parser Design
A robust batch tool must accept both structured JSON and human-readable delimited text blocks.

#### CRITICAL Architectural Invariant (Regex Delimiter Pairing Bugfix)
> [!CAUTION]
> **Past Defect**: Naive string splitting (e.g. `rawInput.split("===")`) splits at every occurrence, causing headers and prompt bodies to separate into duplicate phantom entries (e.g. producing 6 unintended assets from 3 inputs).
> **Mandated Fix**: Always use strict regex pairing that captures the header and binds it directly to its following prompt block until the next header delimiter:

```python
import re

MANIFEST_REGEX = re.compile(
    r'===\s*([^\n]+?)\s*===\s*\n?([\s\S]*?)(?=(?:===\s*[^\n]+?\s*===)|\Z)',
    re.MULTILINE
)

def parse_delimited_manifest(raw_text: str) -> list[dict]:
    assets = []
    for match in MANIFEST_REGEX.finditer(raw_text.strip()):
        header = match.group(1).strip()
        body = match.group(2).strip()
        if not header or not body:
            continue
            
        # Parse inline attributes like [Type: Image] [Model: Imagen-3] [Aspect: 16:9]
        attributes = {}
        attr_matches = re.findall(r'\[([a-zA-Z0-9_-]+)\s*:\s*([^\]]+)\]', body)
        for k, v in attr_matches:
            attributes[k.strip().lower()] = v.strip()
            
        cleaned_prompt = re.sub(r'\[[a-zA-Z0-9_-]+\s*:\s*[^\]]+\]', '', body).strip()
        
        assets.append({
            "id": header,
            "prompt": cleaned_prompt,
            "type": attributes.get("type", "image"),
            "model": attributes.get("model", "imagen-3"),
            "aspect_ratio": attributes.get("aspect", "1:1"),
            "negative_prompt": attributes.get("negative", ""),
            "seed": int(attributes["seed"]) if "seed" in attributes else None
        })
    return assets
```

### 2.3 Prompt Structuring for Flow Modalities

#### A. 2D Game Sprites & Isometric World Assets
- **Portrait vs Sprite Separation**: If generating character sprites, explicitly forbid portrait crops. Specify camera distance, perspective, and full-body isolation:
  - *Recommended Positive*: `"Full body standing action sprite of a shadow awakener assassin, isometric 45-degree angle, entire boots and head visible, centered, isolated on solid pitch black #000000 background, crisp pixel borders, zero drop shadow, 16-bit game asset style."`
  - *Mandatory Negative*: `"portrait, headshot, bust, close-up, cropped legs, cutoff feet, blur, soft gradient background, photo frame, text, watermark"`.

#### B. Ambient Audio & Music Tracks
- Google Flow audio modalities require tempo, instrumentation, key, and mood descriptors:
  - *Prompt*: `"Dark synthwave background music, 110 BPM, analog Roland Juno-106 arpeggios, pulsing sub-bass, cyberpunk ambient atmosphere, looping electronic track for nocturnal city exploration, lossless 48kHz production."`
  - *Negative Prompt*: `"vocals, speech, singing, harsh distortion, clipping, muddy frequencies"`.

#### C. Video Loops & Micro-Cinematics
- Define camera trajectory, motion cadence, and temporal continuity:
  - *Prompt*: `"Cinematic seamless loop of neon rain falling on an asphalt alleyway in Seoul, slow pan forward, volumetric streetlamp mist, 24fps smooth motion, cyberpunk noir realism, zero flickering."`

### 2.4 Asset Studio Pro Directory Architecture & Manifest Specification
The production asset pipeline uses **Asset Studio Pro** in Google Flow, governed by the following strict syntax:

```text
=== ID: [uid] | TYPE: [image|video] | CHAR: [name] | ASPECT: [ratio] | FOLDER: [path] | MODEL: [model] | STYLE: [prefix] | NEGATIVE: [neg] | MUTED: [true|false] ===
[Detailed Prompt on the following lines]
---
```

#### A. Directory Architecture & File Arrangement (NO ZIP FILES):
In Asset Studio Pro, images and videos are **NOT** packaged into a `.ZIP` archive (sandboxed browser security blocks raw `.zip` downloads).
Instead, assets are exported directly through the filesystem using an organized **Directory Path Pipeline**:
1. Every asset includes a structured `FOLDER` tag (e.g. `FOLDER: characters/hero/portraits`, `ui/icons/weapons`, `environments/exterior`).
2. The export engine encodes the folder directory directly into the exported filename using double underscores:
   - **Format**: `[folder]__[subfolder]__[filename].[ext]`
   - **Example**: `characters__neon_voyager__portraits__hero_portrait_01.png`
3. A companion `package_manifest.json` is downloaded alongside all media items, providing full relative directory paths for 1-click import into game engines (Unreal, Unity, Godot) and render pipelines.

#### B. Header Directives & Parameters:
- `ID`: Unique alphanumeric slug with underscores (e.g. `hero_idle_01`, `relic_compass_01`).
- `TYPE`: Explicitly `"image"` or `"video"` (default: `image`).
- `CHAR`: Optional exact name of an entity registered in the Character Vault (e.g. `"Neon Voyager"`). Auto-injects persona, bio, and visual reference conditioning.
- `ASPECT`: Images: `1:1`, `16:9`, `9:16`, `4:3`, `3:4` (default: `1:1`). Videos: `16:9`, `9:16` (default: `16:9`).
- `FOLDER`: Target organization directory structure (e.g. `characters/hero/portraits`, `environments/citadel`, `ui/icons/relics`).
- `MODEL`: Canonical engine override:
  - Images: `🍌 Nano Banana Pro` (default), `🍌 Nano Banana 2.1`, `🍌 Nano Banana 2 Lite`
  - Videos: `Omni 1.1 Flash` (default), `Veo 3.1 - Quality`, `Veo 3.1 - Fast`, `Veo 3.1 - Lite`
- `STYLE`: Optional local style prefix prepended to this specific asset.
- `NEGATIVE`: Optional negative prompt tokens.
- `MUTED`: Video playback audio preview mute state (`true` or `false`).

#### C. Live Feed: Character Ingestions:
Dedicated reactive telemetry feed in the Character Forge:
- **Real-Time Consistency Inspection**: Isolates all assets marked with `CATEGORY: characters` so directors verify face geometry, costume fidelity, and artistic consistency side-by-side without sifting through props/environments.
- **In-Place Diagnostics & Fixes**: Creators trigger instant AI prompt refinement, re-synthesize flawed renders, or adjust model overrides on a per-character basis.

#### D. Active Safety & Stylistic Remapping Dictionary (44 Entries):
When Safe Mode is enabled in Asset Studio Pro, sensitive fantasy terms are automatically remapped:
- "poison" -> "mystic venom" | "blood" -> "crimson ichor" | "bloody" -> "crimson-soaked" | "killer" -> "cleaver"
- "murder" -> "extraction" | "death" -> "void" | "deadly" -> "lethal" | "toxic" -> "corrosive"
- "slaughter" -> "annihilation" | "massacre" -> "overwhelming defeat" | "execute" -> "finalize"
- "corpse" -> "fallen remnant" | "demon" -> "fiend" | "devil" -> "arch-fiend" | "satanic" -> "abyssal"
- "solo leveling" -> "high-fantasy hunter manhwa" | "shadow monarch" -> "void sovereign" | "warrior" -> "guardian"

#### B. Safe Prompting Rules & Trigger Word Avoidance:
Google's backend automatically flags violent, dark, or underage words, causing silent drops or `HTTP 0 / Error code 7`:
- **Underage Policy**: NEVER mention `17-year-old` or `high school student`. Replace with `youthful collegiate scholar` or `awakened prodigy`.
- **Harm & Violence**: Replace `deadly poison` with `emerald venom`, `blood` with `mystic ichor` or `crimson vitality fluid`, `killer` with `cleaver` or `slayer`, and `murder/mutiny` with `conspiracy/betrayal`.
- **IP / Trademark Filter**: Never use `Solo Leveling` or `S-Rank` in prompt text. Rely on the Global Style Prefix (`Korean webtoon hunter art style`).
- **Contraband / Demonic**: Replace `contraband` with `classified relic`, and `demon/demon king` with `abyssal monarch` or `void sovereign`.

#### C. Prompt Density & Anti-Timeout Optimization:
- **Character Cap**: Keep prompt bodies between **150 – 250 characters**. Overly long prompts (600+ chars) combined with the global style prefix trigger `Synthesis Timeout` or `Error code = 7 (batchexecute transport fault)`.
- Always conclude with clean boundary descriptors: `isolated on pure black background #000000, clean sharp edges`.
- Set batch throttle slider to **3.0s – 3.5s** to avoid Google API concurrency rate limits.

---

## 3. Gemini Deep Research & Google Spark Reasoning Protocol

### 3.1 Overcoming the Low-Effort Spark Failure Pattern
> [!IMPORTANT]
> **Known Past Mistake**: When given generic or multi-part underspecified prompts, Gemini Spark puts minimal cognitive effort into the response, outputting shallow bullet points or generic advice.
> **Mandate**: All prompts dispatched to Gemini Spark or Gemini Pro Deep Research must enforce the **High-Density Cognitive Prompt Framework**.

### 3.2 High-Density Prompt Synthesis Architecture
Every Spark prompt must contain these 5 structural layers:
1. **Role & Cognitive Identity**: Define Spark as a principal scientist / systems architect with zero tolerance for filler prose or AI slop.
2. **Context & Invariant Guardrails**: Explicitly state system constraints (e.g. 100% Free Tier, 500MB DB limit, memory footprint, zero egress).
3. **Multi-Perspective Thought Loop**: Direct Spark to execute explicit dialectical stress testing (The Architect, The Adversary, The Cost Guard).
4. **Concrete Derivation Directives**: Request mathematical calculations, token count trade-offs, pseudocode, and benchmark comparison tables.
5. **Strict Output Schema**: Mandate clean Markdown with forbidden patterns (e.g. forbid conversational greetings and filler prose).

*Use `scripts/spark_prompt_synthesizer.py` to compile prompts automatically.*

### 3.3 2-Tier Gemini 4 Argon Hybrid Router (`consult_argon.py` + Vertex AI API Fallback)

When deep reasoning, architecture planning, code review, or hypothesis testing requires **Gemini 4 Argon**:
- **Tier 1 (Default — $0-Token Browser Bridge)**: Connects to the 6 authenticated Google One AI Premium accounts (`Profile 14`, `13`, `16`, `7`, `8`, `9`) via `consult_argon.py`. Prioritizes live connected profiles with lowest usage, verifies `4 Argon` + `High Thinking`, attaches context files (`-f`), audits live 5-hour/weekly quotas, and **automatically deletes temporary automated chats from the sidebar by default (`--clean` is `True` by default)**.
- **Tier 2 (Fallback / Explicit Request — Google Cloud Vertex AI API)**: Routes to `gemini-4-argon` on Google Cloud Vertex AI (`<GCP_PROJECT_ID>` / `http://localhost:8088/v1`) via `consult_argon.py --api` or `<WORKSPACE_ROOT>\api_router\argon.py`.
  - **Automatic Failover**: Triggered automatically when all 6 Google One AI Premium browser accounts hit their 5-hour quota limit.
  - **Explicit Invocation**: Triggered immediately when the user explicitly requests to use the Argon API (`--api`).
- **ZERO SCRIPT READING & ZERO WRAPPERS**: Never call `read_file` on driver scripts and NEVER write intermediate wrapper scripts (`run_argon_query.py`). Execute `consult_argon.py` directly on Turn 1!

```powershell
# ==============================================================================
# CANONICAL 2-TIER ARGON INVOCATION (EXECUTE DIRECTLY VIA run_command ON TURN 1)
# ==============================================================================

# 1. Selective Context-Packed Consultation (DEFAULT: auto-packs Hermes RRF memory + Top-K constraints/ideas/mistakes + AST code slices into temp_read/argon_context_bundle.md and attaches via -f):
python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py "Review the attached context and answer all questions." --pack path/to/file.py:1-150 -o temp_read/review.md

# 1B. Manual File Attachment (-f):
python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py "Review the attached context and answer all questions." -f temp_read/context.md -o temp_read/review.md

# 2. Normal Prompt (Ideas, Architecture, Planning with High Thinking; auto-deletes chat after use):
python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py "Synthesize architectural strategy for X" -o temp_read/solution.md

# 3. Long / Multi-line Prompt File (--prompt-file):
python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py --prompt-file temp_read/prompt.md -o temp_read/solution.md

# 4. Deep Research (Exhaustive Grounded Investigation across 20+ Sources):
python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py "Exhaustive comparison of X vs Y" --deep-research -o temp_read/research.md

# 5. Tier-2 Vertex AI API Route (Use when explicitly requested by user OR when all 6 browser accounts hit quota):
python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py "Review the attached spec" -f temp_read/context.md --api -o temp_read/api_solution.md
# Direct Vertex AI CLI alternative:
python <WORKSPACE_ROOT>\api_router\argon.py -q "Review the attached spec" -f temp_read/context.md --thinking high

# 6. Live Fleet Telemetry (Check active leases & 5h/weekly quota across all 6 profiles):
python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py --status
```

---

## 4. Ephemeral Cloud GPU/TPU Deployment (Colab, Kaggle, Modal)

When specialized neural assets (3D meshes, custom LoRAs, text-to-video) exceed browser or edge capabilities, route to ephemeral cloud compute.

### 4.1 Platform Comparison & Selection Rule

| Modality / Task | Recommended Platform | Optimal Hardware | Ingress / Access Strategy | Session Limit |
|---|---|---|---|---|
| **Text-to-3D / Image-to-3D** (TripoSR, Trellis, InstantMesh) | **Google Colab** (Fast) or **Modal** (API) | Colab T4 (15 GB) or Modal A100 (80 GB) | In-notebook iframe (`7860`) / outbound relay or `@modal.web_endpoint` | Colab: ~4h / Modal: Pay-per-second ($0 idle) |
| **Batch 3D Mesh Baking & Remote LLM Serving** | **Kaggle Notebooks** | 2x Tesla T4 (30.7 GB total VRAM) | **Official First-Party Proxy**: `*.jupyter-proxy.kaggle.net` (`/api/kernels/<id>/channels`) + Novita relay (`https://<YOUR_DOMAIN>) or Air-Gapped Batch | 12 hours hard limit (`30` GPU-h/week std; **`45` GPU-h/week** linked to Colab Pro) |
| **High-Res Video Synthesis** (CogVideoX, Wan2.1, SVD) | **Modal Labs** | NVIDIA A100 (80 GB) or H100 | Serverless `@modal.web_endpoint` (CLI `modal deploy` only; `max_containers=1`, `scaledown_window=60`) | Millisecond billing (`$30/mo` included credit, `1024 GiB` Volumes free) |
| **Batch Soundscapes & Music** (MusicGen, AudioCraft) | **Kaggle** or **Colab** | Tesla T4 (15 GB) | Batch audio export to `.wav` / `.mp3` bundled into ZIP / Drive / GH Release | Free |

### 4.2 Strict Safety, Anti-Ban & Hardware Invariants
> [!IMPORTANT]
> Detailed platform truth tables, the 16 Inviolable Laws, self-healing pre-flight verification cells, and 4 ban-proof architectures are documented in [references/cloud_gpu_guardrails.md](references/cloud_gpu_guardrails.md).

1. **Zero Reverse Tunnels on Kaggle & Colab**: NEVER run `ngrok`, `cloudflared`, `playit.gg`, or SSH reverse proxies on Kaggle or Colab. Automated heuristics flag and permanently ban accounts for reverse tunneling.
2. **Native Ingress & Proxy Rules**:
   - **Modal**: CLI deploy only (`modal deploy`; Modal retired interactive notebooks). Enforce `max_containers=1`, `scaledown_window=60`, `1024 GiB` free Volume ceiling, and capture `subprocess.Popen` logs + active TCP health probes inside `@modal.web_server` so startup crashes don't stall into 900s 504 timeouts.
   - **Modal Pricing (`2026-11-01`) & L4 VRAM Math**: GPU rates/hr: `B300 $7.10`, `B200 $6.25`, `H200 $4.54`, `H100 $3.95`, `RTX PRO 6000 $3.03`, `A100-80GB $2.50`, `A100-40GB $2.10`, `L40S $1.95`, `A10G $1.10`, `L4 $0.80`, `T4 $0.59`, CPU `$0.0473/core/hr`. On 24 GB L4 (`~22.5 GB` usable), use `q4_0` KV cache (`20.74 GB <= 22.5 GB` for 32B `IQ4_XS`) and verify `llama-server` `-fa` / `--flash-attn` boolean/auto syntax (passing `"on"` crashes newer builds).
   - **Colab**: 🛑 **ZERO `share=True` / ZERO REVERSE TUNNELS**. `share=True` downloads `frpc` and triggers container bans. Also **never attempt to relay Colab Pro `/tun/m/...` headlessly** (requires Google OAuth cookies `SAPISID` and kills idle tabs). Use **In-Notebook Iframe** (`serve_kernel_port_as_iframe(7860)`), **Local Tarball Upload** via `colab-cli`, or **Batch to Drive** (`runtime.unassign()`).
   - **Colab Free T4 (`12.7 GB` Host RAM Ceiling) & Abliterated Image Stack**: Never download 24 GB FP16 Flux weights (triggers `SIGKILL 137`) or pass `BitsAndBytesConfig` to `FluxTransformer2DModel` (raises `NotImplementedError`; also never use unmerged PEFT repo `shauray/FLUX-UNCENSORED-merged`). Upgrade `torchao>=0.15.0` & `bitsandbytes>=0.48.0` before `import torch` (`HF_HOME=/tmp/hf_cache`), load pre-quantized GGUF transformers (`t8star/flux.1-dev-abliterated-V2-GGUF` or `silveroxides/Chroma1-HD-GGUF`) to CUDA before 4-bit NF4 `T5-XXL`, and force `pipe.vae.to(dtype=torch.float32)` + slicing/tiling. Never hardcode `HF_TOKEN` literals in generated scripts.
   - **Kaggle Official First-Party Proxy (`45 hrs/wk` Dual-T4)**: Linking Colab Pro unlocks `45 hrs/wk` Dual-T4 (`30,720 MiB` VRAM). Connect remotely with zero ban risk via Kaggle's **VS Code Compatible URL** (`https://kkb-production.jupyter-proxy.kaggle.net/k/<kernel_id>/<JWT>/proxy`) over Jupyter `/api/kernels/<id>/channels`, optionally fronted by the `<40 MB` Novita Sandbox WS-to-OpenAI relay (`https://<YOUR_DOMAIN> e.g. `Mistral-Small-24B-Instruct-2501-abliterated-GGUF` `Q4_K_M`, 64K ctx, `q4_0` KV cache).
3. **The Core Economic Law of Cloud GPUs**:
   $$\text{Total Cost (CCU)} = \text{Hardware Hourly Rate} \times \frac{\text{Wall-Clock Time (min)}}{60}$$
   - **Never choose T4 over L4 for large diffusion/video tasks**: Tesla T4 lacks native `bfloat16` and `FP8` support, forcing PyTorch to offload tensors over slow PCIe to host RAM. A 161-frame video generation on T4 takes 40+ minutes (~1.31 CCU) and risks swap thrashing, while on Ada Lovelace L4 (~2.08 CCU/hr, or `--gpu T4 --high-mem` 52 GB RAM @ `2.35 CCU/hr` for CPU offload) it finishes in 4 minutes with pure CUDA `bfloat16` (~0.14 CCU).
4. **4-Pillar Production Video Generation Architecture**:
   - **Pillar 1: Separation of Identity (T2I) from Motion (I2V)**: Author crisp 2D keyframe stills with high-fidelity models (`Animagine XL 3.1`, `Illustrious-XL`) at native resolution ($1024 \times 1024$). Never set `num_inference_steps=4, guidance_scale=0.0` for structured lecture diagrams (produces blurry smudges) and never silently swap expressive TTS (F5-TTS/CosyVoice-2) for faster CPU Kokoro without flagging expressiveness loss.
   - **Pillar 2: Pre-Flight Contact Sheet Gate**: Always review a 3-frame contact sheet before launching long batch generation.
   - **Pillar 3: Motion Generation & Broadcast Compositing**: Feed validated stills into Wan 2.1 I2V / SVD, or use decoupled 2-stage Colab L4 broadcast rendering (`v10_broadcast_masterclass_engine.py`: dual Gen-8 `h264_nvenc`, $C^2$ quintic pointer easing instead of `np.sin` oscillation, `1480x110px` subtitle pill).
   - **Pillar 4: Post-Assembly & Lossless Concat**: Assemble shots via FFmpeg lossless stream-copy (`ffmpeg -f concat -safe 0 -c copy output.mp4`) and immediately shut down VM (`runtime.unassign()`).
5. **GPU Credit Zero-Waste Invariant**: Cloud GPU notebooks must NEVER be started until all generation scripts, prompt manifests, and environment requirements are 100% verified locally.
6. **Google Flow Identity-Bound Credit & RPM Limits**: Veo uses monthly AI credits (`1,000/mo` Pro) while Imagen 3 uses sliding-window RPC rate limits (`~8 RPM` primary Pro, `~3-4 RPM` family member, `~1-2 RPM` free). Credits are **identity-bound** (not pooled across family accounts); concurrent profiles sharing one egress IP trigger GFE 429 throttling without a host mutex or per-profile proxy.

---

## 5. Specialized 3D Asset Generation Workflows

### 5.1 Recommended SOTA Open Models
- **TripoSR**: Ultra-fast single image-to-3D model (<5 seconds on Tesla T4). Generates textured `.obj` or `.glb` meshes from segmented foreground PNGs.
- **Trellis**: SOTA structural and PBR material synthesis from image inputs.
- **InstantMesh**: High-quality multi-view diffusion and large reconstruction model (LGM) generating clean manifold geometry.
- **Hunyuan3D-1.0**: High-resolution 3D asset generation for game-ready low/medium poly targets.

### 5.2 End-to-End Image-to-3D Pipeline

```mermaid
flowchart LR
    P1["1. 2D Concept Asset<br>(Flow / SDXL)"] --> P2["2. Alpha Isolation<br>(rembg / BiRefNet)"]
    P2 --> P3["3. Cloud Neural Mesh<br>(TripoSR / Trellis on Colab/Modal)"]
    P3 --> P4["4. Poly Optimization<br>(Decimate & Clean Topology)"]
    P4 --> P5["5. GLB Export to Cloudflare R2<br>(Zero-Egress Distribution)"]
```

1. **Step 1 (Generate 2D Reference)**: Generate a crisp 2D orthographic reference image via Gemini Flow or SDXL with clean solid background.
2. **Step 2 (Background Removal)**: Run `rembg` (BiRefNet) to strip the background into a clean 32-bit RGBA PNG with alpha transparency.
3. **Step 3 (Neural Mesh Reconstruction)**: Feed the isolated PNG into TripoSR or Trellis running on Colab or Modal.
4. **Step 4 (Post-Processing & Decimation)**: Optimize geometry using `trimesh` or PyVista, downsampling vertex count to target polybudgets (e.g. 5,000–15,000 triangles for real-time web/canvas games).
5. **Step 5 (Direct Export)**: Save as compressed `.glb` (Draco compression) and push directly to Cloudflare R2 ($0 egress distribution).

---

## 6. Autonomous Google Frontier AI Engine (Argon & Deep Research Bridge)

### 6.1 Overview & Dual-Model Cognitive Bridge
When complex architectural ideation, root-cause analysis, or deep literature syntheses require Google's frontier models, `external-resource` orchestrates the local **Argon Bridge** (`browser-operator/argon_bridge/`). This provides direct, autonomous access to **Gemini 4 Argon on High Thinking** and **Deep Research** via the user's authentic Google One AI Premium accounts—with zero API token expenditure and no sandbox/guest-mode traps.

```mermaid
flowchart TD
    Task["Agent / Subagent Task"] --> Engine{"Select Modality"}
    Engine -->|High-Density Cognitive Brain| Argon["Gemini 4 Argon (High Thinking)<br>gemini.google.com/app"]
    Engine -->|Multi-Source Grounded Investigation| DeepRes["Deep Research Mode<br>Multi-Step Autonomous Synthesis"]
    
    Argon --> Bridge["Local Argon Bridge (Port 9229)<br>MV3 Chrome Extension + Trusted CDP"]
    DeepRes --> Bridge
    
    Bridge --> ProfilePool["6x Google One AI Premium Profiles<br>(Profile 13, 14, 16, 7, 8, 9)"]
    ProfilePool --> HumanStealth["Stealth Layer (stealth_input.py)<br>Cubic Bézier Curves + Ease Pacing + Jitter"]
    HumanStealth --> Harvester["Rich Structured Response Harvester<br>Markdown, Tables (JSON/MD), Code, Canvas, Sources"]
    Harvester --> AutoPurge["Zero-Clutter Purge<br>(Autonomous Sidebar Chat Deletion)"]
```

### 6.2 The 6 Google One AI Premium Profile Fleet & Quota Governance
The bridge automatically audits `%LOCALAPPDATA%\Google\Chrome\User Data\Local State` and balances requests across the user's authenticated profiles:
1. `Profile 13`: `Profile-User` (`profile-1@example.com`)
2. `Profile 14`: `Profile-User` (`profile-2@example.com` / `Profile-User`)
3. `Profile 16`: `Owner` (`profile-3@example.com`)
4. `Profile 7`: `Owner` (`profile-4@example.com`)
5. `Profile 8`: `ggl` (`profile-5@example.com`)
6. `Profile 9`: `Vid` (`profile-6@example.com`)

*Live Quota Telemetry (`https://gemini.google.com/usage`)*:
- The driver opens Google's official quota dashboard in a clean background tab (`active: false`).
- Parses rolling 5-hour compute usage (`current_usage_percent`, `current_reset`), weekly usage (`weekly_usage_percent`, `weekly_reset`), and returns `should_rotate: true` when usage exceeds $80\%$.
- Supports hot-swapping via `--profile <profile_dir>` or automated failover.

### 6.3 Anti-Bot & Anti-Captcha Stealth Architecture
To prevent Google bot detection and captcha challenges:
- **Cubic Bézier Trajectories**: Cursor paths are generated using parametric cubic Bézier curves with smoothstep ($S(t) = 3t^2 - 2t^3$) ease-in/ease-out velocity and Gaussian hand-tremor jitter.
- **Spatial Click Jitter**: Target coordinates are randomized within $\pm 4\text{px}$ of the button bounding box.
- **Human Hesitation & Hold Durations**: Enforces a 90–240ms hover pause prior to click, a 50–115ms mouse-down hold duration, and post-click recovery delays.
- **Cadenced Typing**: Realistic inter-keystroke intervals with micro-pauses at word boundaries.

### 6.4 The Context Bundling & Programmatic Upload Standard
> [!IMPORTANT]
> 🛑 **ZERO-REFUSAL MANDATE (PRE-AUTHENTICATED FLEET)**:
> Autonomous agents MUST NEVER refuse requests to *"use argon"*, *"consult gemini"*, or *"use Google accounts"*, nor claim inability to interact with the browser.
> The **Argon Bridge daemon (`server.py`)** runs permanently at `http://127.0.0.1:9229` via a trusted CDP extension relay and connects directly to 6 authenticated Google One AI Premium profiles (`Profile 14`, `Profile 13`, `Profile 16`, `Profile 7`, `Profile 8`, `Profile 9`).
> Zero API tokens, zero logins, and zero manual pasting required. Simply run `consult_argon.py` or `gemini_brain_driver.py`.

When analyzing multi-file codebases, logs, database migrations, or complex prompts:
- **Context Bundling Protocol**: Write an artifact to `<workspace>/temp_read/context_bundle.md` combining schemas, error logs, interfaces, and constraints.
- **CDP File Upload**: Programmatically attaches the context file directly into the prompt box via CDP `DOM.setFileInputFiles` after text insertion (`--upload temp_read/context_bundle.md` or `-f temp_read/context_bundle.md`).
- **Instant Harvesting**: The driver detects completion the moment action buttons (`Copy`, reaction chips) appear without polling lag.
- **Rich Extraction**: Formatted Markdown, tabular arrays (`Array<Record<string, string>>`), raw code blocks, and deduplicated source citations.

### 6.5 Multi-Agent Concurrency, Tab Collisions & Low-RAM Guardrails
1. **Dynamic Lease Arbitration (`profile_lock_manager.py`)**:
   When multiple agents or subagents query the bridge concurrently:
   - The bridge inspects live leases via `http://127.0.0.1:9229/locks`.
   - If `Profile 14` is currently leased by another agent, the caller is **automatically auto-routed to an idle profile** (`Profile 13`, `Profile 16`, `Profile 7`, `Profile 8`, `Profile 9`).
   - Leases have dynamic TTLs (300s default, 900s for deep research) with continuous 25s heartbeat renewals (`POST /lock/renew`). Prevents typing collisions and conflicting tabs.
2. **Single-Tab Low-RAM Invariant**:
   To strictly protect systems with low RAM from out-of-memory browser crashes:
   - The driver strictly reuses the single existing Gemini tab on that profile window.
   - Never spawn multiple duplicate tabs.
   - Any temporary diagnostic tab (e.g. `/usage`) is immediately closed in a `finally` block upon reading.
3. **Automatic Sidebar Hygiene & Multi-Turn State**:
   - **Auto-Purge by Default (`auto_clean=True`)**: Single-turn automated queries automatically delete the temporary chat from the Gemini sidebar (`Hover -> 3-dots -> Delete -> Confirm`) after saving the output to `temp_read/`, keeping the user's personal Google accounts 100% clean. Pass `--no-clean` (`--keep`) only when debugging.
   - **Multi-Turn Dialogue (`--continue`)**: Re-attaches to an ongoing chat thread using `--session-id` without triggering "New chat", and purges on the final turn when `--clean` is passed.
   - **Tier-2 Vertex AI API Failover (`--api`)**: Automatically routes to Google Cloud Vertex AI (`<GCP_PROJECT_ID>` / `gemini-4-argon`) if all 6 browser accounts hit their 5-hour quota limit, or when `--api` is explicitly requested.

### 6.6 CLI Command Reference

All scripts reside in `<BRAIN_ROOT>\.agents\skills\browser-operator\argon_bridge\` and `deep-thinking\scripts\`:

```powershell
# 1. Audit live Gemini quota on target profile without sending prompts
python .../argon_bridge/gemini_brain_driver.py --profile "Profile 14" --usage

# 2. Query Gemini 4 Argon on High Thinking (retains chat in sidebar unless --auto-clean is passed)
python .../argon_bridge/gemini_brain_driver.py "Design a resilient microservices event mesh." --profile "Profile 14" --thinking High

# 3. Context-Bundled Consultation (Codebases, Logs, Markdown Specs, PDFs)
python .../argon_bridge/gemini_brain_driver.py "Review these files" --upload temp_read/context_bundle.md --profile "Profile 14" --thinking High

# 4. Multi-Turn Dialogue via consult_argon.py
python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py "Initial design query" --session-id "task_mesh" --profile "Profile 13"
python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py "Optimize memory footprint" --session-id "task_mesh" --continue --profile "Profile 13"

# 5. Query in Deep Research mode (900s TTL + auto-confirms plan cards & long-polls report)
python .../argon_bridge/gemini_brain_driver.py "Comprehensive comparison of pgvector vs Milvus vs Qdrant in 2026." --deep-research --profile "Profile 14"

# 6. Finalize multi-turn task and cleanly delete chat from sidebar
python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py "Final report summary" --session-id "task_mesh" --continue --clean --profile "Profile 13"

# 7. Check live multi-agent locks across fleet
python -c "import urllib.request, json; print(json.dumps(json.loads(urllib.request.urlopen('http://127.0.0.1:9229/locks').read()), indent=2))"

# 8. Capture live visual snapshot for self-healing inspection
python .../argon_bridge/gemini_brain_driver.py --screenshot "temp_read/live_gemini.png" --profile "Profile 14"

# 9. Google AI Studio 2M-Token Context Bundling (-f) & Model Selection (Argon, Flash)
python <BRAIN_ROOT>\.agents\skills\browser-operator\argon_bridge\aistudio_subagent.py "Analyze architectural invariants" -f constraints.md project_map.md --profile "Profile 14" --model "gemini-4-argon"

# 10. Harvest <> Get code client SDK snippet for Gemini 4 Argon directly to local file
python <BRAIN_ROOT>\.agents\skills\browser-operator\argon_bridge\aistudio_subagent.py --surface playground --model gemini-4-argon --get-code --get-code-output temp_read/gemini_4_argon_sdk.py

# 11. Build a full-stack app in AI Studio App Builder with multi-file code generation
python <BRAIN_ROOT>\.agents\skills\browser-operator\argon_bridge\aistudio_subagent.py "Interactive Three.js cyber synthwave grid with audio visualizer" --surface apps --profile "Profile 14" --screenshot "temp_read/app_build.png"

# 12. Search AI Studio Showcase Gallery for templates
python <BRAIN_ROOT>\.agents\skills\browser-operator\argon_bridge\aistudio_subagent.py --surface gallery --search-gallery "Argon" --profile "Profile 14"

# 13. Remix a Showcase Gallery app into Build Mode
python <BRAIN_ROOT>\.agents\skills\browser-operator\argon_bridge\aistudio_subagent.py --surface gallery --remix "Wizard Chess 3D" --remix-name "My Custom Chess" --profile "Profile 14"

# 14. Export generated app directly to Antigravity, GitHub, or ZIP archive
python <BRAIN_ROOT>\.agents\skills\browser-operator\argon_bridge\aistudio_subagent.py --surface apps --export-app antigravity --profile "Profile 14"
```

---

## 7. Cross-Skill Integration Contracts

- **`browser-operator` Handshake Protocol**: Stages remote/batch generation manifests or assets into `<active_project>/temp_read/` and verifies non-zero byte size before acquiring a `browser-operator` lease (`ttl=300s`, `25s` heartbeats).
- **Prompt-First File Upload Standard**: Submits prompt instructions and file paths simultaneously. Ensures the solid preview chip (`uploader-file-preview`) is mounted and progress bar is unmounted before triggering send.
- **Single-Tab Low-RAM Limit**: Reuses the primary Gemini tab per profile window to maintain safe host memory bounds.

---

## 8. Bundled Automation Scripts

| Script Path | Purpose | Execution Command |
|---|---|---|
| `scripts/batch_manifest_generator.py` | Compiles, validates, and tests batch generation manifests with regex pairing | `python .../batch_manifest_generator.py --input raw_prompts.txt --output manifest.json` |
| `scripts/spark_prompt_synthesizer.py` | Generates high-density, anti-slop prompts for Gemini Spark / Deep Research | `python .../spark_prompt_synthesizer.py --topic "3D Mesh Pipeline" --role "Architect"` |
| `deep-thinking/scripts/consult_argon.py` | Direct cognitive deliberation via Gemini 4 Argon with file uploads & auto-clean | `python .../consult_argon.py -q "<prompt>" -f <files>` |
| `scripts/modal_asset_server.py` | Reference Modal serverless deployment script for TripoSR/custom models | `modal deploy .../modal_asset_server.py` |
| `scripts/colab_asset_runner.py` | Headless batch asset runner for Colab/Kaggle with automatic R2/Drive sync | `python .../colab_asset_runner.py --manifest manifest.json` |
| `scripts/benchmark/benchmark.js` | Asynchronous multi-provider latency and rate-limit tester across 55+ models | `node .../benchmark.js --tier 1` |
| `scripts/benchmark/test_gateway.js` | Tests Azure VM-1 Gateway and Edge LLM Relay fallback routing | `node .../test_gateway.js` |
| `argon_bridge/gemini_brain_driver.py` | Autonomous driver for Gemini 4 Argon & Deep Research on gemini.google.com | `python .../argon_bridge/gemini_brain_driver.py "<prompt>"` |
| `argon_bridge/aistudio_subagent.py` | Super-subagent driver for Google AI Studio with 2M token context bundling | `python .../argon_bridge/aistudio_subagent.py "<prompt>"` |

---

## 9. Operational Guidelines for Agents

1. **Verify Asset Modality First**: Before proposing a compute solution, determine whether the asset can be generated in Google Flow (free multi-account quota) or strictly requires a custom GPU notebook (e.g. 3D geometry, custom LoRA weights).
2. **Autonomous Cognitive Dispatch**: For complex architecture decisions or deep multi-turn planning, dispatch queries to `gemini_brain_driver.py` using `--thinking High`.
3. **Always Generate Valid Delimited Manifests**: When producing prompts for the user to paste into the Gemini Flow tool, format them with triple equals `=== <ASSET_SLUG> ===` followed by clean, full-body prompts with explicit negative prompts.
4. **Pre-Flight Notebook Verification**: Ensure all Colab/Kaggle scripts use `pip install -q` and include non-interactive `--yes` flags to prevent hanging cell execution.
5. **Sidebar Hygiene & Lifecycle**: `consult_argon.py` auto-cleans ephemeral single-turn chats by default (`--clean` is `True`; pass `--no-clean` / `--keep` for multi-turn debugging). When invoking `gemini_brain_driver.py` directly, chats remain in the sidebar unless `--auto-clean` or `--cleanup` is passed.