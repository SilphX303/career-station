"""Fake Greenhouse and Lever feeds on port 8767 for watchlist testing."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
GH = {"jobs": [
  {"id": 1, "title": "Senior Corporate IT Engineer", "absolute_url": "https://boards.greenhouse.io/monzo/jobs/1", "location": {"name": "London, Remote"}, "updated_at": "2026-09-01", "content": "<p>Own Okta, Google Workspace and our Mac fleet. Responsibilities: you will run identity and endpoints. Remote UK with a London office. Salary &pound;80,000 to &pound;95,000.</p>" * 3},
  {"id": 2, "title": "Account Executive", "absolute_url": "https://boards.greenhouse.io/monzo/jobs/2", "location": {"name": "London"}, "content": "Sales."},
]}
LV = [{"id": "abc", "text": "IT Manager", "hostedUrl": "https://jobs.lever.co/octoenergy/abc", "categories": {"location": "London", "commitment": "Full-time"}, "descriptionPlain": "Lead IT for 2,000 people. Responsibilities include identity, endpoints and vendor management. Hybrid two days. " * 8}]
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/").endswith("/v1/boards/monzo"):
            body = json.dumps({"name": "Monzo Bank"}).encode()
        elif self.path.rstrip("/").endswith("/v1/boards/stealth"):
            body = json.dumps({"name": "Stealth Startup Jobs"}).encode()
        elif "/v1/boards/" in self.path:
            body = json.dumps(GH if "monzo" in self.path or "stealth" in self.path else {"jobs": []}).encode()
        else:
            body = json.dumps(LV).encode()
        self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,*a): pass
if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8767), H).serve_forever()
