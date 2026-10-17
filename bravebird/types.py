from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal


@dataclass
class GitHubConfig:
    username: str
    password: str
    totp_secret: str
    otp_code: str | None = None
    login_url: str = "https://github.com/login"
    session_state_path: str = ".state/github-storage.json"


@dataclass
class PortalFormValues:
    search_term: str
    order_date: str
    region: str
    city: str
    notes: str = ""


@dataclass
class RunInput:
    github: GitHubConfig
    form: PortalFormValues
    output_dir: str = "runs/latest"


@dataclass
class StageTiming:
    stage: str
    started_at: str
    finished_at: str
    duration_ms: int
    retry_count: int
    status: Literal["ok", "failed"]


@dataclass
class PageVisit:
    stage: str
    url: str
    title: str
    timestamp: str


@dataclass
class CapturedFile:
    kind: Literal["download", "screenshot", "html", "log", "manifest"]
    path: str
    description: str


@dataclass
class ResolverAttempt:
    strategy: str
    detail: str
    success: bool


@dataclass
class ResolvedTarget:
    frame_path: list[int]
    strategy: str
    selector_kind: Literal["role", "label", "text", "css"]
    selector_value: str
    attempts: list[ResolverAttempt] = field(default_factory=list)


@dataclass
class FailureBundle:
    stage: str
    url: str
    screenshot_path: str
    html_path: str
    log_path: str
    console_log: list[str]
    resolver_attempts: list[ResolverAttempt]


@dataclass
class RunManifest:
    inputs: RunInput
    session: dict
    pages_visited: list[PageVisit]
    stage_timings: list[StageTiming]
    captured_files: list[CapturedFile]
    failure: FailureBundle | None = None

    def to_dict(self) -> dict:
        return asdict(self)
