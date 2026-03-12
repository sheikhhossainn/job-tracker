#!/usr/bin/env python3
"""
Daily Remote Web Dev Job Tracker
- Step 1: Ask Gemini to search for jobs (plain text, no JSON)
- Step 2: Ask Gemini to convert that text to JSON (no search tool)
- Saves to Google Sheets via GitHub Actions daily at 8 PM
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

MY_PROFILE = """
Skills: HTML, CSS, JavaScript, React, basic Node.js, Git, REST APIs, Tailwind CSS
Experience: 2 years frontend development
Also know: TypeScript (basic), basic SQL
Missing: Docker, AWS, GraphQL, Next.js (intermediate+), CI/CD, Redis, Jest/Vitest
Target: Remote frontend or full-stack roles, $80k+ salary
"""

# ── Gemini call ───────────────────────────────────────────────────────────────

def call_gemini(prompt, use_search=False):
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
    }
    if use_search:
        payload["tools"] = [{"google_search": {}}]

    for attempt in range(1, 4):
        print(f"  Gemini call attempt {attempt}/3...")
        resp = requests.post(GEMINI_URL, json=payload, timeout=120)

        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
            time.sleep(5 * attempt)
            continue

        data      = resp.json()
        candidate = data.get("candidates", [{}])[0]
        reason    = candidate.get("finishReason", "")
        print(f"  Finish reason: {reason}")

        if "content" not in candidate:
            block = data.get("promptFeedback", {}).get("blockReason", "unknown")
            print(f"  No content returned. Block: {block}")
            time.sleep(3)
            continue

        parts = candidate["content"].get("parts", [])
        text  = "".join(p.get("text", "") for p in parts if "text" in p).strip()
        print(f"  Response length: {len(text)}")

        if text:
            return text, reason

        time.sleep(3)

    raise ValueError("Gemini failed after 3 attempts.")


# ── Step 1: Search for jobs (plain text output) ───────────────────────────────

SEARCH_PROMPT = f"""
Today is {datetime.now().strftime('%B %d, %Y')}.

Search the web for remote web developer jobs. Try these searches:
1. site:weworkremotely.com React developer
2. site:wellfound.com remote frontend engineer
3. remote React OR frontend developer job 2025

For each job you find, write a plain text summary with:
- Company name
- Job title  
- Salary (if shown)
- 2-3 key responsibilities
- Required skills list
- Job URL
- Approximate date posted

Find as many as you can (aim for 3-5). Write in plain text, no JSON.
If you find fewer than 3, that is fine — just report what you find accurately.
"""

# ── Step 2: Convert plain text jobs to JSON ───────────────────────────────────

def make_json_prompt(job_text):
    return f"""
Convert these job listings to JSON. Evaluate each against my profile.

MY PROFILE:
{MY_PROFILE}

JOB LISTINGS:
{job_text}

INSTRUCTIONS:
- missing_skills = skills in required_skills that I do NOT have per my profile
- match_score = 0-100 integer based on how many required skills I have
- Keep every string value under 100 characters
- responsibilities: max 3 items
- required_skills: max 6 items
- nice_to_have_skills: max 4 items
- missing_skills: only skills I genuinely lack

Output ONLY the raw JSON below. Start with {{ and end with }}.
No explanation, no markdown, no code fences.

{{
  "jobs": [
    {{
      "company_name": "...",
      "job_title": "...",
      "salary_range": "... or Not Listed",
      "responsibilities": ["...", "..."],
      "required_skills": ["...", "..."],
      "nice_to_have_skills": ["...", "..."],
      "missing_skills": ["..."],
      "match_score": 70,
      "job_url": "...",
      "date_posted": "..."
    }}
  ],
  "top_missing_skills": ["...", "...", "...", "...", "..."]
}}
"""

# ── Parse JSON robustly ───────────────────────────────────────────────────────

def parse_json(text):
    # Strip markdown fences
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*",     "", text)
    text = text.strip()

    # Find outermost { ... }
    start = text.find("{")
    end   = text.rfind("}") + 1

    if start == -1 or end <= 1:
        raise ValueError(f"No JSON object found in:\n{text[:600]}")

    json_str = text[start:end]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        print(f"  Attempting to recover complete job objects...")

        # Extract each complete job object individually
        job_pattern = re.compile(
            r'\{\s*"company_name"\s*:.*?"date_posted"\s*:\s*"[^"]*"\s*\}',
            re.DOTALL
        )
        matches = job_pattern.findall(json_str)
        jobs = []
        for m in matches:
            try:
                jobs.append(json.loads(m))
            except Exception:
                pass

        if not jobs:
            raise ValueError(f"Could not recover any jobs. Raw text:\n{text[:800]}")

        all_missing = []
        for job in jobs:
            all_missing.extend(job.get("missing_skills", []))
        top = [s for s, _ in Counter(all_missing).most_common(5)]

        print(f"  Recovered {len(jobs)} jobs from truncated response.")
        return {"jobs": jobs, "top_missing_skills": top}


# ── Main fetch ────────────────────────────────────────────────────────────────

def fetch_jobs():
    # Step 1: search (with google_search tool, plain text response)
    print("Step 1: Searching for jobs...")
    job_text, _ = call_gemini(SEARCH_PROMPT, use_search=True)
    print(f"  Job listings preview: {job_text[:300]}\n")

    # Step 2: convert to JSON (no search tool — avoids all conflicts)
    print("Step 2: Converting to JSON...")
    json_text, reason = call_gemini(make_json_prompt(job_text), use_search=False)
    print(f"  JSON preview: {json_text[:200]}\n")

    if reason == "MAX_TOKENS":
        print("  Warning: response truncated, attempting recovery...")

    result = parse_json(json_text)
    print(f"  Successfully parsed {len(result.get('jobs', []))} jobs.")
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
        priority = "HIGH" if count >= 3 else ("MEDIUM" if count >= 2 else "Low")
        res = next((v for k, v in RESOURCES.items() if k in skill.lower()),
                   "freeCodeCamp / The Odin Project")
        gap_rows.append([skill, count, priority, res, today])
    sheets_req("PUT", "/values/Skill Gaps!A1?valueInputOption=RAW",
               token, json={"values": gap_rows})

    # Sheet 3: Daily summary
    ensure_sheet("Daily Summary")
    check = sheets_req("GET", "/values/Daily Summary!A1", token)
    if not check.get("values"):
        sheets_req("PUT", "/values/Daily Summary!A1?valueInputOption=RAW", token,
                   json={"values": [["Date", "Jobs Found", "Top Missing Skills", "Avg Match %"]]})

    avg = round(sum(j.get("match_score", 0) for j in jobs) / max(len(jobs), 1))
    sheets_req("POST",
               "/values/Daily Summary!A:D:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
               token, json={"values": [[today, len(jobs), ", ".join(top_missing), f"{avg}%"]]})

    print(f"Done! Top skills to learn: {', '.join(top_missing)}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = fetch_jobs()
    write_to_sheets(result)