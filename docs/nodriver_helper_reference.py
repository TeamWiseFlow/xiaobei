from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

import regex as re
from patchright.async_api import BrowserContext, Page, Playwright, async_playwright

from core.async_logger import base_directory, wis_logger

from .patchright_storage import PATCHRIGHT_USER_DATA_DIR
from .ws_connect import ask_user, notify_user

PLATFORM_LOGIN_URLS = {
    "ks": "https://www.kuaishou.com/",
    "wb": "https://weibo.cn/",
    "mp": "https://mp.weixin.qq.com/cgi-bin/loginpage",
    "bili": "https://www.bilibili.com",
    "dy": "https://www.douyin.com",
    "xhs": "https://www.xiaohongshu.com",
    "zhihu": "https://www.zhihu.com/search?q=huawei&search_source=Guess&utm_content=search_hot&type=content",
}


@dataclass(frozen=True)
class CookieRecord:
    name: str
    value: str
    domain: str
    expires: float = 0

    @classmethod
    def from_dict(cls, value: dict) -> "CookieRecord":
        return cls(
            name=value.get("name", ""),
            value=value.get("value", ""),
            domain=value.get("domain", ""),
            expires=float(value.get("expires", 0) or 0),
        )


#############################
# PatchrightHelper 会新开 chrome 进程打开页面，与用户 dashboard 并不共享页面或者浏览器实例
# 因此它的很多 ask_user 的消息，不能根据用户是否回传确定实际状态，仅仅是起到 确保用户看到 + 等待 的作用
# （用户可能是看到并点击确认后再去操作，也可能操作后再点击确定，或者根本此时没有打开 dashboard）
# 除了正常结果反馈外，存在三种异常结果：
# valueerror —— 这是程序问题，由上层捕获并处理（包括日志记录），错误信息可以直接获得
# RuntimeError —— 这一类都是主动发起的，并在这里已经做了日志和用户通知，上层捕获后，仅需决定放行策略即可，包括 13、70、17、18
# 至于页面打不开、等待超时后的反馈的需要即时通知的消息，这里已经处理，上层无需再操作
#############################


class NodriverHelper:
    def __init__(self, platform: str):
        """
        initialize helper

        Args:
            platform: platform name, like 'wb', 'zhihu' , or just use the domain.
        """
        self.platform = platform
        self.playwright: Optional[Playwright] = None
        # 为兼容已有字段名，browser 现在实际是 patchright 的 BrowserContext
        self.browser: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        self.browser_data = PATCHRIGHT_USER_DATA_DIR
        self.export_dir = base_directory / "nodriver_exported" / platform

        self.export_dir.mkdir(parents=True, exist_ok=True)

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()

    def _build_launch_args(self) -> dict:
        launch_args = {
            "user_data_dir": str(self.browser_data),
            "channel": "chrome",
            "headless": False,
            "locale": "zh-CN",
            "ignore_https_errors": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-features=TranslateUI",
                "--disable-popup-blocking",
                "--disable-prompt-on-repost",
                "--disable-background-timer-throttling",
                "--no-first-run",
                "--no-default-browser-check",
                "--password-store=basic",
                "--use-mock-keychain",
                "--disable-extensions",
                "--disable-default-apps",
                "--mute-audio",
                "--ignore-certificate-errors",
                "--ignore-ssl-errors",
            ],
        }

        browser_executable_path = os.environ.get("BROWSER_EXECUTABLE_PATH")
        if browser_executable_path:
            # 新版 patchright 在部分环境下可能不支持 executable_path，后续会自动降级到 channel=chrome
            launch_args.pop("channel", None)
            launch_args["executable_path"] = browser_executable_path

        return launch_args

    async def start(self):
        """启动浏览器"""
        launch_args = self._build_launch_args()

        try:
            self.playwright = await async_playwright().start()

            try:
                self.browser = await self.playwright.chromium.launch_persistent_context(**launch_args)
            except TypeError:
                # 兼容旧版 patchright: executable_path 不可用时退回 channel=chrome
                if "executable_path" not in launch_args:
                    raise
                fallback_args = self._build_launch_args()
                fallback_args.pop("executable_path", None)
                fallback_args["channel"] = "chrome"
                self.browser = await self.playwright.chromium.launch_persistent_context(**fallback_args)

        except Exception as e:
            wis_logger.warning(f"NodriverHelper 启动浏览器时发生错误: {str(e)}")
            await notify_user(70, [])
            await self.close()
            raise RuntimeError("70")

    @staticmethod
    def _is_transient_navigation_error(exc: Exception) -> bool:
        message = str(exc)
        transient_signals = (
            "Execution context was destroyed",
            "Cannot find context with specified id",
            "Frame was detached",
            "Target closed",
            "Navigation interrupted",
        )
        return any(signal in message for signal in transient_signals)

    async def _safe_evaluate(self, script: str, retries: int = 4, delay: float = 0.35):
        last_error: Optional[Exception] = None
        for attempt in range(retries):
            try:
                assert self.page is not None
                return await self.page.evaluate(script)
            except Exception as exc:
                last_error = exc
                if not self._is_transient_navigation_error(exc) or attempt == retries - 1:
                    raise
                await asyncio.sleep(delay)
        if last_error:
            raise last_error
        raise RuntimeError("unknown evaluate error")

    async def open_page(self, url: str = None):
        """
        打开登录页面

        Args:
            url: 登录页面的 URL
        """
        if not self.browser:
            await self.start()

        login_url = url or PLATFORM_LOGIN_URLS.get(self.platform)
        if not login_url:
            raise ValueError(f"未找到平台 {self.platform} 的登录URL")

        if self.page and not self.page.is_closed():
            await self.page.goto(login_url, wait_until="domcontentloaded")
            return

        assert self.browser is not None
        if self.browser.pages:
            self.page = self.browser.pages[0]
            if self.page.is_closed():
                self.page = await self.browser.new_page()
        else:
            self.page = await self.browser.new_page()

        await self.page.goto(login_url, wait_until="domcontentloaded")

    async def for_verification(self, url: str = None, timeout: int = 180) -> tuple[str, str]:
        """
        等待用户完成验证

        Args:
            timeout: 最大等待时间（秒）
        """
        if not self.page or self.page.is_closed():
            try:
                await asyncio.wait_for(self.open_page(url), timeout=timeout)
            except asyncio.TimeoutError:
                wis_logger.warning(f"打开验证页面 {url} 超时")
                await notify_user(14, [url])
                await notify_user(18, [self.platform])
                raise RuntimeError("18")

        verification_keywords = ["captcha", "verify", "security", "challenge", "recaptcha", "hcaptcha"]
        verification_selectors = [
            'iframe[src*="captcha"]',
            'iframe[src*="recaptcha"]',
            'iframe[src*="hcaptcha"]',
            'div[class*="captcha"]',
            'div[class*="verify"]',
            'form[action*="verify"]',
            'div[class*="recaptcha"]',
            'div[class*="hcaptcha"]',
            'div[class*="security"]',
            'div[class*="challenge"]',
        ]

        await ask_user(115, [self.platform], timeout=5)
        start_time = time.monotonic()

        while True:
            try:
                assert self.page is not None
                current_url = await self._safe_evaluate("window.location.href")
                wis_logger.debug(f"current_url: {current_url}")

                if any(keyword in str(current_url).lower() for keyword in verification_keywords):
                    wis_logger.debug(f"Detected verification keyword in URL: {current_url}")
                    await asyncio.sleep(1)
                    continue

                verification_detected = False
                for selector in verification_selectors:
                    try:
                        element = await self.page.query_selector(selector)
                        if element:
                            wis_logger.debug(f"Detected verification element: {selector}")
                            verification_detected = True
                            break
                    except Exception as selector_error:
                        wis_logger.debug(f"查询选择器 {selector} 失败: {str(selector_error)}")

                if not verification_detected:
                    verification_text_found = await self._safe_evaluate(
                        """
                        () => {
                            const verificationTexts = ['验证', '去验证'];
                            const elements = document.querySelectorAll('button, a, input[type="button"], input[type="submit"]');
                            for (const element of elements) {
                                const text = element.innerText || element.textContent || element.value || '';
                                if (verificationTexts.some((vText) => text.includes(vText))) {
                                    return true;
                                }
                            }
                            return false;
                        }
                        """
                    )
                    if verification_text_found:
                        wis_logger.debug("Detected verification text in page")
                        verification_detected = True

                if not verification_detected:
                    break

                if time.monotonic() - start_time > timeout:
                    raise TimeoutError(f"等待验证超时（{timeout}秒）")

                await asyncio.sleep(1)

            except Exception as e:
                if self._is_transient_navigation_error(e):
                    wis_logger.debug(f"页面跳转中，稍后重试验证检测: {e}")
                    await asyncio.sleep(0.5)
                    continue
                wis_logger.info(f"检测到验证操作错误: {str(e)}")
                await notify_user(18, [self.platform])
                raise RuntimeError("18")

        selected_cookies = await self._get_cookies()
        header_string = self._build_cookie_header(selected_cookies)
        user_agent = await self._safe_evaluate("navigator.userAgent")

        return header_string, user_agent

    async def _get_login_info(
        self,
        url: str = None,
        timeout: int = 60,
        force_login: bool = False,
        saved_cookies: str = "",
    ) -> tuple[str, str]:
        if not self.page or self.page.is_closed():
            try:
                await asyncio.wait_for(self.open_page(url), timeout=timeout)
            except asyncio.TimeoutError:
                wis_logger.info(f"打开登录页面 {url} 超时")
                await notify_user(14, [url])
                await notify_user(17, [self.platform])
                raise RuntimeError("17")

        if force_login:
            assert self.browser is not None
            await self.browser.clear_cookies()
            assert self.page is not None
            await self.page.reload(wait_until="domcontentloaded")
            login_status, _ = await self._check_login_status(saved_cookies=saved_cookies)
            if login_status:
                await ask_user(117, [self.platform], timeout=5)
                await asyncio.sleep(5)

        if self.platform != "xhs":
            await ask_user(113, [self.platform], timeout=5)
        else:
            await ask_user(116, [], timeout=5)

        start_time = time.monotonic()
        selected_cookies: dict[str, CookieRecord] = {}

        while True:
            if time.monotonic() - start_time > timeout:
                wis_logger.info(f"{self.platform} 登录操作超时")
                await notify_user(17, [self.platform])
                raise RuntimeError("17")

            try:
                if url:
                    login_status, selected_cookies = await self._check_url_login_status()
                else:
                    login_status, selected_cookies = await self._check_login_status(saved_cookies=saved_cookies)
            except Exception as e:
                if self._is_transient_navigation_error(e):
                    wis_logger.debug(f"页面跳转中，稍后重试登录状态检测: {e}")
                    await asyncio.sleep(0.5)
                    continue
                wis_logger.info(f"登录状态自动检测失败（非页面跳转瞬态错误）: {str(e)}")
                raise

            if login_status and selected_cookies:
                break

            await asyncio.sleep(1)

        header_string = self._build_cookie_header(selected_cookies)
        assert self.page is not None
        user_agent = await self._safe_evaluate("navigator.userAgent")

        return header_string, user_agent

    async def for_mc_login(
        self, url: str = None, timeout: int = 90, force_login: bool = False, saved_cookies: str = ""
    ) -> tuple[str, str]:
        """for media crawler"""
        if url:
            header_string, user_agent = await self.for_verification(url=url, timeout=timeout)
        else:
            header_string, user_agent = await self._get_login_info(
                url=None,
                timeout=timeout,
                force_login=force_login,
                saved_cookies=saved_cookies,
            )

        login_token_file = self.export_dir / "login_token.json"
        save_data = {"cookies": header_string, "user_agent": user_agent}
        with open(login_token_file, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=4)
        wis_logger.info(f"Cookies 已保存到: {login_token_file}")

        return header_string, user_agent

    async def for_mp_login(
        self, url: str = None, timeout: int = 60, force_login: bool = False, token: str = None
    ) -> tuple[str, str, str]:
        """for wx_crawler"""
        if url and token:
            header_string, user_agent = await self.for_verification(url=url, timeout=timeout)
        else:
            header_string, user_agent = await self._get_login_info(url=url, timeout=timeout, force_login=force_login)

        assert self.page is not None
        current_url = await self._safe_evaluate("window.location.href")

        if not token:
            token = self._extract_token_from_url(str(current_url))

        if not token:
            try:
                page_content = await self.page.content()
                token = self._extract_token_from_html(page_content)
                if token:
                    wis_logger.debug(f"从页面内容中提取到 token: {token}")
                else:
                    wis_logger.warning(f"after many method, still cannot extract token for: {current_url}")
            except Exception:
                wis_logger.warning(f"try to get page content for token extraction, but failed: {current_url}")

        if not token:
            raise ValueError("cannot get login token for wx_crawler")

        login_token_file = self.export_dir / "login_token.json"
        save_data = {
            "token": token,
            "cookies": header_string,
            "user_agent": user_agent,
            "login_time": datetime.now().isoformat(),
        }
        with open(login_token_file, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=4)
        wis_logger.info(f"Cookies 已保存到: {login_token_file}")

        return token, header_string, user_agent

    @staticmethod
    def _extract_token_from_url(current_url: str) -> Optional[str]:
        try:
            parsed = urlparse(current_url)
            query_params = parse_qs(parsed.query)
            return query_params.get("token", [None])[0]
        except Exception:
            wis_logger.warning(f"无法从 URL 中提取 token: {current_url}")
            return None

    @staticmethod
    def _extract_token_from_html(page_content: str) -> Optional[str]:
        token_match = re.search(r'token["\']?\s*[:=]\s*["\']([^"\']+)["\']', page_content)
        if token_match:
            return token_match.group(1)

        url_match = re.search(r'token=([^&"\'\s]+)', page_content)
        if url_match:
            return url_match.group(1)

        return None

    async def _check_url_login_status(self) -> Tuple[bool, dict[str, CookieRecord]]:
        """
        目前是通过网页元素进行检查，后期看看能不能直接用 local storage

        Returns:
            True: 已登录状态
            False: 未登录状态
        """
        texts = await self._collect_auth_texts()
        if self._has_login_prompt(texts):
            wis_logger.debug(f"login prompt found: {texts}")
            return False, {}

        wis_logger.debug("没有找到登录按钮, 判定登录成功")
        return True, await self._get_cookies()

    async def _collect_auth_texts(self) -> list[str]:
        assert self.page is not None
        texts = await self._safe_evaluate(
            """
            () => {
                const nodes = document.querySelectorAll(
                    'button, a, input[type="button"], input[type="submit"], [role="button"]'
                );
                const values = [];
                for (const node of nodes) {
                    const text = (node.innerText || node.textContent || node.value || '').trim();
                    if (text) {
                        values.push(text);
                    }
                }
                return Array.from(new Set(values)).slice(0, 300);
            }
            """
        )

        if isinstance(texts, list):
            return [str(t).strip() for t in texts if str(t).strip()]
        return []

    @staticmethod
    def _has_login_prompt(texts: list[str]) -> bool:
        normalized = [t.strip().lower() for t in texts if t and t.strip()]

        exact_hits = {
            "登录",
            "登录/注册",
            "一键登录",
            "验证码登录",
            "密码登录",
            "login",
            "login/register",
            "sign in",
            "log in",
        }

        if any(text in exact_hits for text in normalized):
            return True

        for text in normalized:
            if text in {"已登录", "登录中", "已登陆"}:
                continue
            if "登录" in text and len(text) <= 12:
                return True
            if "login" in text and len(text) <= 24:
                return True

        return False

    async def _check_login_status(self, saved_cookies: str = "") -> Tuple[bool, dict[str, CookieRecord]]:
        if self.platform == "mp":
            assert self.page is not None
            current_url = await self._safe_evaluate("window.location.href")
            if "token=" in str(current_url):
                return True, await self._get_cookies()
            return False, {}

        if self.platform == "wb":
            cookies = await self._get_cookies()
            sub_cookie = cookies.get("SUB")
            scf_cookie = cookies.get("SCF")
            sso_login_state = cookies.get("SSOLoginState")

            if (
                sub_cookie
                and sub_cookie.value
                and ((scf_cookie and scf_cookie.value) or (sso_login_state and sso_login_state.value))
            ):
                return True, cookies
            return False, {}

        if self.platform == "dy":
            cookies = await self._get_cookies()
            required_keys = {"sessionid", "sid_tt", "uid_tt"}
            stale_keys = {
                "sid_ucp_sso_v1",
                "ssid_ucp_sso_v1",
                "sso_uid_tt",
                "toutiao_sso_user",
                "toutiao_sso_user_ss",
            }

            has_required = required_keys.issubset(cookies.keys())
            has_stale = any(k in cookies for k in stale_keys)

            if has_required and not has_stale:
                return True, cookies
            return False, {}

        if self.platform == "xhs":
            _, cookies = await self._check_url_login_status()
            web_session = cookies.get("web_session")
            if web_session and web_session.value:
                # xhs 新签名/鉴权依赖多 cookie（例如 a1、webId、gid 等），
                # 不能仅保留 web_session。
                return True, cookies
            return False, {}

        if self.platform == "zhihu":
            cookies = await self._get_cookies()
            current_web_session = cookies.get("z_c0")
            if current_web_session and current_web_session.value:
                wis_logger.info(f"zhihu login success, z_c0: {current_web_session.value}")
                return True, cookies
            return False, {}

        if self.platform == "bili":
            cookies = await self._get_cookies()
            sessdata = cookies.get("SESSDATA")
            dede_user_id = cookies.get("DedeUserID")
            if (sessdata and sessdata.value) or (dede_user_id and dede_user_id.value):
                return True, cookies
            return False, {}

        if self.platform == "ks":
            cookies = await self._get_cookies()
            login_keys = {
                "kuaishou.server.webday7_st",
                "userId",
                "kuaishou.server.webday7_ph",
                "passToken",
            }
            if any(key in cookies for key in login_keys):
                return True, cookies
            return False, {}

        wis_logger.warning("未配置平台，使用通用 url 侦测规则")
        return await self._check_url_login_status()

    async def _get_cookies(self) -> dict[str, CookieRecord]:
        assert self.page is not None
        assert self.browser is not None

        current_url = await self._safe_evaluate("window.location.href")
        current_domain = await self._safe_evaluate("window.location.hostname")

        if str(current_url) == "chrome-error://chromewebdata/":
            wis_logger.info("主机脱网")
            await notify_user(14, [self.platform])
            raise RuntimeError("13")

        cookies = [CookieRecord.from_dict(item) for item in await self.browser.cookies()]

        selected_cookies: dict[str, CookieRecord] = {}
        normalized_current_domain = str(current_domain).lstrip(".").lower()

        for cookie in cookies:
            if self.platform == "wb":
                if not self._wb_domain_matches(cookie.domain, normalized_current_domain):
                    continue
            else:
                if not self._domain_matches(cookie.domain, normalized_current_domain):
                    continue
            existing = selected_cookies.get(cookie.name)
            if not existing or self._prefer_new_cookie(existing, cookie):
                selected_cookies[cookie.name] = cookie

        return selected_cookies

    @staticmethod
    def _domain_matches(cookie_domain: str, host: str) -> bool:
        if not cookie_domain:
            return False
        normalized = cookie_domain.lstrip(".").lower()
        if not normalized:
            return False
        if normalized == host:
            return True
        return host.endswith(f".{normalized}")

    @classmethod
    def _wb_domain_matches(cls, cookie_domain: str, host: str) -> bool:
        if cls._domain_matches(cookie_domain, host):
            return True

        normalized_cookie_domain = cookie_domain.lstrip(".").lower() if cookie_domain else ""
        if not normalized_cookie_domain:
            return False

        # wb 平台仅接受 weibo.cn 域 cookie
        if host.endswith("weibo.cn") and normalized_cookie_domain.endswith("weibo.cn"):
            return True

        return False

    @staticmethod
    def _prefer_new_cookie(existing_cookie: CookieRecord, new_cookie: CookieRecord) -> bool:
        existing_expires = existing_cookie.expires or 0
        new_expires = new_cookie.expires or 0

        if new_expires and new_expires > existing_expires:
            return True

        if not new_expires and not existing_expires:
            existing_domain = existing_cookie.domain or ""
            new_domain = new_cookie.domain or ""
            return len(new_domain) > len(existing_domain)

        return False

    def _build_cookie_header(self, selected_cookies: dict[str, CookieRecord]) -> str:
        if self.platform == "xhs":
            xhs_cookie_order = [
                "a1",
                "web_session",
                "webId",
                "gid",
                "webBuild",
                "xsecappid",
                "websectiga",
                "sec_poison_id",
            ]
            ordered_parts: list[str] = []
            used_keys: set[str] = set()
            for key in xhs_cookie_order:
                cookie = selected_cookies.get(key)
                if cookie and cookie.value:
                    ordered_parts.append(f"{cookie.name}={cookie.value}")
                    used_keys.add(key)

            for cookie_name, cookie in selected_cookies.items():
                if cookie_name in used_keys:
                    continue
                if cookie and cookie.value:
                    ordered_parts.append(f"{cookie.name}={cookie.value}")

            return "; ".join(ordered_parts)

        if self.platform == "wb":
            wb_cookie_order = [
                "_T_WM",
                "SCF",
                "SUB",
                "SUBP",
                "SSOLoginState",
                "ALF",
                "MLOGIN",
                "M_WEIBOCN_PARAMS",
            ]
            ordered_parts: list[str] = []
            used_keys: set[str] = set()
            for key in wb_cookie_order:
                cookie = selected_cookies.get(key)
                if cookie and cookie.value:
                    ordered_parts.append(f"{cookie.name}={cookie.value}")
                    used_keys.add(key)

            for cookie_name, cookie in selected_cookies.items():
                if cookie_name in used_keys:
                    continue
                if cookie and cookie.value:
                    ordered_parts.append(f"{cookie.name}={cookie.value}")

            return "; ".join(ordered_parts)

        return ";".join([f"{cookie.name}={cookie.value}" for cookie in selected_cookies.values()])

    async def close(self):
        """关闭浏览器"""
        try:
            if self.browser:
                await self.browser.close()
        except Exception as e:
            wis_logger.error(f"关闭浏览器时发生错误: {str(e)}")
        finally:
            self.browser = None
            self.page = None

            if self.playwright:
                try:
                    await self.playwright.stop()
                except Exception as e:
                    wis_logger.error(f"关闭 playwright 时发生错误: {str(e)}")
                finally:
                    self.playwright = None
