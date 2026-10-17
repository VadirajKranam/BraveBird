from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import re

from playwright.async_api import BrowserContext, Page

from .retry import RetryOptions, with_retry
from .totp import get_code
from .types import GitHubConfig
from .utils import ensure_dir


class SessionCheckResult(dict):
    reused: bool
    stale_detected: bool


async def _looks_logged_in(page: Page) -> bool:
    url = page.url
    if "/login" in url or "/sessions/" in url:
        return False
    try:
        if await page.get_by_text("Sign in to GitHub", exact=False).is_visible():
            return False
    except Exception:
        pass
    try:
        return await page.locator('a[href*="logout"], button:has-text("Sign out"), [aria-label*="Sign out"]').count() > 0
    except Exception:
        return False


async def _is_session_alive(page: Page) -> bool:
    await page.goto("https://github.com/settings/profile", wait_until="domcontentloaded")
    return await _looks_logged_in(page)


async def _maybe_fill_two_factor(page: Page, config: GitHubConfig) -> None:
    otp_selector = 'input[name="app_otp"], input[autocomplete="one-time-code"], input[name*="otp" i], input[name*="code" i], input#otp'
    otp_input = page.locator(otp_selector).first
    if await page.locator(otp_selector).count() == 0:
        visible_text_inputs = page.locator('input:visible:not([type="password"])')
        if await visible_text_inputs.count() == 0:
            return
        otp_input = visible_text_inputs.first
    submit_button = page.get_by_role("button", name=re.compile(r"verify|continue|submit", re.I))
    visible_submit = page.locator('button[type="submit"]:visible, input[type="submit"]:visible').first
    max_attempts = 1 if config.otp_code else 2
    for attempt in range(max_attempts):
        code = config.otp_code or await get_code(None, config.totp_secret)
        await otp_input.fill(code)
        try:
            await submit_button.click()
        except Exception:
            await visible_submit.click()
        await page.wait_for_load_state("domcontentloaded")
        if await _looks_logged_in(page):
            return
        if attempt == 0 and not config.otp_code:
            continue
    if config.otp_code:
        raise RuntimeError("Provided one-time OTP code was rejected")
    raise RuntimeError("2FA code was rejected twice")


async def _perform_login(page: Page, config: GitHubConfig) -> None:
    await page.goto(config.login_url, wait_until="domcontentloaded")
    username_locator = page.get_by_label("Username or email address")
    if await username_locator.count() == 0:
        username_locator = page.locator('input[name="login"], input#login_field, input[autocomplete="username"]').first
    if await username_locator.count() == 0:
        username_locator = page.locator('input[type="text"]:visible, input[type="email"]:visible').first
    await username_locator.fill(config.username)

    password_locator = page.get_by_label("Password")
    if await password_locator.count() == 0:
        password_locator = page.locator('input[name="password"], input[type="password"], input[autocomplete="current-password"]').first
    if await password_locator.count() == 0:
        password_locator = page.locator('input[type="password"]:visible').first
    await password_locator.fill(config.password)
    await page.get_by_role("button", name=re.compile(r"sign in|log in|submit", re.I)).click()
    await page.wait_for_load_state("domcontentloaded")
    await _maybe_fill_two_factor(page, config)
    await page.wait_for_load_state("networkidle")
    if not await _looks_logged_in(page):
        current_title = ""
        try:
            current_title = await page.title()
        except Exception:
            current_title = ""
        raise RuntimeError(f"GitHub login did not complete (url={page.url}, title={current_title})")


async def ensure_github_session(context: BrowserContext, config: GitHubConfig, storage_state_path: str) -> SessionCheckResult:
    page = await context.new_page()
    try:
        reused = Path(storage_state_path).exists() and await _is_session_alive(page)
        if reused:
            await page.close()
            return SessionCheckResult(reused=True, stale_detected=False)

        stale_detected = Path(storage_state_path).exists()
        await with_retry(
            lambda: _perform_login(page, config),
            RetryOptions(attempts=2, base_delay_ms=1500, max_delay_ms=5000, factor=2.0),
        )
        ensure_dir(Path(storage_state_path).parent)
        await context.storage_state(path=storage_state_path)
        return SessionCheckResult(reused=False, stale_detected=stale_detected)
    finally:
        await page.close()
