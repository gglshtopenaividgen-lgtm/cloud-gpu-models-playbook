# Cloud Compute & External Resource Cheat Sheet

| Platform | Free Quota & Cycle | Key Hardware | Ingress Method | Primary Use Case |
|---|---|---|---|---|
| **Google Flow** | Unlimited with multiple Gemini Pro accounts | Google TPUs / Cloud Infra | Flow Web UI & Batch Export | 2D Art, Sprite Sheets, Video Loops, Ambient Tracks |
| **Modal Labs** | $30.00 / month recurring credits | A100-80GB ($2.50/h), T4 ($0.59/h) | Native `@modal.web_endpoint` | Serverless 3D Mesh APIs, FLUX.1 generation |
| **Kaggle Notebooks** | 30 GPU-hours / week (Sunday reset) | 2x Tesla T4 (30.7 GB total) or TPU v3-8 | Air-gapped batch to R2/Drive | Heavy batch mesh baking, MusicGen loops |
| **Google Colab** | Rolling 12-72h reset (~4h session) | Tesla T4 (15 GB) | Gradio `share=True` | Rapid 3D prototyping (TripoSR), InstantMesh tests |
| **Gemini Spark** | Unlimited via web | Google Cloud Reasoning | Structured Cognitive Prompt | Mathematical derivations, algorithm proofs, zero-slop blueprints |

### Strict Non-Negotiable Rules
1. **Never use reverse tunnels on Kaggle/Colab** (`ngrok`, `cloudflared` trigger immediate account termination).
2. **Never start a GPU notebook without 100% locally verified caller scripts**.
3. **Always use regex pairing in manifest parsers to avoid splitting errors**.
