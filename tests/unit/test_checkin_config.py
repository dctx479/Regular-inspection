"""签到请求头和账号间冷却的回归测试。"""

import pytest

from checkin import CheckIn
from main import get_account_delay_seconds, validate_env_vars
from utils.auth_method import AuthMethod
from utils.config import AccountConfig, AuthConfig, ProviderConfig
from utils.retry import retry_on_status


@pytest.fixture
def checkin_instance():
    account = AccountConfig(name="test", provider="anyrouter")
    provider = ProviderConfig(
        name="TestProvider",
        base_url="https://test.example.com",
        login_url="https://test.example.com/login",
        checkin_url="https://test.example.com/api/sign_in",
        user_info_url="https://test.example.com/api/user",
        api_user_key="X-User-Id",
    )
    return CheckIn(account, provider)


def test_api_user_inference_only_accepts_unambiguous_suffix(checkin_instance):
    assert checkin_instance._infer_api_user("linuxdo_84404") == "84404"
    assert checkin_instance._infer_api_user("zx2021") is None
    assert checkin_instance._infer_api_user("zj") is None


def test_provider_specific_api_user_header(checkin_instance):
    headers = checkin_instance._build_request_headers("12345")
    assert headers["X-User-Id"] == "12345"
    assert "New-Api-User" not in headers


def test_account_delay_can_be_disabled(monkeypatch):
    monkeypatch.setenv("ACCOUNT_DELAY_ENABLED", "false")
    assert get_account_delay_seconds() == 0.0


def test_account_delay_range(monkeypatch):
    monkeypatch.setenv("ACCOUNT_DELAY_ENABLED", "true")
    monkeypatch.setenv("ACCOUNT_DELAY_MIN_SECONDS", "2")
    monkeypatch.setenv("ACCOUNT_DELAY_MAX_SECONDS", "4")
    delay = get_account_delay_seconds()
    assert 2 <= delay <= 4


def test_server_push_is_detected_by_environment_validation(monkeypatch):
    monkeypatch.setenv("ACCOUNTS", '[{"name":"test","cookies":{"session":"v"}}]')
    monkeypatch.setenv("SERVERPUSHKEY", "test-key")
    monkeypatch.delenv("EMAIL_USER", raising=False)
    monkeypatch.delenv("EMAIL_PASS", raising=False)
    monkeypatch.delenv("EMAIL_TO", raising=False)

    # 仅验证通知误报已消失；账号 JSON 由后续 load_accounts 流程验证。
    assert validate_env_vars() is True


@pytest.mark.asyncio
async def test_retry_on_status_retries_403(monkeypatch):
    monkeypatch.setenv("STATUS_RETRY_COUNT", "1")
    monkeypatch.setenv("STATUS_RETRY_BASE_SECONDS", "0")
    monkeypatch.setenv("STATUS_RETRY_MAX_SECONDS", "0")

    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"status": 403, "ok": False}
        return {"status": 200, "ok": True}

    class TestLogger:
        def warning(self, _message):
            pass

    result = await retry_on_status(
        operation,
        logger=TestLogger(),
        operation_name="test",
        retry_statuses=(403,),
    )

    assert calls == 2
    assert result["status"] == 200


@pytest.mark.asyncio
async def test_auth_stage_retries_temporary_403(monkeypatch, checkin_instance):
    monkeypatch.setenv("STATUS_RETRY_COUNT", "1")
    monkeypatch.setenv("STATUS_RETRY_BASE_SECONDS", "0")
    monkeypatch.setenv("STATUS_RETRY_MAX_SECONDS", "0")

    auth_config = AuthConfig(
        method=AuthMethod.EMAIL,
        username="test@example.com",
        password="StrongP@ss1",
    )
    calls = 0

    async def fake_checkin(_auth_config):
        nonlocal calls
        calls += 1
        if calls == 1:
            return False, {"error": "HTTP 403", "retry_auth": True}
        return True, {"success": True}

    checkin_instance._checkin_with_auth = fake_checkin
    result = await checkin_instance._checkin_with_auth_with_retry(auth_config)

    assert calls == 2
    assert result == (True, {"success": True})
