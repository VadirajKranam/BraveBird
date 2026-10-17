from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
import asyncio


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def sleep(ms: int) -> None:
    await asyncio.sleep(ms / 1000)


def ensure_dir(dir_path: str | Path) -> None:
    Path(dir_path).mkdir(parents=True, exist_ok=True)


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"^-+|-+$", "", value)
    return value[:80] or "run"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def parse_bool(value: str | None, fallback: bool = False) -> bool:
    if value is None:
        return fallback
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_bool(name: str, fallback: bool = False) -> bool:
    return parse_bool(os.getenv(name), fallback)
