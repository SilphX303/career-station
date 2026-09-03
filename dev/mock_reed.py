"""Fake Reed API for local testing. Run: python dev/mock_reed.py (port 8765)
Then: CAREER_REED_KEY=x CAREER_REED_BASE=http://127.0.0.1:8765 uvicorn ..."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

JOBS = [
    {"jobId": 1001, "jobTitle": "Modern Workplace Engineer", "employerName": "Nimbus Digital", "locationName": "Brighton",
     "minimumSalary": 70000, "maximumSalary": 80000, "jobUrl": "https://www.reed.co.uk/jobs/1001", "date": "02/09/2026",
     "jobDescription": "Intune, Entra ID, Autopilot, M365. Hybrid, 2 days in Brighton office."},
    {"jobId": 1002, "jobTitle": "Senior TechOps Engineer", "employerName": "Kraken Technologies", "locationName": "London",
     "minimumSalary": 75000, "maximumSalary": 95000, "jobUrl": "https://www.reed.co.uk/jobs/1002", "date": "01/09/2026",
     "jobDescription": "Remote first. Okta, Google Workspace, Terraform, fleet management at scale."},
    {"jobId": 1003, "jobTitle": "IT Service Manager", "employerName": "Northwind Defence", "locationName": "Farnborough",
     "minimumSalary": 60000, "maximumSalary": 68000, "jobUrl": "https://www.reed.co.uk/jobs/1003", "date": "31/08/2026",
     "jobDescription": "ITIL service management. On site 4 days."},
    {"jobId": 1004, "jobTitle": "IAM Engineer", "employerName": "Bluefin Payments", "locationName": "Remote",
     "minimumSalary": None, "maximumSalary": None, "jobUrl": "https://www.reed.co.uk/jobs/1004", "date": "03/09/2026",
     "jobDescription": "Entra, SailPoint, SCIM. Fully remote UK."},
    {"jobId": 1005, "jobTitle": "1st Line Service Desk Analyst", "employerName": "Acme Ltd", "locationName": "Eastbourne",
     "minimumSalary": 24000, "maximumSalary": 26000, "jobUrl": "https://www.reed.co.uk/jobs/1005", "date": "03/09/2026",
     "jobDescription": "Password resets and ticket triage."},
]


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        kw = parse_qs(u.query).get("keywords", [""])[0].lower()
        hits = [j for j in JOBS if any(w in j["jobTitle"].lower() for w in kw.split())]
        body = json.dumps({"results": hits, "totalResults": len(hits)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8765), H).serve_forever()
