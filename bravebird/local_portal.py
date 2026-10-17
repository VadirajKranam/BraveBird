from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from uuid import uuid4
from urllib.parse import parse_qs, urlparse
from pathlib import Path

from .utils import ensure_dir


REGION_CITIES: dict[str, list[str]] = {
    "north": ["Seattle", "Portland", "Denver"],
    "south": ["Austin", "Miami", "Atlanta"],
    "west": ["San Francisco", "Los Angeles", "Phoenix"],
}


@dataclass
class DemoPortalHandle:
    base_url: str
    close: callable


def _html_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif; }}
    body {{ margin: 0; background: linear-gradient(180deg, #f6f7fb 0%, #ffffff 100%); color: #132238; }}
    header {{ padding: 24px 32px; background: #0f172a; color: white; }}
    main {{ padding: 28px 32px 48px; max-width: 1080px; }}
    a, button {{ color: #1d4ed8; }}
    .card {{ background: white; border: 1px solid #dbe4f0; border-radius: 18px; box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06); padding: 20px; margin: 18px 0; }}
    .muted {{ color: #5b6b7f; }}
    .pill {{ display: inline-block; padding: 4px 10px; border-radius: 999px; background: #eff6ff; color: #1d4ed8; font-size: 12px; font-weight: 600; }}
    iframe {{ width: 100%; min-height: 560px; border: 0; border-radius: 14px; background: white; }}
    table {{ width: 100%; border-collapse: collapse; }}
    td, th {{ padding: 10px 12px; border-bottom: 1px solid #e5edf7; text-align: left; }}
    input, select, textarea, button {{ font: inherit; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .span-2 {{ grid-column: 1 / -1; }}
    label {{ display: block; font-weight: 600; margin-bottom: 6px; }}
    input, select, textarea {{ width: 100%; box-sizing: border-box; border-radius: 12px; border: 1px solid #cbd5e1; padding: 12px 14px; background: white; }}
    textarea {{ min-height: 100px; resize: vertical; }}
    .actions {{ display: flex; gap: 12px; align-items: center; }}
    .button {{ display: inline-flex; align-items: center; justify-content: center; padding: 12px 18px; border: 0; border-radius: 12px; background: #2563eb; color: white; cursor: pointer; text-decoration: none; }}
    .button.secondary {{ background: #e2e8f0; color: #0f172a; }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _escape_attr(text: str) -> str:
    return text.replace("&", "&amp;").replace('"', "&quot;")


def _form_frame_html() -> str:
    options = "".join(f'<option value="{region}">{region.capitalize()}</option>' for region in REGION_CITIES)
    city_options = "".join(
        f'<option data-region="{region}" value="{city}">{city}</option>'
        for region, cities in REGION_CITIES.items()
        for city in cities
    )
    return f"""<!doctype html>
<html lang=\"en\">
<head><meta charset=\"utf-8\" /></head>
<body style=\"margin:0;font-family:Inter,system-ui,sans-serif;background:#f8fafc;color:#0f172a;\">
  <div style=\"padding:18px 20px;\">
    <div style=\"padding:12px 14px;border:1px solid #cbd5e1;border-radius:12px;background:#eff6ff;color:#1e3a8a;\">This form lives inside an iframe and the city list depends on the selected region.</div>
    <form method=\"post\" action=\"/workspace/summary\">
      <div class=\"form-grid\">
        <div><label for=\"searchTerm\">Search term</label><input id=\"searchTerm\" name=\"searchTerm\" type=\"text\" placeholder=\"Find a receipt or order\" /></div>
        <div><label for=\"orderDate\">Order date</label><input id=\"orderDate\" name=\"orderDate\" type=\"date\" /></div>
        <div><label for=\"region\">Region</label><select id=\"region\" name=\"region\"><option value=\"\">Choose one</option>{options}</select></div>
        <div><label for=\"city\">City</label><select id=\"city\" name=\"city\"><option value=\"\">Choose a region first</option>{city_options}</select></div>
        <div class=\"span-2\"><label for=\"notes\">Notes</label><textarea id=\"notes\" name=\"notes\" placeholder=\"Extra detail for the receipt\"></textarea></div>
        <div class=\"span-2 actions\"><button class=\"button\" type=\"submit\">Create receipt</button></div>
      </div>
    </form>
    <script>
      const citiesByRegion = {REGION_CITIES!r};
      const region = document.getElementById('region');
      const city = document.getElementById('city');
      function refreshCities() {{
        const items = citiesByRegion[region.value] ?? [];
        city.innerHTML = items.length ? items.map((item) => '<option value="' + item + '">' + item + '</option>').join('') : '<option value="">Choose a region first</option>';
      }}
      region.addEventListener('change', refreshCities);
    </script>
  </div>
</body>
</html>"""


def _summary_page(state: dict, base_url: str) -> str:
    return _html_shell(
        "Receipt ready",
        f"""
        <header><h1>Receipt ready</h1><p class=\"muted\">A document has been generated from your submission.</p></header>
        <main>
          <div class=\"card\">
            <span class=\"pill\">Submitted</span>
            <h2>Request {state['id']}</h2>
            <table><tbody>
              <tr><th>Search term</th><td>{_escape_html(state['searchTerm'])}</td></tr>
              <tr><th>Order date</th><td>{_escape_html(state['orderDate'])}</td></tr>
              <tr><th>Region</th><td>{_escape_html(state['region'])}</td></tr>
              <tr><th>City</th><td>{_escape_html(state['city'])}</td></tr>
              <tr><th>Notes</th><td>{_escape_html(state.get('notes', ''))}</td></tr>
            </tbody></table>
            <p class=\"actions\"><a class=\"button\" download href=\"{base_url}/document/{state['id']}\">Download receipt</a><a class=\"button secondary\" href=\"/workspace/new\">Create another</a></p>
          </div>
        </main>
        """,
    )


def _receipt_text(state: dict) -> str:
    return "\n".join(
        [
            "BraveBird Receipt",
            f"Request: {state['id']}",
            f"Created: {state['createdAt']}",
            f"Search term: {state['searchTerm']}",
            f"Order date: {state['orderDate']}",
            f"Region: {state['region']}",
            f"City: {state['city']}",
            f"Notes: {state.get('notes', '')}",
            "",
            "This file was produced by the embedded demo portal.",
        ]
    )


class _Handler(BaseHTTPRequestHandler):
    submissions: dict[str, dict] = {}

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(_html_shell("BraveBird Portal", '<header><h1>BraveBird Portal</h1><p class="muted">A deterministic demo portal for the automation runner.</p></header><main><div class="card"><span class="pill">Step 1</span><h2>Workspace</h2><p class="muted">Navigate through the dashboard and start a request.</p><a class="button" href="/workspace">Open workspace</a></div></main>'))
            return
        if parsed.path == "/workspace":
            self._send_html(_html_shell("Workspace", '<header><h1>Workspace</h1><p class="muted">One page deeper, then into the form frame.</p></header><main><div class="card"><span class="pill">Step 2</span><h2>Requests</h2><p class="muted">Create a new request to open the nested form.</p><a class="button" href="/workspace/new">New request</a></div></main>'))
            return
        if parsed.path == "/workspace/new":
            self._send_html(_html_shell("New request", f'<header><h1>New request</h1><p class="muted">Three pages deep from the home page, with the form embedded in an iframe.</p></header><main><div class="card"><span class="pill">Step 3</span><h2>Request form</h2><p class="muted">The form below is isolated in a nested browsing context.</p><iframe title="request form" srcdoc="{_escape_attr(_form_frame_html())}"></iframe></div></main>'))
            return
        if parsed.path.startswith("/document/"):
            doc_id = parsed.path.rsplit("/", 1)[-1]
            record = self.submissions.get(doc_id)
            if not record:
                self.send_response(404)
                self.send_header("content-type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Unknown receipt id")
                return
            data = _receipt_text(record).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/plain; charset=utf-8")
            self.send_header("content-disposition", f'attachment; filename="receipt-{record["id"]}.txt"')
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(404)
        self.send_header("content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/workspace/summary":
            length = int(self.headers.get("content-length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            params = parse_qs(body)
            state = {
                "id": uuid4().hex,
                "createdAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "searchTerm": params.get("searchTerm", [""])[0],
                "orderDate": params.get("orderDate", [""])[0],
                "region": params.get("region", [""])[0],
                "city": params.get("city", [""])[0],
                "notes": params.get("notes", [""])[0],
            }
            self.submissions[state["id"]] = state
            base_url = f"http://{self.headers.get('host')}"
            self._send_html(_summary_page(state, base_url))
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A003
        return

    def _send_html(self, html: str):
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


async def start_demo_portal() -> DemoPortalHandle:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def close() -> None:
        server.shutdown()
        server.server_close()

    return DemoPortalHandle(base_url=f"http://127.0.0.1:{server.server_port}", close=close)
