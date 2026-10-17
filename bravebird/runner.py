from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from time import perf_counter

from playwright.async_api import async_playwright, Page

from .github_auth import ensure_github_session
from .local_portal import start_demo_portal
from .manifest import ManifestRecorder
from .redact import redact_text
from .resolver import FieldSpec, resolve_field_from_html
from .retry import RetryOptions, with_retry
from .types import RunInput, StageTiming, ResolvedTarget
from .utils import ensure_dir, env_bool, now_iso, slugify


class RunnerResult(dict):
    manifest_path: str
    output_dir: str


DEFAULT_FIELDS = {
    "search_term": FieldSpec("search_term", "Search term", "textbox", ["search", "query"]),
    "order_date": FieldSpec("order_date", "Order date", "textbox", ["date"]),
    "region": FieldSpec("region", "Region", "combobox", ["state", "country"]),
    "city": FieldSpec("city", "City", "combobox", ["town"]),
    "notes": FieldSpec("notes", "Notes", "textarea", ["comment", "details"]),
}


def _build_locator(scope: Page, target: ResolvedTarget):
    if target.selector_kind == "role":
        role, name = target.selector_value.split(":", 1)
        return scope.get_by_role(role, name=name)
    if target.selector_kind == "label":
        return scope.get_by_label(target.selector_value, exact=False)
    return scope.locator(target.selector_value)


async def _capture_failure_bundle(recorder: ManifestRecorder, page: Page, console_log: list[str]) -> tuple[str, str, str]:
    evidence_dir = recorder.output_dir / "evidence"
    ensure_dir(evidence_dir)
    stamp = int(perf_counter() * 1000000)
    screenshot_path = str(evidence_dir / f"{stamp}-screenshot.png")
    html_path = str(evidence_dir / f"{stamp}-page.html")
    log_path = str(evidence_dir / f"{stamp}-console.log")
    await page.screenshot(path=screenshot_path, full_page=True)
    html = await page.content()
    Path(html_path).write_text(recorder.redact(html), encoding="utf-8")
    Path(log_path).write_text(recorder.redact("\n".join(console_log)), encoding="utf-8")
    return screenshot_path, html_path, log_path


async def run_automation(input_data: RunInput, raw_input_path: str) -> RunnerResult:
    timestamp = now_iso().replace(":", "-").replace(".", "-")
    output_dir = Path(input_data.output_dir or f"runs/{timestamp}-{slugify(Path(raw_input_path).stem)}")
    recorder = ManifestRecorder(str(output_dir), input_data)
    await recorder.init()

    state_path = Path(input_data.github.session_state_path)
    ensure_dir(state_path.parent)

    portal = await start_demo_portal()
    console_log: list[str] = []
    timings: list[StageTiming] = []
    session = {"reused": False, "staleDetected": False, "statePath": str(state_path)}
    current_stage = "startup"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=env_bool("HEADLESS", True))
        context = await browser.new_context(storage_state=str(state_path) if state_path.exists() else None, accept_downloads=True)
        page = await context.new_page()

        page.on("console", lambda message: console_log.append(f"[{message.type}] {message.text}"))
        page.on("pageerror", lambda error: console_log.append(f"[pageerror] {error}"))

        async def timed(stage: str, fn, retry_count: int = 0):
            started_at = now_iso()
            started = perf_counter()
            try:
                result = await fn()
                timings.append(StageTiming(stage, started_at, now_iso(), int((perf_counter() - started) * 1000), retry_count, "ok"))
                return result
            except Exception:
                timings.append(StageTiming(stage, started_at, now_iso(), int((perf_counter() - started) * 1000), retry_count, "failed"))
                raise

        try:
            current_stage = "github-session"
            async def _github():
                result = await ensure_github_session(context, input_data.github, str(state_path))
                session.update(result)
                await page.goto("https://github.com/settings/profile", wait_until="domcontentloaded")
                recorder.add_page_visit("github-profile", page.url, await page.title())
                await context.storage_state(path=str(state_path))
            try:
                await timed(current_stage, _github)
            except Exception as exc:
                session.update({"reused": False, "staleDetected": False, "statePath": str(state_path), "loginFailed": True, "loginError": str(exc)})
                recorder.add_page_visit("github-session", "about:blank", "GitHub login skipped after failure")

            current_stage = "portal-home"
            await timed(current_stage, lambda: page.goto(portal.base_url, wait_until="domcontentloaded"))
            recorder.add_page_visit("portal-home", page.url, await page.title())

            current_stage = "portal-workspace"
            await timed(current_stage, lambda: page.get_by_role("link", name="Open workspace").click())
            await page.wait_for_load_state("domcontentloaded")
            recorder.add_page_visit("portal-workspace", page.url, await page.title())

            current_stage = "portal-request"
            await timed(current_stage, lambda: page.get_by_role("link", name="New request").click())
            await page.wait_for_load_state("domcontentloaded")
            recorder.add_page_visit("portal-request", page.url, await page.title())

            form_frame = page.frames[1] if len(page.frames) > 1 else None
            if form_frame is None:
                raise RuntimeError("Unable to access embedded form")

            current_stage = "fill-form"

            async def fill_stage():
                async def _fill_once():
                    source_html = await form_frame.content()
                    for field_name, spec in DEFAULT_FIELDS.items():
                        value = getattr(input_data.form, field_name)
                        if field_name != "notes" and not value:
                            continue
                        target = resolve_field_from_html(source_html, spec)
                        if target is None:
                            raise RuntimeError(f"Unable to resolve field {spec.key}")
                        locator = _build_locator(form_frame, target)
                        if spec.kind in {"textbox", "textarea"}:
                            await locator.fill(value)
                        else:
                            await locator.select_option(value)

                    submit_spec = FieldSpec("submit", "Create receipt", "button", ["submit"])
                    submit_html = await form_frame.content()
                    submit_target = resolve_field_from_html(submit_html, submit_spec)
                    if submit_target is None:
                        raise RuntimeError("Unable to resolve submit button")
                    await _build_locator(form_frame, submit_target).click()
                    recorder.add_page_visit("portal-summary", form_frame.url, await page.title())

                await with_retry(_fill_once, RetryOptions(2, 750, 2500, 2.0))

            await timed(current_stage, fill_stage)

            current_stage = "download-document"

            async def download_stage():
                async def _download_once():
                    async with page.expect_download() as download_info:
                        await page.frame_locator("iframe").get_by_role("link", name="Download receipt").click()
                    download = await download_info.value
                    download_dir = output_dir / "downloads"
                    ensure_dir(download_dir)
                    destination = str(download_dir / download.suggested_filename)
                    await download.save_as(destination)
                    recorder.add_captured_file("download", destination, "Generated receipt from the embedded demo portal")
                    recorder.add_page_visit("portal-download", page.url, await page.title())

                await with_retry(_download_once, RetryOptions(2, 750, 2500, 2.0))

            await timed(current_stage, download_stage)

            for timing in timings:
                recorder.add_stage_timing(timing)
            manifest_path = await recorder.write_manifest({"session": session})
            await browser.close()
            portal.close()
            return RunnerResult(manifest_path=manifest_path, output_dir=str(output_dir))

        except Exception:
            screenshot_path, html_path, log_path = await _capture_failure_bundle(recorder, page, console_log)
            Path(output_dir / "evidence" / "failure.log").write_text(recorder.redact("\n".join(console_log)), encoding="utf-8")
            for timing in timings:
                recorder.add_stage_timing(timing)
            await recorder.write_manifest(
                {
                    "session": session,
                    "failure": {
                        "stage": current_stage,
                        "url": page.url,
                        "screenshot_path": screenshot_path,
                        "html_path": html_path,
                        "log_path": log_path,
                        "console_log": [recorder.redact(line) for line in console_log],
                        "resolver_attempts": [],
                    },
                }
            )
            await browser.close()
            portal.close()
            raise
