from unittest.mock import Mock

import pytest
import torch

from app.services import pytorch_projection_model as checkpoints


@pytest.fixture(autouse=True)
def fresh_device_selection():
    checkpoints.inference_device.cache_clear()
    yield
    checkpoints.inference_device.cache_clear()


def test_cpu_only_machine_does_not_inspect_cuda_architectures(monkeypatch):
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: False)
    capability = Mock(side_effect=AssertionError('No CUDA device'))
    monkeypatch.setattr(torch.cuda, 'get_device_capability', capability)
    assert checkpoints.inference_device().type == 'cpu'
    capability.assert_not_called()


@pytest.mark.parametrize(('capability', 'architectures', 'expected'), [
    ((6, 1), ['sm_75', 'sm_80', 'sm_86', 'sm_90', 'sm_100', 'sm_120'], 'cpu'),
    ((7, 0), ['sm_75', 'sm_80'], 'cpu'),
    ((6, 1), ['sm_60', 'sm_70'], 'cuda'),
    ((8, 9), ['sm_75', 'sm_80', 'sm_86'], 'cuda'),
    ((9, 0), ['sm_86', 'compute_86'], 'cuda'),
])
def test_device_selection_checks_binary_and_ptx_compatibility(monkeypatch, caplog, capability, architectures, expected):
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: True)
    monkeypatch.setattr(torch.cuda, 'get_device_capability', lambda: capability)
    monkeypatch.setattr(torch.cuda, 'get_arch_list', lambda: architectures)
    monkeypatch.setattr(torch.cuda, 'get_device_name', lambda: 'Test GPU')
    assert checkpoints.inference_device().type == expected
    if expected == 'cpu':
        assert 'Using CPU' in caplog.text and 'unsupported' in caplog.text


def test_explicit_cpu_device_does_not_probe_cuda(monkeypatch):
    monkeypatch.setattr(checkpoints, 'inference_device', Mock(side_effect=AssertionError('Explicit device must win')))
    load = Mock(side_effect=FileNotFoundError('checkpoint unavailable'))
    monkeypatch.setattr(torch, 'load', load)
    device = torch.device('cpu')
    with pytest.raises(FileNotFoundError):
        checkpoints.load_projection_checkpoint('missing.pth', device=device)
    assert load.call_args.kwargs['map_location'] == device
