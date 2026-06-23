"""Tests for local-model GPU offload configuration.

These cover the pure decision logic (env-var resolution) and the status
surface — neither requires llama-cpp or a real GGUF file to be installed.
"""

import importlib

import pytest

import services.local_model_service as lms


@pytest.fixture(autouse=True)
def _clear_gpu_env(monkeypatch):
    monkeypatch.delenv("LOCAL_MODEL_GPU_LAYERS", raising=False)
    yield


def test_resolve_gpu_layers_auto_uses_offload_when_supported(monkeypatch):
    monkeypatch.setattr(lms, "_supports_gpu_offload", lambda: True)
    assert lms._resolve_gpu_layers() == -1


def test_resolve_gpu_layers_auto_falls_back_to_cpu(monkeypatch):
    monkeypatch.setattr(lms, "_supports_gpu_offload", lambda: False)
    assert lms._resolve_gpu_layers() == 0


def test_resolve_gpu_layers_force_cpu(monkeypatch):
    # Even when the build supports GPU, an explicit 0 forces CPU.
    monkeypatch.setattr(lms, "_supports_gpu_offload", lambda: True)
    monkeypatch.setenv("LOCAL_MODEL_GPU_LAYERS", "0")
    assert lms._resolve_gpu_layers() == 0


def test_resolve_gpu_layers_explicit_count(monkeypatch):
    monkeypatch.setattr(lms, "_supports_gpu_offload", lambda: False)
    monkeypatch.setenv("LOCAL_MODEL_GPU_LAYERS", "20")
    assert lms._resolve_gpu_layers() == 20


def test_resolve_gpu_layers_invalid_falls_back_to_auto(monkeypatch):
    monkeypatch.setattr(lms, "_supports_gpu_offload", lambda: True)
    monkeypatch.setenv("LOCAL_MODEL_GPU_LAYERS", "banana")
    assert lms._resolve_gpu_layers() == -1


def test_supports_gpu_offload_false_when_llama_unavailable(monkeypatch):
    monkeypatch.setattr(lms, "LLAMA_CPP_AVAILABLE", False)
    assert lms._supports_gpu_offload() is False


def test_status_reports_gpu_capability_when_idle(monkeypatch):
    monkeypatch.setattr(lms, "_supports_gpu_offload", lambda: True)
    svc = lms.LocalModelService()
    status = svc.get_status()
    assert status["loaded"] is False
    assert status["gpu_offload_supported"] is True


def test_status_reports_active_gpu_when_loaded(monkeypatch):
    monkeypatch.setattr(lms, "_supports_gpu_offload", lambda: True)
    svc = lms.LocalModelService()
    # Simulate a loaded model with GPU offload without touching llama-cpp.
    svc._model = object()
    svc._loaded_model_path = "/tmp/model.gguf"
    svc._loaded_model_id = "local-test"
    svc._loaded_n_ctx = 4096
    svc._loaded_n_gpu_layers = -1
    status = svc.get_status()
    assert status["loaded"] is True
    assert status["n_gpu_layers"] == -1
    assert status["gpu_active"] is True
    assert status["n_ctx"] == 4096


def test_status_gpu_inactive_on_cpu_load(monkeypatch):
    monkeypatch.setattr(lms, "_supports_gpu_offload", lambda: False)
    svc = lms.LocalModelService()
    svc._model = object()
    svc._loaded_n_gpu_layers = 0
    status = svc.get_status()
    assert status["gpu_active"] is False
