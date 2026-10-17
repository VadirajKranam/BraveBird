from __future__ import annotations

import argparse
import json
from pathlib import Path

from .resolver import FieldSpec, resolve_field_from_html


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", default="fixtures/offline/request-form.html")
    parser.add_argument("--spec", default="fixtures/offline/spec.json")
    args = parser.parse_args()
    html = Path(args.html).read_text(encoding="utf-8")
    spec_data = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    results = []
    for item in spec_data["fields"]:
        field = FieldSpec(item["key"], item["label"], item["kind"], item.get("aliases", []))
        resolved = resolve_field_from_html(html, field)
        results.append({"field": field.key, "resolved": resolved.__dict__ if resolved else None})
    print(json.dumps(results, indent=2, default=lambda o: o.__dict__))


if __name__ == "__main__":
    main()
