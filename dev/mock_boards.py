"""Fake Adzuna and RSS endpoints for local testing on port 8766."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

ADZ = [
 {"id": "a1", "title": "Modern Workplace Engineer", "company": {"display_name": "Nimbus Digital"}, "location": {"display_name": "Brighton, East Sussex"},
  "salary_min": 70000, "salary_max": 80000, "redirect_url": "https://adzuna.example/a1", "created": "2026-09-02T10:00:00Z", "description": "Intune Entra Autopilot. Hybrid."},
 {"id": "a2", "title": "Head of IT", "company": {"display_name": "Octopus Energy"}, "location": {"display_name": "London"},
  "salary_min": 90000, "salary_max": 110000, "redirect_url": "https://adzuna.example/a2", "created": "2026-09-03T08:00:00Z", "description": "Own IT for 2,000 people. Okta, Google Workspace, hybrid 2 days."},
]
RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>CWJobs search</title>
<item><title>Infrastructure Engineer - Monzo - Remote</title><link>https://cwjobs.example/1</link><guid>cw1</guid>
<description>&lt;p&gt;Remote UK. Salary &pound;80,000 - &pound;90,000. Terraform, AWS, Okta.&lt;/p&gt;</description><pubDate>Wed, 02 Sep 2026 09:00:00 GMT</pubDate></item>
<item><title>IT Manager</title><link>https://cwjobs.example/2</link><guid>cw2</guid>
<description>Location: Crawley. Circa &pound;65k. Lead a team of 4.</description><pubDate>Tue, 01 Sep 2026 09:00:00 GMT</pubDate></item>
</channel></rss>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path.startswith("/adzuna"):
            kw = parse_qs(u.query).get("what", [""])[0].lower()
            hits = [j for j in ADZ if any(w in j["title"].lower() for w in kw.split())]
            body, ct = json.dumps({"results": hits}).encode(), "application/json"
        else:
            body, ct = RSS.encode(), "application/rss+xml"
        self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass

if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8766), H).serve_forever()
