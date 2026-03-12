#!/usr/bin/env python3
"""
Daily Remote Web Dev Job Tracker
- Uses Gemini 2.5 Flash with Google Search grounding
- Saves results to Google Sheets automatically
- Run daily via GitHub Actions at 8 PM
"""

import json
import os
import re
import base64
import time
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

RESOURCES = {
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

# ── Prompt ────────────────────────────────────────────────────────────────────

def build_prompt():
    today = datetime.now().strftime("%B %d, %Y")
    return f"""
Today is {today}. Use Google Search to find 5 current remote web developer job postings.

Search these sites: wellfound.com, weworkremotely.com, remote.co, linkedin.com/jobs, and company career pages.
Look for: React developer, frontend developer, or full-stack JavaScript developer roles posted in the last 30 days.

My profile:
{MY_PROFILE}

Based on what you find, create a JSON object describing these jobs and how they match my profile.
Analyze each job's required skills against my profile to identify missing_skills and calculate match_score.

Return ONLY this JSON structure with no other text:
{{
  "jobs": [
    {{
      "company_name": "actual company name",
      "job_title": "actual job title",
      "salary_range": "salary if listed or Not Listed",
      "responsibilities": ["responsibility 1", "responsibility 2", "responsibility 3"],
      "required_skills": ["skill1", "skill2", "skill3"],
      "nice_to_have_skills": ["skill1", "skill2"],
      "missing_skills": ["skills from required_skills that I do NOT have based on my profile"],
      "match_score": 70,
      "job_url": "actual url",
      "date_posted": "date"
    }}
  ],
  "top_missing_skills": ["5 most common missing skills across all jobs"]
}}
"""

# ── Gemini API ────────────────────────────────────────────────────────────────

def call_gemini_with_retry(prompt, use_search=False, retries=3):
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 8192,
        },
    }
    if use_search:
        payload["tools"] = [{"google_search": {}}]

    for attempt in range(1, retries + 1):
        print(f"Calling Gemini (attempt {attempt}/{retries})...")
        resp = requests.post(GEMINI_URL, json=payload, timeout=120)

        if resp.status_code != 200:
            print(f"HTTP {resp.status_code}: {resp.text[:300]}")
            if attempt < retries:
                time.sleep(5 * attempt)
                continue
            resp.raise_for_status()

        data = resp.json()
        candidates = data.get("candidates", [])

        if not candidates:
            block = data.get("promptFeedback", {}).get("blockReason", "unknown")
            raise ValueError(f"No candidates returned. Block reason: {block}. Response: {json.dumps(data)[:400]}")

        candidate = candidates[0]
        finish_reason = candidate.get("finishReason", "")
        print(f"Finish reason: {finish_reason}")

        # RECITATION means Gemini refused to reproduce content — retry without search
        if finish_reason == "RECITATION":
            print("Recitation block — retrying without search tool...")
            if use_search:
                payload.pop("tools", None)
                use_search = False
            if attempt < retries:
                time.sleep(3)
                continue
            raise ValueError("Gemini kept hitting RECITATION block. Try again later.")

        if "content" not in candidate:
            print(f"No content in candidate: {json.dumps(candidate)[:300]}")
            if attempt < retries:
                time.sleep(3)
                continue
            raise ValueError(f"Gemini returned no content after {retries} attempts.")

        parts = candidate["content"].get("parts", [])
        text  = "".join(p.get("text", "") for p in parts if "text" in p).strip()

        if not text:
            print("Empty text response, retrying...")
            if attempt < retries:
                time.sleep(3)
                continue
            raise ValueError("Gemini returned empty text.")

        return text

    raise ValueError("All retry attempts failed.")


def fetch_jobs():
    print("Fetching jobs from Gemini with Google Search...")
    text = call_gemini_with_retry(build_prompt(), use_search=True)

    print(f"Response length: {len(text)}")
    print(f"Preview: {text[:300]}")

    # Strip markdown fences
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    # Extract outermost JSON object
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start == -1 or end <= 1:
        raise ValueError(f"No JSON object found in response:\n{text[:800]}")

    result = json.loads(text[start:end])
    print(f"Parsed {len(result.get('jobs', []))} jobs successfully.")
    return result


# ── Google Sheets Auth ────────────────────────────────────────────────────────

def get_sheets_token():
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    creds   = json.loads(GOOGLE_CREDS_JSON)
    now     = int(time.time())
    header  = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
    ).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "iss":   creds["client_email"],
        "scope": "https://www.googleapis.com/auth/spreadsheets",
        "aud":   "https://oauth2.googleapis.com/token",
        "iat":   now,
        "exp":   now + 3600,
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
        "assertion":  jwt,
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
    jobs        = result.get("jobs", [])
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
        missing = job.get("missing_skills", [])
        rows.append([
            job.get("company_name", ""),
            job.get("job_title", ""),
            job.get("salary_range", "Not Listed"),
            f"{job.get('match_score', 0)}%",
            "\n".join(f"- {r}" for r in job.get("responsibilities", [])),
            "\n".join(job.get("required_skills", [])),
            "\n".join(job.get("nice_to_have_skills", [])),
            "\n".join(f"MISSING: {s}" for s in missing) if missing else "Good match!",
            job.get("date_posted", ""),
            job.get("job_url", ""),
        ])
    sheets_req("PUT", f"/values/{tab}!A1?valueInputOption=RAW", token, json={"values": rows})
    print(f"Written {len(jobs)} jobs to tab '{tab}'")

    # Sheet 2: Skill gaps
    ensure_sheet("Skill Gaps")
    all_missing = []
    for job in jobs:
        all_missing.extend(job.get("missing_skills", []))
    freq = Counter(all_missing).most_common(20)

    gap_rows = [["Skill", "Times Missing", "Priority", "Free Learning Resource", "Last Updated"]]
    for skill, count in freq:
        priority = "HIGH" if count >= 4 else ("MEDIUM" if count >= 2 else "Low")
        res = next((v for k, v in RESOURCES.items() if k in skill.lower()),
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
    sheets_req(
        "POST",
        "/values/Daily Summary!A:D:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
        token,
        json={"values": [[today, len(jobs), ", ".join(top_missing), f"{avg}%"]]}
    )

    print(f"Done! Top skills to learn: {', '.join(top_missing)}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = fetch_jobs()
    write_to_sheets(result)