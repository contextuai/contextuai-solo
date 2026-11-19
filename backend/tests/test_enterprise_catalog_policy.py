"""
Tests for Issue #79:
Enterprise Internal Model Catalog Override, SHA-256 Verification, and
Policy-Locked Airplane Lock.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import queue
import socketserver
import struct
import threading
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app as app_module
from routers import enterprise as enterprise_router
from services import enterprise_policy as ep
from services import hf_hub_discovery as hhd
from services import local_model_service as lms
from services import model_catalog as mc
from services import net_guard
from services.model_manager import ModelManager


def _make_gguf_bytes(payload: bytes = b"vesper-test-weights") -> bytes:
    buf = bytearray()
    buf.extend(b"GGUF")
    buf.extend(struct.pack("<I", 3))
    buf.extend(struct.pack("<Q", 0))
    buf.extend(struct.pack("<Q", 0))
    buf.extend(payload)
    return bytes(buf)


@pytest.fixture(autouse=True)
def _isolate_enterprise_env(tmp_path, monkeypatch):
    """Isolate policy/settings files, env vars, Airplane Lock, and catalog state per test."""
    for var in (
        "VESPER_AIRPLANE_LOCK_ENFORCED",
        "VESPER_CATALOG_URL",
        "CATALOG_JSON_URL",
        "VESPER_CATALOG_EXCLUSIVE",
        "VESPER_REQUIRE_SHA256",
        "VESPER_POLICY_FILE",
        "VESPER_ENTERPRISE_SETTINGS_PATH",
        "CONTEXTUAI_SIDECAR_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("VESPER_POLICY_FILE", str(tmp_path / "missing_policy.json"))
    monkeypatch.setenv(
        "VESPER_ENTERPRISE_SETTINGS_PATH",
        str(tmp_path / "user_enterprise_settings.json"),
    )
    monkeypatch.setenv("VESPER_AUDIT_DB_PATH", str(tmp_path / "audit.db"))
    ep._SHA256_CACHE.clear()
    net_guard._AIRPLANE_LOCK = False
    net_guard.clear_egress_ledger()
    hhd.restore_builtin_catalog()

    yield

    ep._SHA256_CACHE.clear()
    net_guard._AIRPLANE_LOCK = False
    net_guard.clear_egress_ledger()
    hhd.restore_builtin_catalog()


def test_default_ota_catalog_url_updated():
    assert "contextuai/vesper/main/catalog/models.json" in hhd.DEFAULT_OTA_CATALOG_URL


def test_policy_precedence_env_over_admin_over_user(tmp_path, monkeypatch):
    user_path = tmp_path / "user_enterprise_settings.json"
    user_path.write_text(
        json.dumps({
            "catalog_url": "https://user.example/models.json",
            "catalog_exclusive": True,
            "require_sha256": False,
        }),
        encoding="utf-8",
    )

    p_user = ep.get_enterprise_policy()
    assert p_user["policy_source"] == "user_settings"
    assert p_user["catalog_url"] == "https://user.example/models.json"
    assert p_user["catalog_exclusive"] is True
    assert p_user["require_sha256"] is False
    assert p_user["locked_fields"] == []

    # Admin policy overrides catalog_url and enforces airplane lock,
    # while unlocked catalog_exclusive falls through from user settings.
    admin_path = tmp_path / "policy.json"
    admin_path.write_text(
        json.dumps({
            "catalog_url": "https://corp.internal/models.json",
            "airplane_lock_enforced": True,
            "allowed_model_sha256": {"corp-7b": "a" * 64},
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("VESPER_POLICY_FILE", str(admin_path))

    p_admin = ep.get_enterprise_policy()
    assert p_admin["policy_source"] == "admin_policy"
    assert p_admin["catalog_url"] == "https://corp.internal/models.json"
    assert p_admin["catalog_exclusive"] is True
    assert p_admin["airplane_lock_enforced"] is True
    assert p_admin["allowed_model_sha256"] == {"corp-7b": "a" * 64}
    assert "catalog_url" in p_admin["locked_fields"]
    assert "airplane_lock_enforced" in p_admin["locked_fields"]
    assert "catalog_exclusive" not in p_admin["locked_fields"]

    # Env vars override admin policy
    monkeypatch.setenv("CATALOG_JSON_URL", "https://fallback-env.internal/models.json")
    p_fallback = ep.get_enterprise_policy()
    assert p_fallback["catalog_url"] == "https://fallback-env.internal/models.json"
    assert p_fallback["policy_source"] == "env"

    monkeypatch.setenv("VESPER_CATALOG_URL", "https://env.internal/models.json")
    monkeypatch.setenv("VESPER_CATALOG_EXCLUSIVE", "false")
    monkeypatch.setenv("VESPER_REQUIRE_SHA256", "true")
    monkeypatch.setenv("VESPER_AIRPLANE_LOCK_ENFORCED", "true")

    p_env = ep.get_enterprise_policy()
    assert p_env["policy_source"] == "env"
    assert p_env["catalog_url"] == "https://env.internal/models.json"
    assert p_env["catalog_exclusive"] is False
    assert p_env["require_sha256"] is True
    assert p_env["airplane_lock_enforced"] is True
    for field in ("catalog_url", "catalog_exclusive", "require_sha256", "airplane_lock_enforced"):
        assert field in p_env["locked_fields"]


def test_save_user_settings_enforces_locked_fields(tmp_path, monkeypatch):
    admin_path = tmp_path / "policy.json"
    admin_path.write_text(
        json.dumps({
            "catalog_url": "https://corp.internal/models.json",
            "airplane_lock_enforced": True,
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("VESPER_POLICY_FILE", str(admin_path))

    # Attempting to mutate locked catalog_url raises PermissionError
    with pytest.raises(PermissionError):
        ep.save_user_enterprise_settings({"catalog_url": "https://evil.example/models.json"})

    # Attempting to disable locked airplane_lock_enforced raises PermissionError
    with pytest.raises(PermissionError):
        ep.save_user_enterprise_settings({"airplane_lock_enforced": False})

    # Updating unlocked fields succeeds while keeping locked fields unchanged
    updated = ep.save_user_enterprise_settings({
        "catalog_url": "https://corp.internal/models.json",
        "catalog_exclusive": True,
        "require_sha256": True,
    })
    assert updated["catalog_exclusive"] is True
    assert updated["require_sha256"] is True
    assert updated["catalog_url"] == "https://corp.internal/models.json"


def test_airplane_lock_policy_enforced_and_privacy_router_403(tmp_path, monkeypatch):
    admin_path = tmp_path / "policy.json"
    admin_path.write_text(json.dumps({"airplane_lock_enforced": True}), encoding="utf-8")
    monkeypatch.setenv("VESPER_POLICY_FILE", str(admin_path))

    enforced, src = ep.is_airplane_lock_policy_enforced()
    assert enforced is True
    assert src == "admin_policy"
    assert net_guard.is_airplane_lock_enabled() is True

    # Loopback remains allowed
    net_guard.assert_egress_allowed("http://127.0.0.1:18741/v1/models", "local_v1")

    # External egress is blocked
    with pytest.raises(net_guard.EgressBlockedError):
        net_guard.assert_egress_allowed("https://huggingface.co/api/models", "hf_hub_search")

    # Direct service disable raises PermissionError
    with pytest.raises(PermissionError):
        net_guard.set_airplane_lock(False)

    # Privacy router returns HTTP 403 when trying to disable policy-locked Airplane Lock
    client = TestClient(app_module.app)
    r_unlock = client.post("/api/v1/privacy/airplane-lock", json={"enabled": False})
    assert r_unlock.status_code == 403

    r_ledger = client.get("/api/v1/privacy/ledger")
    assert r_ledger.status_code == 200
    ledger = r_ledger.json()
    assert ledger["airplane_lock"] is True
    assert ledger["policy_locked"] is True
    assert ledger["policy_source"] == "admin_policy"
    assert "total_allowed_requests" in ledger
    assert "total_blocked_requests" in ledger
    assert "external_connections_count" in ledger
    assert "zero_egress_verified" in ledger

    r_manifest = client.get("/api/v1/privacy/manifest")
    assert r_manifest.status_code == 200
    manifest = r_manifest.json()
    assert manifest["telemetry"] == "none"
    assert manifest["policy_locked"] is True
    assert manifest["airplane_lock"] is True


@pytest.mark.asyncio
async def test_local_path_and_file_uri_catalog_sync_under_airplane_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("VESPER_AIRPLANE_LOCK_ENFORCED", "true")
    assert net_guard.is_airplane_lock_enabled() is True

    manifest = tmp_path / "enterprise_models.json"
    cache_file = tmp_path / "cache.json"
    sample_sha = "b" * 64
    manifest.write_text(
        json.dumps({
            "models": [
                {
                    "id": "corp-airgap-7b",
                    "name": "Corp Airgap 7B",
                    "download_url": "https://mirror.corp.internal/corp-airgap-7b.gguf",
                    "sha256": sample_sha,
                    "hf_filename": "corp-airgap-7b.gguf",
                }
            ]
        }),
        encoding="utf-8",
    )

    # 1. Raw local filesystem path succeeds with Airplane Lock ON
    monkeypatch.setenv("VESPER_CATALOG_URL", str(manifest))
    res_path = await hhd.refresh_ota_catalog(cache_path=str(cache_file))
    assert res_path["source"] == "local_file"
    assert res_path["merged_count"] == 1
    entry = mc.get_model("corp-airgap-7b")
    assert entry is not None
    assert entry["sha256"] == sample_sha
    assert entry["download_url"] == "https://mirror.corp.internal/corp-airgap-7b.gguf"
    assert len(net_guard.get_egress_ledger()["entries"]) == 0

    # 2. file:// URI succeeds with Airplane Lock ON
    hhd.restore_builtin_catalog()
    monkeypatch.setenv("VESPER_CATALOG_URL", manifest.as_uri())
    res_uri = await hhd.refresh_ota_catalog(cache_path=str(cache_file))
    assert res_uri["source"] == "local_file"
    assert mc.get_model("corp-airgap-7b") is not None
    assert len(net_guard.get_egress_ledger()["entries"]) == 0

    # 3. External HTTPS URL is still blocked by Airplane Lock
    monkeypatch.setenv("VESPER_CATALOG_URL", "https://external.example/models.json")
    with pytest.raises(net_guard.EgressBlockedError):
        await hhd.refresh_ota_catalog(cache_path=str(cache_file))


@pytest.mark.asyncio
async def test_exclusive_catalog_mode_and_restore_builtin(tmp_path, monkeypatch):
    initial_id = id(mc.LOCAL_MODEL_CATALOG)
    initial_count = len(mc.LOCAL_MODEL_CATALOG)
    assert mc.get_model("qwen2.5-7b") is not None

    manifest = tmp_path / "exclusive_models.json"
    cache_file = tmp_path / "cache.json"
    manifest.write_text(
        json.dumps({
            "models": [
                {
                    "id": "approved-corp-model",
                    "name": "Approved Corp Model",
                    "hf_repo": "corp/approved-gguf",
                    "hf_filename": "approved-corp.gguf",
                    "sha256": "c" * 64,
                }
            ]
        }),
        encoding="utf-8",
    )

    monkeypatch.setenv("VESPER_CATALOG_URL", str(manifest))
    monkeypatch.setenv("VESPER_CATALOG_EXCLUSIVE", "true")

    res_excl = await hhd.refresh_ota_catalog(cache_path=str(cache_file))
    assert res_excl["exclusive"] is True
    assert res_excl["total_catalog_models"] == 1
    assert id(mc.LOCAL_MODEL_CATALOG) == initial_id
    assert mc.get_model("approved-corp-model") is not None
    assert mc.get_model("qwen2.5-7b") is None

    # Turn exclusive mode off and refresh -> built-in catalog restored cleanly
    monkeypatch.setenv("VESPER_CATALOG_EXCLUSIVE", "false")
    res_restored = await hhd.refresh_ota_catalog(cache_path=str(cache_file))
    assert res_restored["exclusive"] is False
    assert id(mc.LOCAL_MODEL_CATALOG) == initial_id
    assert len(mc.LOCAL_MODEL_CATALOG) >= initial_count
    assert mc.get_model("qwen2.5-7b") is not None


def test_sha256_verification_pass_fail_and_cache(tmp_path, monkeypatch):
    gguf_file = tmp_path / "sample.gguf"
    raw = _make_gguf_bytes(b"deterministic-gguf-content")
    gguf_file.write_bytes(raw)
    expected = hashlib.sha256(raw).hexdigest()

    digest1 = ep.compute_file_sha256(str(gguf_file))
    digest2 = ep.compute_file_sha256(str(gguf_file))
    assert digest1 == expected
    assert digest2 == expected

    # Valid hash passes
    res_ok = ep.verify_gguf_sha256(str(gguf_file), expected)
    assert res_ok == {"verified": True, "sha256": expected, "expected_sha256": expected}

    # Mismatched hash raises ModelIntegrityError
    with pytest.raises(ep.ModelIntegrityError, match="mismatch"):
        ep.verify_gguf_sha256(str(gguf_file), "0" * 64)

    # Missing expected hash when require_checksum=True raises ModelIntegrityError
    with pytest.raises(ep.ModelIntegrityError):
        ep.verify_gguf_sha256(str(gguf_file), None, require_checksum=True)

    # Missing expected hash when require_checksum=False returns verified=False
    res_unverified = ep.verify_gguf_sha256(str(gguf_file), None, require_checksum=False)
    assert res_unverified == {"verified": False, "sha256": expected, "expected_sha256": None}

    # Env VESPER_REQUIRE_SHA256 enforces checksum requirement automatically
    monkeypatch.setenv("VESPER_REQUIRE_SHA256", "true")
    with pytest.raises(ep.ModelIntegrityError):
        ep.verify_gguf_sha256(str(gguf_file), None)


def test_local_model_service_integrity_block_and_n_ctx(tmp_path, monkeypatch):
    svc = lms.LocalModelService()
    assert svc.get_loaded_n_ctx(fallback=8192) == 8192

    good_bytes = _make_gguf_bytes(b"trusted-weights-v1")
    good_sha = hashlib.sha256(good_bytes).hexdigest()
    gguf_path = tmp_path / "corp-guard-test.gguf"
    gguf_path.write_bytes(good_bytes)

    hhd.merge_catalog_entries([
        {
            "id": "corp-guard-test",
            "name": "Corp Guard Test",
            "hf_repo": "corp/guard",
            "hf_filename": "corp-guard-test.gguf",
            "sha256": good_sha,
        }
    ])

    # Tamper the file on disk after catalog registration
    gguf_path.write_bytes(_make_gguf_bytes(b"tampered-weights-evil"))

    class _FailIfCalledLlama:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Llama must never be instantiated for tampered GGUF")

    monkeypatch.setattr(lms, "LLAMA_CPP_AVAILABLE", True)
    monkeypatch.setattr(lms, "Llama", _FailIfCalledLlama)

    # Must raise ModelIntegrityError outside/before retry loop
    with pytest.raises(ep.ModelIntegrityError):
        svc._ensure_model(str(gguf_path))

    # Restore untampered file -> Llama loads and get_loaded_n_ctx reflects loaded ctx
    gguf_path.write_bytes(good_bytes)
    loaded_instances = []

    class _FakeLlama:
        def __init__(self, **kwargs):
            loaded_instances.append(kwargs)

        def close(self):
            pass

    monkeypatch.setattr(lms, "Llama", _FakeLlama)
    monkeypatch.setattr(svc, "_compute_dynamic_n_ctx", lambda *a, **kw: 16384)
    svc._ensure_model(str(gguf_path))
    assert len(loaded_instances) == 1
    assert svc.get_loaded_n_ctx() == 16384
    svc.unload_model()


def test_model_manager_download_url_and_sha256_tamper_unlink(tmp_path):
    good_bytes = _make_gguf_bytes(b"enterprise-mirror-gguf-payload")
    good_sha = hashlib.sha256(good_bytes).hexdigest()

    serve_dir = tmp_path / "mirror"
    serve_dir.mkdir()
    (serve_dir / "corp-mirror.gguf").write_bytes(good_bytes)

    class _QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(serve_dir), **kwargs)

        def log_message(self, format, *args):
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), _QuietHandler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            mirror_url = f"http://127.0.0.1:{port}/corp-mirror.gguf"

            # 1. Valid SHA-256 download from custom download_url succeeds even under Airplane Lock
            net_guard.set_airplane_lock(True)
            hhd.merge_catalog_entries([
                {
                    "id": "corp-mirror-valid",
                    "name": "Corp Mirror Valid",
                    "hf_repo": "enterprise",
                    "hf_filename": "corp-mirror.gguf",
                    "download_url": mirror_url,
                    "sha256": good_sha,
                }
            ])

            models_dir_ok = tmp_path / "models_ok"
            mgr_ok = ModelManager(models_dir=str(models_dir_ok))
            res_ok = mgr_ok._download_files(
                repo_id="enterprise",
                filename="corp-mirror.gguf",
                model_id="corp-mirror-valid",
                progress_queue=queue.Queue(),
            )
            assert "error" not in res_ok
            assert res_ok["verified"] is True
            assert res_ok["sha256"] == good_sha
            assert (models_dir_ok / "corp-mirror.gguf").is_file()

            installed = mgr_ok.list_installed()
            assert len(installed) == 1
            assert installed[0]["expected_sha256"] == good_sha

            # 2. Tampered / mismatched SHA-256 unlinks downloaded file and returns error
            hhd.merge_catalog_entries([
                {
                    "id": "corp-mirror-bad",
                    "name": "Corp Mirror Bad",
                    "hf_repo": "enterprise",
                    "hf_filename": "corp-mirror-bad.gguf",
                    "download_url": mirror_url,
                    "sha256": "f" * 64,
                }
            ])
            models_dir_bad = tmp_path / "models_bad"
            mgr_bad = ModelManager(models_dir=str(models_dir_bad))
            res_bad = mgr_bad._download_files(
                repo_id="enterprise",
                filename="corp-mirror-bad.gguf",
                model_id="corp-mirror-bad",
                progress_queue=queue.Queue(),
            )
            assert "error" in res_bad
            assert "mismatch" in res_bad["error"].lower()
            assert not (models_dir_bad / "corp-mirror-bad.gguf").exists()
        finally:
            httpd.shutdown()


def test_enterprise_router_endpoints(tmp_path, monkeypatch):
    test_app = FastAPI()
    test_app.include_router(enterprise_router.router)
    client = TestClient(test_app)

    # Create local enterprise manifest
    manifest = tmp_path / "corp_catalog.json"
    gguf_bytes = _make_gguf_bytes(b"router-verify-weights")
    gguf_sha = hashlib.sha256(gguf_bytes).hexdigest()
    manifest.write_text(
        json.dumps({
            "models": [
                {
                    "id": "corp-router-model",
                    "name": "Corp Router Model",
                    "hf_repo": "corp/router",
                    "hf_filename": "corp-router-model.gguf",
                    "sha256": gguf_sha,
                }
            ]
        }),
        encoding="utf-8",
    )

    # 1. GET /policy
    r_get = client.get("/api/v1/enterprise/policy")
    assert r_get.status_code == 200
    assert r_get.json()["policy_source"] == "default"

    # 2. PUT /policy unlocked update succeeds
    r_put = client.put(
        "/api/v1/enterprise/policy",
        json={
            "catalog_url": str(manifest),
            "catalog_exclusive": True,
            "require_sha256": True,
        },
    )
    assert r_put.status_code == 200
    assert r_put.json()["catalog_url"] == str(manifest)
    assert r_put.json()["catalog_exclusive"] is True

    # 3. POST /catalog/sync works while Airplane Lock is enforced
    monkeypatch.setenv("VESPER_AIRPLANE_LOCK_ENFORCED", "true")
    r_sync = client.post("/api/v1/enterprise/catalog/sync")
    assert r_sync.status_code == 200
    assert r_sync.json()["source"] == "local_file"
    assert r_sync.json()["merged_count"] == 1
    assert r_sync.json()["total_catalog_models"] == 1

    # 4. PUT /policy returns 403 when attempting to modify env-locked field
    monkeypatch.setenv("VESPER_REQUIRE_SHA256", "true")
    r_put_locked = client.put(
        "/api/v1/enterprise/policy",
        json={"require_sha256": False},
    )
    assert r_put_locked.status_code == 403

    # 5. POST /models/{model_id}/verify
    models_dir = tmp_path / "models_router"
    models_dir.mkdir()
    local_mgr = ModelManager(models_dir=str(models_dir))
    monkeypatch.setattr(enterprise_router, "model_manager", local_mgr)

    # Not installed -> 404
    r_missing = client.post("/api/v1/enterprise/models/corp-router-model/verify")
    assert r_missing.status_code == 404

    # Installed & valid -> 200 verified=True
    model_file = models_dir / "corp-router-model.gguf"
    model_file.write_bytes(gguf_bytes)
    r_ok = client.post("/api/v1/enterprise/models/corp-router-model/verify")
    assert r_ok.status_code == 200
    assert r_ok.json()["verified"] is True
    assert r_ok.json()["sha256"] == gguf_sha

    # Tampered -> 422
    model_file.write_bytes(_make_gguf_bytes(b"corrupted-by-attacker"))
    r_tamper = client.post("/api/v1/enterprise/models/corp-router-model/verify")
    assert r_tamper.status_code == 422
