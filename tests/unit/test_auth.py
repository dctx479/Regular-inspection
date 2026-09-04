"""
认证模块单元测试
"""
import json
from unittest.mock import AsyncMock

import pytest

from utils.auth_method import AuthMethod
from utils.config import AuthConfig


class TestCookiesAuthenticator:
    """Cookies 认证器测试"""

    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_authenticate_success(self, mock_page, mock_context, sample_provider_config):
        """测试 Cookies 认证成功场景"""
        from utils.auth import CookiesAuthenticator

        auth_config = AuthConfig(
            method=AuthMethod.COOKIES,
            cookies={"session": "test_session_value"},
            api_user="12345"
        )

        authenticator = CookiesAuthenticator(
            account_name="Test Account",
            auth_config=auth_config,
            provider_config=sample_provider_config
        )

        # Mock cookies 验证成功
        mock_context.cookies.return_value = [
            {"name": "session", "value": "test_session_value"}
        ]

        # 生产路径在浏览器上下文中使用 fetch 验证用户信息。
        mock_page.evaluate.return_value = {
            "status": 200,
            "ok": True,
            "contentType": "application/json",
            "data": {
                "success": True,
                "data": {
                    "id": "12345",
                    "username": "test_user"
                }
            }
        }

        result = await authenticator.authenticate(mock_page, mock_context)

        assert result["success"] is True
        assert result["user_id"] == "12345"
        assert result["username"] == "test_user"

    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_authenticate_expired_cookies(self, mock_page, mock_context, sample_provider_config):
        """测试 Cookies 过期场景"""
        from utils.auth import CookiesAuthenticator

        auth_config = AuthConfig(
            method=AuthMethod.COOKIES,
            cookies={"session": "expired_session"},
            api_user="12345"
        )

        authenticator = CookiesAuthenticator(
            account_name="Test Account",
            auth_config=auth_config,
            provider_config=sample_provider_config
        )

        # Mock cookies 验证失败
        mock_page.url = "https://test.com/login"
        mock_context.cookies.return_value = [
            {"name": "session", "value": "expired_session"}
        ]

        # Mock 浏览器 API 返回 401
        mock_page.evaluate.return_value = {
            "status": 401,
            "ok": False,
            "contentType": "application/json",
            "data": {"success": False, "message": "unauthorized"}
        }

        mock_page.goto = AsyncMock()

        result = await authenticator.authenticate(mock_page, mock_context)

        assert result["success"] is False
        assert "401" in result["error"]

    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_email_login_requires_authenticated_session(self, mock_page, mock_context, sample_provider_config):
        """仍在登录页时，即使存在疑似用户元素也不能判定成功。"""
        from utils.auth import EmailAuthenticator

        auth_config = AuthConfig(
            method=AuthMethod.EMAIL,
            username="test@example.com",
            password="StrongP@ss1"
        )
        authenticator = EmailAuthenticator(
            account_name="Email Account",
            auth_config=auth_config,
            provider_config=sample_provider_config
        )

        mock_page.url = "https://test.example.com/login"
        # 仅为真正的表单元素返回节点；登录页上的其它 UI 元素全部视为不存在。
        email_input = AsyncMock()
        password_input = AsyncMock()
        login_button = AsyncMock()

        def query_selector(selector):
            if selector == 'input[name="username"]':
                return email_input
            if selector == 'input[type="password"]':
                return password_input
            if selector == 'button[type="submit"]':
                return login_button
            return None

        mock_page.query_selector.side_effect = query_selector
        mock_page.evaluate.return_value = {
            "status": 403,
            "ok": False,
            "contentType": "text/html",
            "data": "forbidden"
        }
        mock_context.cookies.return_value = [
            {"name": "acw_tc", "value": "waf"},
            {"name": "cdn_sec_tc", "value": "waf"},
            {"name": "acw_sc__v2", "value": "waf"},
        ]

        result = await authenticator.authenticate(mock_page, mock_context)

        assert result["success"] is False
        assert "HTTP 403" in result["error"]


class TestEmailAuthenticator:
    """邮箱认证器测试"""

    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_authenticate_requires_api_verified_session(
        self, monkeypatch, mock_page, mock_context, sample_provider_config
    ):
        """邮箱登录只有在用户 API 验证通过后才成功。"""
        from utils.auth import EmailAuthenticator

        auth_config = AuthConfig(
            method=AuthMethod.EMAIL,
            username="test@example.com",
            password="StrongP@ss1",
        )
        authenticator = EmailAuthenticator(
            account_name="Verified Email Account",
            auth_config=auth_config,
            provider_config=sample_provider_config,
        )

        monkeypatch.setattr("utils.auth.email.session_cache.load", lambda **_kwargs: None)
        monkeypatch.setattr("utils.auth.email.session_cache.save", lambda **_kwargs: True)

        email_input = AsyncMock()
        password_input = AsyncMock()
        login_button = AsyncMock()

        def query_selector(selector):
            if selector == 'input[name="username"]':
                return email_input
            if selector == 'input[type="password"]':
                return password_input
            if selector == 'button[type="submit"]':
                return login_button
            return None

        mock_page.query_selector.side_effect = query_selector
        mock_page.url = "https://test.example.com/console"
        mock_context.cookies.return_value = [
            {"name": "session", "value": "valid-session"}
        ]

        async def evaluate(script, *_args):
            if "localStorage.getItem('user')" in script:
                return json.dumps({"id": "12345", "username": "test_user"})
            return {
                "status": 200,
                "ok": True,
                "contentType": "application/json",
                "data": {
                    "success": True,
                    "data": {"id": "12345", "username": "test_user"},
                },
            }

        mock_page.evaluate.side_effect = evaluate

        result = await authenticator.authenticate(mock_page, mock_context)

        assert result["success"] is True
        assert result["user_id"] == "12345"

    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_authenticate_no_email_input(self, mock_page, mock_context, sample_provider_config):
        """测试找不到邮箱输入框场景"""
        from utils.auth import EmailAuthenticator

        auth_config = AuthConfig(
            method=AuthMethod.EMAIL,
            username="test@example.com",
            password="password123"
        )

        authenticator = EmailAuthenticator(
            account_name="Test Account",
            auth_config=auth_config,
            provider_config=sample_provider_config
        )

        # Mock 找不到邮箱输入框
        mock_page.query_selector.return_value = None

        result = await authenticator.authenticate(mock_page, mock_context)

        assert result["success"] is False
        assert "not found" in result["error"].lower()


# 添加更多测试用例...
# TODO: 添加 GitHub 和 Linux.do 认证器测试
