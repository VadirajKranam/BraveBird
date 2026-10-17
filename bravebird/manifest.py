from __future__ import annotations

import json
from pathlib import Path

from .redact import redact_json_string, redact_text
from .types import CapturedFile, FailureBundle, PageVisit, RunInput, RunManifest, StageTiming
from .utils import ensure_dir, now_iso


class ManifestRecorder:
    def __init__(self, output_dir: str, inputs: RunInput) -> None:
        self.output_dir = Path(output_dir)
        self.inputs = inputs
        self.pages_visited: list[PageVisit] = []
        self.stage_timings: list[StageTiming] = []
        self.captured_files: list[CapturedFile] = []

    async def init(self) -> None:
        ensure_dir(self.output_dir)
        ensure_dir(self.output_dir / "evidence")
        ensure_dir(self.output_dir / "downloads")

    def add_page_visit(self, stage: str, url: str, title: str) -> None:
        self.pages_visited.append(PageVisit(stage=stage, url=url, title=title, timestamp=now_iso()))

    def add_captured_file(self, kind: str, file_path: str, description: str) -> None:
        self.captured_files.append(CapturedFile(kind=kind, path=file_path, description=description))

    def add_stage_timing(self, timing: StageTiming) -> None:
        self.stage_timings.append(timing)

    def redact(self, output: str) -> str:
        return redact_text(
            output,
            [
                self.inputs.github.username,
                self.inputs.github.password,
                self.inputs.github.totp_secret,
                self.inputs.form.search_term,
                self.inputs.form.order_date,
                self.inputs.form.region,
                self.inputs.form.city,
                self.inputs.form.notes,
            ],
        )

    async def write_manifest(self, extra: dict | None = None) -> str:
        manifest = RunManifest(
            inputs=self.inputs,
            session=(extra or {}).get("session", {"reused": False, "staleDetected": False, "statePath": ""}),
            pages_visited=self.pages_visited,
            stage_timings=self.stage_timings,
            captured_files=self.captured_files,
            failure=(extra or {}).get("failure"),
        )
        path = self.output_dir / "manifest.json"
        path.write_text(
            redact_json_string(
                manifest.to_dict(),
                [
                    self.inputs.github.username,
                    self.inputs.github.password,
                    self.inputs.github.totp_secret,
                    self.inputs.form.search_term,
                    self.inputs.form.order_date,
                    self.inputs.form.region,
                    self.inputs.form.city,
                    self.inputs.form.notes,
                ],
            ),
            encoding="utf-8",
        )
        return str(path)

    async def write_text_file(self, name: str, contents: str) -> str:
        path = self.output_dir / name
        path.write_text(contents, encoding="utf-8")
        return str(path)
