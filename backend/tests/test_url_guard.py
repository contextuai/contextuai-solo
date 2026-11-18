"""SPEC-05: Always-On SSRF Blocklist (`backend/services/tools/url_guard.py`) tests."""
import socket
import pytest

from services.tools.url_guard import (
    SSRFBlockedError,
    assert_url_allowed,
    is_url_allowed,
)
from services.tools.api_tools import APITools
from services.tools.web_tools import WebTools


def test_url_guard_blocks_loopback_and_localhost():
    assert is_url_allowed("http://127.0.0.1:8080/test") is False
    assert is_url_allowed("http://127.0.1.1/secret") is False
    assert is_url_allowed("http://localhost:8000/api") is False
    assert is_url_allowed("http://[::1]:8000/api") is False
    with pytest.raises(SSRFBlockedError):
        assert_url_allowed("http://127.0.0.1:18741/api/v1/cloud-providers")


def test_url_guard_blocks_cloud_metadata_and_link_local():
    assert is_url_allowed("http://169.254.169.254/latest/meta-data/") is False
    assert is_url_allowed("http://metadata.google.internal/computeMetadata/v1/") is False
    assert is_url_allowed("http://[fe80::1]/test") is False
    assert is_url_allowed("http://0.0.0.0:8000/") is False


def test_url_guard_blocks_sidecar_port_even_on_lan():
    assert is_url_allowed("http://192.168.1.50:18741/api/v1/health") is False
    assert is_url_allowed("http://10.0.0.5:18741/v1/models") is False


def test_url_guard_allows_lan_non_sidecar_and_public_ips(monkeypatch):
    assert is_url_allowed("http://192.168.1.50:8080/status") is True

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert is_url_allowed("https://example.com/api/data") is True


def test_url_guard_blocks_dns_rebinding_to_loopback(monkeypatch):
    def fake_rebinding_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port or 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_rebinding_getaddrinfo)
    assert is_url_allowed("http://evil.rebind.attacker.com/steal") is False


@pytest.mark.asyncio
async def test_api_tools_and_web_tools_enforce_url_guard():
    api_tools = APITools()
    assert api_tools._is_safe_url("http://169.254.169.254/latest/meta-data/") is False
    assert api_tools._is_safe_url("http://127.0.0.1:18741/api/v1/health") is False

    wt = WebTools()
    res_fetch = await wt.fetch_url("http://127.0.0.1:18741/api/v1/health")
    assert res_fetch["success"] is False

    res_links = await wt.extract_links("http://169.254.169.254/latest")
    assert res_links["success"] is False

    res_status = await wt.check_url_status(["http://localhost:18741/health"])
    assert res_status["accessible_count"] == 0
    assert res_status["results"][0]["accessible"] is False
