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

PROMPT = f"""
Search the web and find 8 real remote web developer job postings that are recent (2024-2025).
Focus on: frontend developer, full-stack developer, React developer roles.
Look on: LinkedIn, Indeed, We Work Remotely, Remote.co, Wellfound, company career pages.

My profile:
{MY_PROFILE}

For each job return:
- company_name
- job_title
- salary_range (or "Not Listed")
- responsibilities (list, max 5 items)
- required_skills (list)
- nice_to_have_skills (list)
- missing_skills (skills from required list that I am missing based on my profile)
- match_score (0-100 integer, how well I match)
- job_url
- date_posted

Also return top_missing_skills: the 5 most important skills I should learn across all jobs.

IMPORTANT: Respond ONLY with a valid JSON object. No markdown, no explanation, no code fences.
Start your response with {{ and end with }}
Format:
{{
  "jobs": [
    {{
      "company_name": "...",
      "job_title": "...",
      "salary_range": "...",
      "responsibilities": ["..."],
      "required_skills": ["..."],
      "nice_to_have_skills": ["..."],
      "missing_skills": ["..."],
      "match_score": 75,
      "job_url": "...",
      "date_posted": "..."
    }}
  ],
  "top_missing_skills": ["skill1", "skill2", "skill3", "skill4", "skill5"]
}}
"""

# ── Gemini API ────────────────────────────────────────────────────────────────

def fetch_jobs():
    print("Asking Gemini to find web dev jobs...")
    payload = {
        "contents": [{"parts": [{"text": PROMPT}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4000},
        "tools": [{"google_search": {}}]
    }
    resp = requests.post(GEMINI_URL, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    # Collect all text parts (Gemini sometimes splits across multiple parts)
    parts = data["candidates"][0]["content"]["parts"]
    text = " ".join(p.get("text", "") for p in parts if "text" in p).strip()

    print("Gemini response preview:", text[:200])

    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)

    # Extract JSON — find first { and last }
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON found in Gemini response: {text[:500]}")

    json_str = text[start:end]
    return json.loads(json_str)


# ── Google Sheets Auth ────────────────────────────────────────────────────────

def get_sheets_token():
    import time
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    creds = json.loads(GOOGLE_CREDS_JSON)
    now   = int(time.time())

    header  = base64.urlsafe_b64encode(json.dumps({"alg":"RS256","typ":"JWT"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "iss":   creds["client_email"],
        "scope": "https://www.googleapis.com/auth/spreadsheets",
        "aud":   "https://oauth2.googleapis.com/token",
        "iat":   now,
        "exp":   now + 3600
    }).encode()).rstrip(b"=")

    msg = header + b"." + payload
    private_key = serialization.load_pem_private_key(
        creds["private_key"].encode(), password=None
    )
    signature = private_key.sign(msg, padding.PKCS1v15(), hashes.SHA256())
    sig_b64   = base64.urlsafe_b64encode(signature).rstrip(b"=")
    jwt       = (msg + b"." + sig_b64).decode()

    token_resp = requests.post("https://oauth2.googleapis.com/token", data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion":  jwt
    })
    token_resp.raise_for_status()
    return token_resp.json()["access_token"]


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