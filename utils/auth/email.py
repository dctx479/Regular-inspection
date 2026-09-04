"""
邮箱密码认证器 - 使用用户名和密码进行表单登录
"""

from typing import Any, Dict, Optional, Tuple

from playwright.async_api import BrowserContext, Page

from utils.auth.base import Authenticator, logger
from utils.constants import (
    EMAIL_INPUT_SELECTORS,
    LOGIN_BUTTON_SELECTORS,
    POPUP_CLOSE_SELECTORS,
    TimeoutConfig,
)
from utils.sanitizer import sanitize_exception
from utils.session_cache import SessionCache

# 会话缓存实例
session_cache = SessionCache()


class EmailAuthenticator(Authenticator):
    """邮箱密码认证"""

    async def _close_popups(self, page: Page):
        """关闭可能的弹窗"""
        try:
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(TimeoutConfig.VERY_SHORT_WAIT)
            for sel in POPUP_CLOSE_SELECTORS:
                try:
                    close_btn = await page.query_selector(sel)
                    if close_btn:
                        await close_btn.click()
                        await page.wait_for_timeout(TimeoutConfig.VERY_SHORT_WAIT)
                        break
                except Exception:
                    continue
        except Exception:
            pass

    async def _find_and_click_email_tab(self, page: Page) -> bool:
        """查找并点击邮箱登录选项"""
        logger.info(f"🔍 [{self.auth_config.username}] 查找邮箱登录选项...")

        # 等待页面交互元素就绪
        try:
            await page.wait_for_timeout(1500)
        except Exception:
            pass

        for sel in [
            'button:has-text("邮箱")',
            'a:has-text("邮箱")',
            'button:has-text("Email")',
            'a:has-text("Email")',
            'text=邮箱登录',
            'text=Email Login',
        ]:
            try:
                el = await page.query_selector(sel)
                if el:
                    logger.info(f"✅ [{self.auth_config.username}] 找到邮箱登录选项: {sel}")
                    await el.click()
                    await page.wait_for_timeout(800)
                    return True
            except Exception:
                continue
        return False

    async def _find_email_input(self, page: Page):
        """查找邮箱输入框"""
        logger.info(f"🔍 [{self.auth_config.username}] 查找邮箱输入框...")
        email_input = None
        for sel in EMAIL_INPUT_SELECTORS:
            try:
                email_input = await page.query_selector(sel)
                if email_input:
                    logger.info(f"✅ [{self.auth_config.username}] 找到邮箱输入框: {sel}")
                    return email_input
            except Exception:
                continue

        # 调试信息
        if not email_input:
            await self._debug_page_inputs(page)
        return None

    async def _debug_page_inputs(self, page: Page):
        """输出调试信息"""
        try:
            page_title = await page.title()
            page_url = page.url
            logger.error(f"❌ [{self.auth_config.username}] 邮箱输入框未找到")
            logger.info(f"   当前页面: {page_title}")
            logger.info(f"   当前URL: {page_url}")

            # 查找所有输入框
            all_inputs = await page.query_selector_all('input')
            logger.info(f"   页面共有 {len(all_inputs)} 个输入框")
            for i, inp in enumerate(all_inputs[:5]):  # 只显示前5个
                try:
                    inp_type = await inp.get_attribute('type')
                    inp_name = await inp.get_attribute('name')
                    inp_placeholder = await inp.get_attribute('placeholder')
                    logger.info(f"     输入框{i+1}: type={inp_type}, name={inp_name}, placeholder={inp_placeholder}")
                except Exception:
                    logger.info(f"     输入框{i+1}: 无法获取属性")
        except Exception as e:
            logger.info(f"   调试信息获取失败: {e}")

    async def _find_and_click_login_button(self, page: Page):
        """查找并点击登录按钮"""
        for sel in LOGIN_BUTTON_SELECTORS:
            try:
                login_button = await page.query_selector(sel)
                if login_button:
                    return login_button
            except Exception:
                continue
        return None

    async def _try_cached_session(
        self, page: Page, context: BrowserContext
    ) -> Optional[Dict[str, Any]]:
        """尝试复用本地会话缓存，缓存失效时立即删除。"""
        try:
            cached = session_cache.load(
                account_name=self.account_name,
                provider=self.provider_config.name,
            )
            if not cached or not cached.get("cookies"):
                return None

            logger.info(f"♻️ [{self.auth_config.username}] 尝试复用会话缓存...")
            await context.add_cookies(cached["cookies"])
            await page.goto(
                f"{self.provider_config.base_url}/panel",
                wait_until="domcontentloaded",
                timeout=TimeoutConfig.PAGE_LOAD,
            )
            await page.wait_for_timeout(TimeoutConfig.SHORT_WAIT_2)

            api_user = cached.get("user_id") or self.auth_config.api_user
            validation = await self._validate_authenticated_session(
                page, context, api_user
            )
            if validation.get("success"):
                logger.info(f"✅ [{self.auth_config.username}] 会话缓存验证成功")
                return {
                    "success": True,
                    "cookies": validation.get("cookies", {}),
                    "user_id": validation.get("user_id") or cached.get("user_id"),
                    "username": validation.get("username") or cached.get("username"),
                }

            logger.warning(
                f"⚠️ [{self.auth_config.username}] 会话缓存已失效，删除后重新登录"
            )
            session_cache.delete(self.account_name, self.provider_config.name)
            try:
                await context.clear_cookies()
                await page.goto(
                    self.provider_config.get_login_url(),
                    wait_until="domcontentloaded",
                    timeout=TimeoutConfig.PAGE_LOAD,
                )
            except Exception as nav_error:
                logger.debug(
                    f"⚠️ [{self.auth_config.username}] 返回登录页失败: {nav_error}"
                )
        except Exception as e:
            # 缓存损坏或无法注入时不阻断正常登录流程。
            logger.debug(f"⚠️ [{self.auth_config.username}] 复用会话缓存失败: {e}")
        return None

    async def _check_login_success(
        self, page: Page, context: BrowserContext
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """验证登录是否真正建立了可用会话。

        页面 URL、标题或 CSS 元素都可能在登录失败时保持正常外观；最终以
        当前浏览器上下文访问用户信息 API 的结果为准。
        """
        current_url = page.url
        logger.info(f"🔍 [{self.auth_config.username}] 登录后URL: {current_url}")

        error_msg = await self._check_error_messages(page)
        if error_msg:
            return False, error_msg, None, None

        if "login" in current_url.lower():
            logger.warning(
                f"⚠️ [{self.auth_config.username}] 仍在登录页面，不能仅凭页面元素判定成功"
            )

        # localStorage 中的 ID 是登录后最可靠的候选值；如果配置中显式提供
        # api_user，则作为没有 localStorage 数据时的备用候选。
        local_user_id, local_username = await self._extract_user_from_localstorage(page)
        api_user = local_user_id or self.auth_config.api_user
        if api_user:
            logger.info(f"🔑 [{self.auth_config.username}] 使用 API User 验证会话: {api_user}")
        else:
            logger.info(f"ℹ️ [{self.auth_config.username}] 未找到 API User，尝试由会话 API 返回用户信息")

        validation = await self._validate_authenticated_session(page, context, api_user)

        # 如果 localStorage 中的值和显式配置不同，允许用显式值再验证一次，
        # 但绝不从显示名称或邮箱地址猜测用户 ID。
        if (
            not validation.get("success")
            and local_user_id
            and self.auth_config.api_user
            and str(local_user_id) != str(self.auth_config.api_user)
        ):
            validation = await self._validate_authenticated_session(
                page, context, self.auth_config.api_user
            )

        if validation.get("success"):
            return (
                True,
                None,
                validation.get("user_id") or local_user_id,
                validation.get("username") or local_username,
            )

        error = validation.get("error") or "登录后会话验证失败"
        status = validation.get("status")
        if "login" in page.url.lower():
            error = f"Login failed - still on login page ({error})"
        elif status in (401, 403):
            error = f"登录后用户信息 API 返回 HTTP {status}，会话未建立"

        return False, error, None, None

    async def _check_error_messages(self, page: Page) -> Optional[str]:
        """检查错误提示信息"""
        try:
            error_selectors = ['.error', '.alert-danger', '[class*="error"]', '.toast-error', '[role="alert"]']
            for sel in error_selectors:
                error_msg = await page.query_selector(sel)
                if error_msg:
                    try:
                        error_text = await error_msg.inner_text()
                        if error_text and error_text.strip():
                            # 检查是否是成功消息
                            success_keywords = ['成功', 'success', '登录成功', 'login success']
                            error_keywords = ['失败', '错误', 'error', 'invalid', 'incorrect', '验证码', 'captcha']

                            error_text_lower = error_text.lower()
                            is_success = any(keyword in error_text_lower for keyword in success_keywords)
                            is_real_error = any(keyword in error_text_lower for keyword in error_keywords)

                            if is_real_error:
                                logger.error(f"❌ [{self.auth_config.username}] 登录错误: {error_text}")
                                return f"Login failed: {error_text}"
                            elif is_success:
                                logger.info(f"✅ [{self.auth_config.username}] 检测到成功消息: {error_text}")
                            else:
                                logger.warning(f"⚠️ [{self.auth_config.username}] 检测到消息: {error_text}")
                    except Exception:
                        pass
        except Exception:
            pass
        return None

    async def authenticate(self, page: Page, context: BrowserContext) -> Dict[str, Any]:
        """使用邮箱密码登录"""
        try:
            logger.info("ℹ️ Starting Email authentication")

            if not await self._init_page_and_check_cloudflare(page):
                return {"success": False, "error": "Cloudflare verification timeout"}

            cached_result = await self._try_cached_session(page, context)
            if cached_result:
                return cached_result

            await self._close_popups(page)
            await self._find_and_click_email_tab(page)
            await page.wait_for_timeout(TimeoutConfig.SHORT_WAIT_2)

            email_input = await self._find_email_input(page)
            if not email_input:
                return {"success": False, "error": "Email input field not found"}

            password_input = await page.query_selector('input[type="password"]')
            if not password_input:
                return {"success": False, "error": "Password input field not found"}

            await email_input.fill(self.auth_config.username)

            error = await self._fill_password(password_input)
            if error:
                return {"success": False, "error": error}

            login_button = await self._find_and_click_login_button(page)
            if not login_button:
                return {"success": False, "error": "Login button not found"}

            logger.info(f"🔑 [{self.auth_config.username}] 点击登录按钮...")
            await login_button.click()

            try:
                await page.wait_for_load_state("networkidle", timeout=TimeoutConfig.MEDIUM_WAIT_10)
                await page.wait_for_timeout(TimeoutConfig.SHORT_WAIT_2)
            except Exception:
                logger.warning(f"⚠️ [{self.auth_config.username}] 页面加载超时，继续检查登录状态...")

            success, error_msg, user_id, username = await self._check_login_success(
                page, context
            )
            if not success:
                return {"success": False, "error": error_msg}

            final_cookies = await context.cookies()
            cookies_dict = {cookie["name"]: cookie["value"] for cookie in final_cookies}

            if not self._has_authenticated_cookie(cookies_dict):
                logger.warning(f"⚠️ [{self.auth_config.username}] 未找到session cookie")

            logger.info(f"✅ [{self.auth_config.username}] 邮箱认证完成，获取到 {len(cookies_dict)} 个cookies")

            # 保存会话缓存
            try:
                session_cache.save(
                    account_name=self.account_name,
                    provider=self.provider_config.name,
                    cookies=final_cookies,
                    user_id=user_id,
                    username=username,
                    expiry_hours=24
                )
                logger.info(f"✅ [{self.auth_config.username}] 会话已缓存（24小时有效）")
            except Exception as cache_error:
                logger.warning(f"⚠️ [{self.auth_config.username}] 缓存保存失败: {cache_error}")

            return {"success": True, "cookies": cookies_dict, "user_id": user_id, "username": username}

        except Exception as e:
            return {"success": False, "error": f"Email auth failed: {sanitize_exception(e)}"}
