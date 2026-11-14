#!/usr/bin/env python3
"""
Cloud GPU Pre-Flight Guard (Colab / Kaggle / Modal).
Validates GPU VRAM, /tmp ephemeral disk space, GGUF binary magic bytes,
psutil 5.9/6.0 port reclamation, and progress-bar suppression.
"""

import ctypes
import gc
import os
import shutil
import subprocess
from pathlib import Path
from typing import Tuple


def configure_ephemeral_env(cache_root: str = "/tmp") -> None:
    """Route Hugging Face / PyTorch caches to /tmp and suppress notebook log bloat."""
    root = Path(cache_root)
    (root / "hf_cache" / "hub").mkdir(parents=True, exist_ok=True)
    (root / "torch_cache").mkdir(parents=True, exist_ok=True)
    (root / "models").mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("HF_HOME", str(root / "hf_cache"))
    os.environ.setdefault("HF_HUB_CACHE", str(root / "hf_cache" / "hub"))
    os.environ.setdefault("TORCH_HOME", str(root / "torch_cache"))
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TQDM_DISABLE"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")


def reclaim_port(port: int) -> None:
    """
    Safely reclaim a stuck TCP port in interactive Jupyter kernels.
    Handles psutil 5.9.x (connections) and psutil 6.0+ (net_connections).
    Never binds to Google Colab's reserved supervisor port 8080.
    """
    if port in (8080, 8082):
        raise ValueError(f"Port {port} is reserved by Colab/platform supervisor; pick 7860, 7890, or 8000.")

    try:
        import psutil
    except ImportError:
        return

    proc = psutil.Process(os.getpid())
    conn_fn = getattr(proc, "net_connections", None) or getattr(proc, "connections", None)
    if conn_fn is None:
        return

    for conn in conn_fn(kind="inet"):
        if conn.laddr and getattr(conn.laddr, "port", None) == port and conn.fd >= 0:
            try:
                os.close(conn.fd)
            except OSError:
                pass


def verify_gguf_binary(path: str | Path, min_mb: int = 100) -> Tuple[bool, str]:
    """
    Confirm downloaded file is a valid GGUF binary (not a 404/401 HTML page).
    Automatically removes corrupt files so callers can trigger fallback mirrors.
    """
    p = Path(path)
    if not p.exists():
        return False, "File does not exist"
    size_bytes = p.stat().st_size
    if size_bytes < min_mb * 1024 * 1024:
        p.unlink(missing_ok=True)
        return False, f"File too small ({size_bytes / (1024**2):.1f} MB < {min_mb} MB)"
    with p.open("rb") as f:
        magic = f.read(4)
    if magic != b"GGUF":
        p.unlink(missing_ok=True)
        return False, f"Invalid GGUF magic header {magic!r}; corrupt file purged"
    return True, f"Valid GGUF ({size_bytes / (1024**3):.2f} GB)"


def free_linux_memory() -> None:
    """Release CUDA cache and return glibc heap arenas to Linux OS."""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except ImportError:
        pass
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def check_system_summary(model_dir: str = "/tmp/models") -> dict:
    """Return quick GPU count/VRAM and ephemeral /tmp free space diagnostics."""
    disk = shutil.disk_usage(Path(model_dir).parent if Path(model_dir).parent.exists() else "/")
    gpus = []
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            text=True,
            timeout=5,
        )
        for line in out.strip().splitlines():
            idx, name, total, free = [x.strip() for x in line.split(",")]
            gpus.append({"index": int(idx), "name": name, "vram_total_mb": int(total), "vram_free_mb": int(free)})
    except Exception:
        pass

    return {
        "tmp_free_gb": round(disk.free / (1024 ** 3), 2),
        "gpu_count": len(gpus),
        "gpus": gpus,
        "hf_token_set": bool(os.environ.get("HF_TOKEN")),
    }


if __name__ == "__main__":
    configure_ephemeral_env()
    print(check_system_summary())
