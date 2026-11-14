#!/usr/bin/env python3
"""
Parameterized GGUF OpenAI-Compatible Server for Kaggle Dual-T4 / Colab T4.
- Uses /tmp/models (never fills 19.5 GB /kaggle/working quota).
- Validates b'GGUF' magic bytes and supports fallback Hugging Face mirrors.
- Splits weights across Dual-T4 GPUs (--split-mode layer --tensor-split 1,1) with q4_0 KV cache.
- Reads HF_TOKEN strictly from environment variables.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from pre_flight_check import configure_ephemeral_env, reclaim_port, verify_gguf_binary


def download_gguf(
    repo_id: str,
    filename: str,
    model_dir: str = "/tmp/models",
    fallback_repo: Optional[str] = None,
    fallback_file: Optional[str] = None,
) -> Path:
    """Download GGUF in a single pass into model_dir and verify GGUF magic bytes."""
    from huggingface_hub import hf_hub_download

    target_dir = Path(model_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("HF_TOKEN") or None

    attempts = [(repo_id, filename)]
    if fallback_repo and (fallback_file or filename):
        attempts.append((fallback_repo, fallback_file or filename))

    last_err = ""
    for r_id, fname in attempts:
        try:
            local_path = Path(
                hf_hub_download(
                    repo_id=r_id,
                    filename=fname,
                    local_dir=str(target_dir),
                    token=token,
                )
            )
            ok, msg = verify_gguf_binary(local_path)
            if ok:
                print(f"[OK] Ready: {local_path} ({msg})")
                return local_path
            last_err = msg
        except Exception as exc:
            last_err = f"{r_id}/{fname}: {exc}"
            print(f"[WARN] Download attempt failed: {last_err}")

    raise RuntimeError(f"All GGUF download attempts failed: {last_err}")


def launch_llama_server(
    model_path: Path,
    server_bin: str = "llama-server",
    host: str = "127.0.0.1",
    port: int = 8000,
    ctx_size: int = 16384,
    tensor_split: str = "1,1",
    kv_type: str = "q4_0",
    flash_attn: bool = True,
    slots: int = 1,
) -> subprocess.Popen:
    """Launch llama-server with layer split, quantized KV cache, and active health check."""
    import urllib.request

    reclaim_port(port)
    cmd = [
        server_bin,
        "-m", str(model_path),
        "--host", host,
        "--port", str(port),
        "-ngl", "99",
        "--split-mode", "layer",
        "--tensor-split", tensor_split,
        "-c", str(ctx_size),
        "-ctk", kv_type,
        "-ctv", kv_type,
        "--parallel", str(slots),
        "-b", "512",
        "-ub", "128",
    ]
    if flash_attn:
        cmd.append("-fa")

    log_path = Path("/tmp/llama_server.log")
    log_file = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)

    url = f"http://{host}:{port}/health"
    for _ in range(90):
        if proc.poll() is not None:
            tail = log_path.read_text(encoding="utf-8", errors="ignore")[-2000:]
            raise RuntimeError(f"llama-server exited early ({proc.returncode}):\n{tail}")
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    print(f"[READY] OpenAI endpoint active at http://{host}:{port}/v1")
                    return proc
        except Exception:
            pass
        time.sleep(2)

    proc.terminate()
    raise TimeoutError("Timed out waiting for llama-server /health; inspect /tmp/llama_server.log")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve GGUF on Dual-T4 / Single-T4 via llama-server")
    parser.add_argument("--repo", default="bartowski/Qwen2.5-Coder-32B-Instruct-abliterated-GGUF")
    parser.add_argument("--file", default="Qwen2.5-Coder-32B-Instruct-abliterated-IQ4_XS.gguf")
    parser.add_argument("--fallback-repo", default=None)
    parser.add_argument("--fallback-file", default=None)
    parser.add_argument("--model-dir", default="/tmp/models")
    parser.add_argument("--server-bin", default="llama-server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ctx", type=int, default=16384)
    parser.add_argument("--tensor-split", default="1,1", help="'1,1' for Dual-T4 split; '1,0' for GPU0 isolation")
    parser.add_argument("--kv-type", default="q4_0", choices=["q4_0", "q8_0", "f16"])
    parser.add_argument("--no-fa", action="store_true", help="Disable FlashAttention on older T4 builds if asserting")
    args = parser.parse_args()

    configure_ephemeral_env()
    model_path = download_gguf(args.repo, args.file, args.model_dir, args.fallback_repo, args.fallback_file)
    proc = launch_llama_server(
        model_path=model_path,
        server_bin=args.server_bin,
        port=args.port,
        ctx_size=args.ctx,
        tensor_split=args.tensor_split,
        kv_type=args.kv_type,
        flash_attn=not args.no_fa,
    )
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        sys.exit(0)


if __name__ == "__main__":
    main()
