import pytest

from app.services import runtime_device


def test_cpu_mode_reports_cpu_only_build(monkeypatch, capsys):
    monkeypatch.delenv("REQUIRE_CUDA", raising=False)
    monkeypatch.setattr(runtime_device.torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(runtime_device.torch.version, "cuda", None)
    assert runtime_device.report_runtime_device().type == "cpu"
    assert "none (CPU-only build)" in capsys.readouterr().out


def test_gpu_mode_reports_gpu_name(monkeypatch, capsys):
    monkeypatch.setenv("REQUIRE_CUDA", "true")
    monkeypatch.setattr(runtime_device.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(runtime_device.torch.cuda, "get_device_name", lambda: "Test GPU")
    assert runtime_device.report_runtime_device().type == "cuda"
    assert "Runtime device: CUDA (Test GPU)" in capsys.readouterr().out


@pytest.mark.parametrize("cuda_build, expected", [
    (None, "CPU-only PyTorch"), ("13.4", "cannot access a compatible NVIDIA GPU"),
])
def test_gpu_mode_cannot_silently_fall_back(monkeypatch, cuda_build, expected):
    monkeypatch.setenv("REQUIRE_CUDA", "true")
    monkeypatch.setattr(runtime_device.torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(runtime_device.torch.version, "cuda", cuda_build)
    with pytest.raises(RuntimeError, match=expected):
        runtime_device.report_runtime_device()
