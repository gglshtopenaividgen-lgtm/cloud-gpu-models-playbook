#!/usr/bin/env python3
"""
Production Modal Serverless @modal.web_server Template for OpenAI-Compatible GGUF Serving.
Enforces:
- max_containers=1 (prevents horizontal GPU autoscaling burn on cold-start queues)
- scaledown_window=60 (prevents 3600s idle credit bleed)
- --no-mmap (avoids FUSE virtual filesystem page-fault stalls on Modal Volumes)
- Persistent @modal.Volume weight caching + non-blocking liveness probe
"""

import os
import subprocess
import time
from pathlib import Path

import modal

APP_NAME = "cloud-gpu-llama-server"
VOLUME_NAME = "gguf-weights-cache"
MODEL_DIR = "/models"
MODEL_REPO = os.environ.get("MODEL_REPO", "bartowski/Qwen2.5-Coder-32B-Instruct-abliterated-GGUF")
MODEL_FILE = os.environ.get("MODEL_FILE", "Qwen2.5-Coder-32B-Instruct-abliterated-IQ4_XS.gguf")
CTX_SIZE = int(os.environ.get("CTX_SIZE", "32768"))

app = modal.App(APP_NAME)
weights_vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

image = (
    modal.Image.from_registry("ghcr.io/ggml-org/llama.cpp:server-cuda", add_python="3.11")
    .pip_install("huggingface_hub", "hf_transfer")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "HF_HUB_DISABLE_PROGRESS_BARS": "1"})
)


def _ensure_model_cached() -> str:
    from huggingface_hub import hf_hub_download

    target = Path(MODEL_DIR) / MODEL_FILE
    if target.exists() and target.stat().st_size > 100 * 1024 * 1024:
        with target.open("rb") as f:
            if f.read(4) == b"GGUF":
                return str(target)

    downloaded = hf_hub_download(
        repo_id=MODEL_REPO,
        filename=MODEL_FILE,
        local_dir=MODEL_DIR,
        token=os.environ.get("HF_TOKEN") or None,
    )
    weights_vol.commit()
    return downloaded


@app.function(
    image=image,
    gpu="L4",
    volumes={MODEL_DIR: weights_vol},
    max_containers=1,
    scaledown_window=60,
    timeout=900,
)
@modal.web_server(8000, startup_timeout=300)
def serve():
    """Spawn llama-server non-blockingly and verify /health before returning."""
    import urllib.request

    model_path = _ensure_model_cached()
    cmd = [
        "/app/llama-server",
        "-m", model_path,
        "--host", "0.0.0.0",
        "--port", "8000",
        "-ngl", "99",
        "--no-mmap",
        "-c", str(CTX_SIZE),
        "-ctk", "q4_0",
        "-ctv", "q4_0",
        "-fa",
    ]
    log_path = Path("/tmp/llama_server.log")
    log_file = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)

    for _ in range(120):
        if proc.poll() is not None:
            tail = log_path.read_text(encoding="utf-8", errors="ignore")[-2000:]
            raise RuntimeError(f"llama-server crashed ({proc.returncode}):\n{tail}")
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception:
            pass
        time.sleep(2)

    raise TimeoutError("llama-server failed /health within startup window; check /tmp/llama_server.log")
