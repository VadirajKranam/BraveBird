from __future__ import annotations

import json
import re


DEFAULT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), "[redacted-email]"),
    (re.compile(r"\b\d{6}\b"), "[redacted-code]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"), "[redacted-token]"),
    (re.compile(r'"password"\s*:\s*".*?"', re.I), '"password":"[redacted]"'),
    (re.compile(r'"totpSecret"\s*:\s*".*?"', re.I), '"totpSecret":"[redacted]"'),
]


def redact_text(input_text: str, extra_values: list[str] | None = None) -> str:
    output = input_text
    for value in (extra_values or []):
        if value:
            output = output.replace(value, "[redacted]")
    for pattern, replacement in DEFAULT_PATTERNS:
        output = pattern.sub(replacement, output)
    return output


def redact_json_string(value: object, extra_values: list[str] | None = None) -> str:
    return redact_text(json.dumps(value, indent=2), extra_values)
