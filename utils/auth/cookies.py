"""
Cookies 认证器 - 使用预设的 Cookies 进行认证
"""

import asyncio
from typing import Any, Dict, Optional, Tuple

from playwright.async_api import BrowserContext, Page

from utils.auth.base import Authenticator, logger
from utils.sanitizer import sanitize_exception


class CookiesAuthenticator(Authenticator):
    """Cookies 认证"""

    async def _validate_cookies_with_precheck(
        self,
        page: Page,
        context: BrowserContext,
        cookies_dict: Dict[str, str]
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Cookies 有效性预检机制（增强版）

        Returns:
            Tuple[bool, Optional[str], Optional[str], Optional[str]]:
                (是否有效, 用户ID, 用户名, 错误信息)
        """
        try:
            logger.info(f"🔍 [{self.account_name}] 等待 Cookies 应用到浏览器上下文...")
            await asyncio.sleep(1)

            # 页面能返回 200 只代表 SPA 外壳可访问，不能作为认证依据。
            logger.info(f"🔍 [{self.account_name}] 步骤1: 访问用户中心验证 Cookies...")
            test_urls = [
                f"{self.provider_config.base_url}/panel",
                f"{self.provider_config.base_url}/dashboard",
                f"{self.provider_config.base_url}/",
            ]
            navigation_success = False
            for test_url in test_urls:
                try:
                    await page.goto(test_url, wait_until="domcontentloaded", timeout=20000)
                    navigation_success = True
                    logger.info(f"✅ [{self.account_name}] 成功访问: {test_url}")
                    break
                except Exception as nav_error:
                    logger.debug(f"⚠️ [{self.account_name}] 访问 {test_url} 失败: {nav_error}")

            if not navigation_success:
                return False, None, None, "Unable to navigate to any test URL"

            await asyncio.sleep(2)
            page_content = await page.content()
            current_url = page.url

            # 检查 WAF 挑战，但挑战通过后仍必须进行 API 认证验证。
            cf_indicators = [
                "checking your browser",
                "just a moment",
                "cf-challenge",
                "challenge-platform",
                "cloudflare",
                "ddos protection",
            ]
            if any(indicator in page_content.lower() for indicator in cf_indicators):
                logger.warning(f"⚠️ [{self.account_name}] 检测到 Cloudflare 拦截，等待验证完成...")
                if not await self._wait_for_cloudflare_bypass(page, max_wait=15):
                    return False, None, None, "Cloudflare challenge not passed"

                current_url = page.url

            if "/login" in current_url.lower():
                logger.warning(f"⚠️ [{self.account_name}] 被重定向到登录页，Cookies 可能已失效")

            # 优先使用显式 api_user；只有名称末尾存在明确数字 ID 时才允许推断。
            api_user = self.auth_config.api_user or self._infer_api_user(self.account_name)
            if api_user:
                logger.info(f"🔑 [{self.account_name}] 使用 API User: {api_user}")
            else:
                logger.warning(f"⚠️ [{self.account_name}] 未配置可靠的 API User，将尝试不带用户头验证")

            logger.info(f"🔍 [{self.account_name}] 步骤2: 通过浏览器 API 验证 Cookies...")
            validation = await self._validate_authenticated_session(page, context, api_user)

            # 如果配置的 ID 不正确，但页面里能读到真实 ID，再用真实 ID 重试一次。
            if not validation.get("success"):
                logger.info(f"🔍 [{self.account_name}] API 首次验证失败，尝试从 localStorage 获取真实用户 ID...")
                local_user_id, local_username = await self._extract_user_from_localstorage(page)
                if local_user_id and str(local_user_id) != str(api_user or ""):
                    validation = await self._validate_authenticated_session(
                        page, context, local_user_id
                    )
                    if validation.get("success"):
                        return (
                            True,
                            validation.get("user_id") or str(local_user_id),
                            validation.get("username") or local_username,
                            None,
                        )

            if validation.get("success"):
                logger.info(
                    f"✅ [{self.account_name}] 浏览器 API 验证通过: "
                    f"ID={validation.get('user_id')}, 用户名={validation.get('username')}"
                )
                return (
                    True,
                    validation.get("user_id"),
                    validation.get("username"),
                    None,
                )

            error = validation.get("error") or "Cookies validation failed"
            status = validation.get("status")
            if status in (401, 403):
                error = (
                    f"认证 API 返回 HTTP {status}，Cookie 可能已过期、被撤销，"
                    "或 api_user 与 Cookie 不匹配"
                )

            # 无论页面是否能打开，都不能以账号名作为用户 ID 放行。
            logger.error(f"❌ [{self.account_name}] Cookies 预检未通过: {error}")
            return False, None, None, error

        except Exception as e:
            logger.error(f"❌ [{self.account_name}] Cookies 预检异常: {e}")
            return False, None, None, f"Validation error: {sanitize_exception(e)}"

    async def _wait_for_cloudflare_bypass(
        self,
        page: Page,
        max_wait: int = 15
    ) -> bool:
        """
        等待 Cloudflare 验证完成

        Args:
            page: Playwright 页面对象
            max_wait: 最大等待秒数

        Returns:
            bool: 是否通过验证
        """
        try:
            start_time = asyncio.get_event_loop().time()

            while asyncio.get_event_loop().time() - start_time < max_wait:
                page_content = await page.content()
                current_url = page.url

                # 检查是否还有 Cloudflare 标记
                has_cloudflare = any(
                    marker in page_content.lower()
                    for marker in [
                        "just a moment",
                        "checking your browser",
                        "cf-challenge",
                        "challenge-platform"
                    ]
                )

                # 如果没有 Cloudflare 标记，且不在验证页，说明通过了
                if not has_cloudflare:
                    page_title = await page.title()
                    if "verification" not in page_title.lower():
                        logger.info(f"✅ [{self.account_name}] Cloudflare 验证已通过")
                        return True

                # 检查是否已跳转到正常页面
                if '/login' in current_url and not has_cloudflare:
                    logger.info(f"✅ [{self.account_name}] 已跳转到登录页，验证通过")
                    return True

                # 继续等待
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                logger.info(f"   ⏳ 等待 Cloudflare 验证... ({elapsed}s/{max_wait}s)")
                await asyncio.sleep(2)

            logger.warning(f"⚠️ [{self.account_name}] Cloudflare 验证超时")
            return False

        except Exception as e:
            logger.warning(f"⚠️ [{self.account_name}] Cloudflare 等待异常: {e}")
            return False

    async def authenticate(self, page: Page, context: BrowserContext) -> Dict[str, Any]:
        """使用 Cookies 认证（增强版 - 带预检机制）"""
        try:
            # 设置 cookies
            cookies = self.auth_config.cookies
            if not cookies:
                return {"success": False, "error": "No cookies provided"}

            # 先访问目标网站，确保域名上下文正确
            logger.info(f"🌐 [{self.account_name}] 预访问目标网站以建立域名上下文...")
            try:
                await page.goto(
                    self.provider_config.base_url,
                    wait_until="domcontentloaded",
                    timeout=15000
                )
                await asyncio.sleep(1)  # 等待页面稳定
            except Exception as nav_error:
                logger.warning(f"⚠️ [{self.account_name}] 预访问失败: {nav_error}，继续尝试设置 cookies")

            # 将 cookies 字典转换为 Playwright 格式
            domain = self._get_domain(self.provider_config.base_url)
            # 移除可能的端口号
            if ':' in domain:
                domain = domain.split(':')[0]

            # 对于子域名，添加前导点以支持所有子域名
            # 例如：api.example.com -> .example.com
            domain_parts = domain.split('.')
            if len(domain_parts) > 2:
                # 使用根域名（支持所有子域名）
                domain = '.' + '.'.join(domain_parts[-2:])
            elif not domain.startswith('.'):
                # 顶级域名也添加前导点
                domain = '.' + domain

            logger.info(f"🍪 [{self.account_name}] 设置 Cookies domain: {domain}")

            cookie_list = []
            for name, value in cookies.items():
                cookie_dict = {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": "/",
                }

                # 如果是 HTTPS，添加 secure 属性
                if self.provider_config.base_url.startswith('https'):
                    cookie_dict["secure"] = True
                    # 对于跨站 cookies，需要设置 sameSite
                    cookie_dict["sameSite"] = "None"
                else:
                    cookie_dict["sameSite"] = "Lax"

                cookie_list.append(cookie_dict)

            await context.add_cookies(cookie_list)
            logger.info(f"✅ [{self.account_name}] 已添加 {len(cookie_list)} 个 cookies")

            # 获取cookies字典用于验证
            final_cookies = await context.cookies()
            cookies_dict = {cookie["name"]: cookie["value"] for cookie in final_cookies}

            # 🔥 核心改进：使用预检机制验证 Cookies
            logger.info(f"🔍 [{self.account_name}] 开始 Cookies 有效性预检...")
            is_valid, user_id, username, error_msg = await self._validate_cookies_with_precheck(
                page, context, cookies_dict
            )

            if is_valid:
                logger.info(f"✅ [{self.account_name}] Cookies 验证成功")
                return {
                    "success": True,
                    "cookies": cookies_dict,
                    "user_id": user_id,
                    "username": username
                }
            else:
                logger.error(f"❌ [{self.account_name}] Cookies 验证失败: {error_msg}")
                return {"success": False, "error": error_msg or "Cookies validation failed"}

        except Exception as e:
            error_msg = sanitize_exception(e)
            logger.error(f"❌ [{self.account_name}] Cookies 认证异常: {error_msg}")
            return {"success": False, "error": f"Cookies auth failed: {error_msg}"}
