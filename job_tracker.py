#!/usr/bin/env python3
"""
Daily Remote Web Dev Job Tracker
- Uses Gemini API (free) to search & analyze jobs
- Saves results to Google Sheets automatically
- Run daily via GitHub Actions at 8 PM
"""

import json
import os
import re
import base64
from datetime import datetime
from collections import Counter

import requests

# ── Config ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY    = os.environ["GEMINI_API_KEY"]
SPREADSHEET_ID    = os.environ["SPREADSHEET_ID"]
GOOGLE_CREDS_JSON = base64.b64decode(os.environ["GOOGLE_CREDENTIALS"]).decode("utf-8")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
)

# ── YOUR PROFILE — edit this ──────────────────────────────────────────────────
MY_PROFILE = """
Skills I have: HTML, CSS, JavaScript, React, basic Node.js, Git, REST APIs, Tailwind CSS
Experience: 2 years frontend development
Familiar with: TypeScript (basic), basic SQL
NOT familiar with: Docker, Kubernetes, AWS, GraphQL, Next.js (intermediate+),
                   Python backend, microservices, CI/CD pipelines, Redis,
                   testing frameworks (Jest/Vitest)
Target: Remote frontend or full-stack roles, $80k+ salary
"""

# ── Step 1 prompt: search the web for jobs ────────────────────────────────────
SEARCH_PROMPT = """
Search the web right now and find 5 real remote web developer job postings from 2024-2025.
Focus on: frontend developer, full-stack developer, or React developer roles paying $80k+.
Sources to check: We Work Remotely, Remote.co, Wellfound, LinkedIn, company career pages.

For each job collect:
- Company name
- Job title
- Salary range (if listed)
- Key responsibilities (max 4)
- Required skills
- Nice to have skills
- Job URL
- Date posted

Return a plain text summary of the 5 jobs you found. Be detailed and accurate.
"""

# ── Step 2 prompt: convert to JSON ───────────────────────────────────────────
def make_json_prompt(job_text):
    return f"""
Convert the following job listings into a JSON object.

My developer profile:
{MY_PROFILE}

Job listings:
{job_text}

Return ONLY a valid JSON object with this exact structure.
No markdown, no code fences, no explanation — just the raw JSON:

{{
  "jobs": [
    {{
      "company_name": "...",
      "job_title": "...",
      "salary_range": "...",
      "responsibilities": ["...", "..."],
      "required_skills": ["...", "..."],
      "nice_to_have_skills": ["...", "..."],
      "missing_skills": ["skills I am missing based on my profile"],
      "match_score": 75,
      "job_url": "...",
      "date_posted": "..."
    }}
  ],
  "top_missing_skills": ["5 most important skills I should learn"]
}}
"""

# ── Gemini API call ───────────────────────────────────────────────────────────

def call_gemini(prompt, use_search=False):
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192},
    }
    if use_search:
        payload["tools"] = [{"google_search": {}}]

    resp = requests.post(GEMINI_URL, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts if "text" in p).strip()


def fetch_jobs():
    # Step 1: Search the web for jobs (with google_search tool)
    print("Step 1: Searching web for jobs...")
    job_text = call_gemini(SEARCH_PROMPT, use_search=True)
    print("Found job listings, length:", len(job_text))
    print("Preview:", job_text[:300])

    # Step 2: Convert to structured JSON (no search tool = no conflict)
    print("Step 2: Converting to structured JSON...")
    json_text = call_gemini(make_json_prompt(job_text), use_search=False)
    print("JSON response length:", len(json_text))
    print("JSON preview:", json_text[:200])

    # Strip any accidental markdown fences
    json_text = re.sub(r"```json\s*", "", json_text)
    json_text = re.sub(r"```\s*", "", json_text)
    json_text = json_text.strip()

    # Extract the JSON object
    start = json_text.find("{")
    end   = json_text.rfind("}") + 1
    if start == -1 or end <= 1:
        raise ValueError(f"No valid JSON found. Response:\n{json_text[:1000]}")

    return json.loads(json_text[start:end])


# ── Google Sheets Auth ────────────────────────────────────────────────────────

def get_sheets_token():
    import time
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    creds  = json.loads(GOOGLE_CREDS_JSON)
    now    = int(time.time())
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
    ).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "iss":   creds["client_email"],
        "scope": "https://www.googleapis.com/auth/spreadsheets",
        "aud":   "https://oauth2.googleapis.com/token",
        "iat":   now,
        "exp":   now + 3600
    }).encode()).rstrip(b"=")

    msg         = header + b"." + payload
    private_key = serialization.load_pem_private_key(
        creds["private_key"].encode(), password=None
    )
    signature = private_key.sign(msg, padding.PKCS1v15(), hashes.SHA256())
    sig_b64   = base64.urlsafe_b64encode(signature).rstrip(b"=")
    jwt       = (msg + b"." + sig_b64).decode()

    r = requests.post("https://oauth2.googleapis.com/token", data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion":  jwt
    })
    r.raise_for_status()
    return r.json()["access_token"]


def sheets_req(method, path, token, **kwargs):
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
    r = requests.request(
        method, base + path,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        **kwargs
    )
    r.raise_for_status()
    return r.json()


# ── Write to Google Sheets ────────────────────────────────────────────────────

def write_to_sheets(result):
    jobs        = result["jobs"]
    top_missing = result.get("top_missing_skills", [])
    today       = datetime.now().strftime("%Y-%m-%d")
    token       = get_sheets_token()

    meta         = sheets_req("GET", "", token)
    sheet_titles = [s["properties"]["title"] for s in meta["sheets"]]

    def ensure_sheet(title):
        if title not in sheet_titles:
            sheets_req("POST", ":batchUpdate", token, json={
                "requests": [{"addSheet": {"properties": {"title": title}}}]
            })
            sheet_titles.append(title)

    # Sheet 1: Today's jobs
    tab = f"Jobs {today}"
    ensure_sheet(tab)

    rows = [["Company", "Role", "Salary", "Match %", "Responsibilities",
             "Required Skills", "Nice to Have", "Skills I'm Missing",
             "Date Posted", "Job URL"]]
    for job in jobs:
        rows.append([
            job.get("company_name", ""),
            job.get("job_title", ""),
            job.get("salary_range", "Not Listed"),
            f"{job.get('match_score', 0)}%",
            "\n".join(f"- {r}" for r in job.get("responsibilities", [])),
            "\n".join(job.get("required_skills", [])),
            "\n".join(job.get("nice_to_have_skills", [])),
            "\n".join(f"MISSING: {s}" for s in job.get("missing_skills", [])) or "Good match!",
            job.get("date_posted", ""),
            job.get("job_url", ""),
        ])
    sheets_req("PUT", f"/values/{tab}!A1?valueInputOption=RAW", token, json={"values": rows})

    # Sheet 2: Skill gaps
    ensure_sheet("Skill Gaps")
    all_missing = []
    for job in jobs:
        all_missing.extend(job.get("missing_skills", []))
    freq = Counter(all_missing).most_common(20)

    resources = {
        "typescript":  "typescriptlang.org / Total TypeScript (free)",
        "next.js":     "nextjs.org/learn (official, free)",
        "graphql":     "graphql.org/learn (free)",
        "docker":      "docs.docker.com / TechWorld with Nana YouTube",
        "jest":        "jestjs.io/docs (free)",
        "vitest":      "vitest.dev (free)",
        "testing":     "vitest.dev / Testing Library docs",
        "aws":         "AWS Free Tier + freeCodeCamp AWS course",
        "ci/cd":       "GitHub Actions docs (free)",
        "redis":       "redis.io/docs (free)",
        "postgresql":  "pgexercises.com (free)",
        "node.js":     "The Odin Project (free)",
        "kubernetes":  "kubernetes.io/docs (free)",
        "python":      "CS50P Harvard (free)",
    }

    gap_rows = [["Skill", "Times Missing", "Priority", "Free Learning Resource", "Last Updated"]]
    for skill, count in freq:
        priority = "HIGH" if count >= 4 else ("MEDIUM" if count >= 2 else "Low")
        res = next((v for k, v in resources.items() if k in skill.lower()),
                   "freeCodeCamp / The Odin Project")
        gap_rows.append([skill, count, priority, res, today])
    sheets_req("PUT", "/values/Skill Gaps!A1?valueInputOption=RAW", token, json={"values": gap_rows})

    # Sheet 3: Daily summary log
    ensure_sheet("Daily Summary")
    check = sheets_req("GET", "/values/Daily Summary!A1", token)
    if not check.get("values"):
        sheets_req("PUT", "/values/Daily Summary!A1?valueInputOption=RAW", token,
                   json={"values": [["Date", "Jobs Found", "Top Missing Skills", "Avg Match %"]]})

    avg = round(sum(j.get("match_score", 0) for j in jobs) / max(len(jobs), 1))
    sheets_req("POST",
               "/values/Daily Summary!A:D:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
               token, json={"values": [[today, len(jobs), ", ".join(top_missing), f"{avg}%"]]})

    print(f"Done! {len(jobs)} jobs written to tab '{tab}'")
    print(f"Top skills to learn: {', '.join(top_missing)}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = fetch_jobs()
    write_to_sheets(result)