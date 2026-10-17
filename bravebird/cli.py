from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from .runner import run_automation
from .types import GitHubConfig, PortalFormValues, RunInput


def load_input(path: str) -> RunInput:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    github_raw = raw["github"]
    github = GitHubConfig(
        username=github_raw["username"],
        password=github_raw["password"],
        totp_secret=github_raw.get("totp_secret", github_raw.get("totpSecret", "")),
        otp_code=github_raw.get("otp_code", github_raw.get("otpCode")),
        login_url=github_raw.get("login_url", github_raw.get("loginUrl", "https://github.com/login")),
        session_state_path=github_raw.get("session_state_path", github_raw.get("sessionStatePath", ".state/github-storage.json")),
    )
    form_raw = raw["form"]
    form = PortalFormValues(
        search_term=form_raw["searchTerm"],
        order_date=form_raw["orderDate"],
        region=form_raw["region"],
        city=form_raw["city"],
        notes=form_raw.get("notes", ""),
    )
    return RunInput(github=github, form=form, output_dir=raw.get("outputDir", "runs/latest"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="inputs/example.json")
    args = parser.parse_args()
    result = asyncio.run(run_automation(load_input(args.input), args.input))
    print(f"Manifest written to {result['manifest_path']}")
    print(f"Output directory: {result['output_dir']}")


if __name__ == "__main__":
    main()
