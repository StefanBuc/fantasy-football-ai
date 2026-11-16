import os

import torch


def report_runtime_device() -> torch.device:
    """Report the selected device, and enforce explicit GPU-mode requests."""
    required = os.getenv("REQUIRE_CUDA", "false").strip().lower() in {"1", "true", "yes"}
    available = torch.cuda.is_available()
    if required and not available:
        reason = (
            "This image has CPU-only PyTorch. Rebuild with compose.gpu.yaml."
            if torch.version.cuda is None else
            "CUDA PyTorch is installed, but Docker cannot access a compatible NVIDIA GPU."
        )
        raise RuntimeError(f"REQUIRE_CUDA is enabled. {reason}")
    device = torch.device("cuda" if available else "cpu")
    label = f"CUDA ({torch.cuda.get_device_name()})" if available else "CPU"
    print(
        f"[PyTorch] Runtime device: {label}; torch={torch.__version__}; "
        f"CUDA build={torch.version.cuda or 'none (CPU-only build)'}",
        flush=True,
    )
    return device
