#!/usr/bin/env python3
"""
Daily Remote Web Dev Job Tracker
- Step 1: Gemini searches for jobs (plain text)
- Step 2: Gemini converts to JSON (no search tool)
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

# Support multiple Gemini API keys — falls back to next key on 429
GEMINI_API_KEYS = [k.strip() for k in [
    os.environ.get("GEMINI_API_KEY", ""),
    os.environ.get("GEMINI_API_KEY_2", ""),
] if k.strip()]

if not GEMINI_API_KEYS:
    raise ValueError("No Gemini API keys found!")

print(f"Loaded {len(GEMINI_API_KEYS)} Gemini API key(s)")
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]

# Load Google credentials — auto-detects base64 or raw JSON
_raw = os.environ["GOOGLE_CREDENTIALS"].strip()
print(f"Credentials raw length: {len(_raw)}")
print(f"Credentials starts with: {repr(_raw[:30])}")

if _raw.startswith("{"):
    GOOGLE_CREDS_JSON = _raw
else:
    _padded = _raw + "=" * (4 - len(_raw) % 4) if len(_raw) % 4 else _raw
    GOOGLE_CREDS_JSON = base64.b64decode(_padded).decode("utf-8")

_creds_check = json.loads(GOOGLE_CREDS_JSON)
print(f"Credentials loaded for: {_creds_check['client_email']}")

def get_gemini_url(key):
    return (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent?key=" + key
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
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192},
    }
    if use_search:
        payload["tools"] = [{"google_search": {}}]

    # Try each API key, rotate on 429
    keys_to_try = []
    for key in GEMINI_API_KEYS:
        keys_to_try += [key] * 2  # try each key twice before moving on

    for attempt, key in enumerate(keys_to_try, 1):
        print(f"  Gemini call attempt {attempt}/{len(keys_to_try)} (key ...{key[-6:]})...")
        try:
            resp = requests.post(get_gemini_url(key), json=payload, timeout=120)
        except requests.exceptions.Timeout:
            print("  Request timed out, retrying...")
            time.sleep(5)
            continue

        if resp.status_code == 429:
            print(f"  429 rate limit on key ...{key[-6:]}, trying next key...")
            time.sleep(2)
            continue

        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
            time.sleep(5)
            continue

        data      = resp.json()
        candidate = data.get("candidates", [{}])[0]
        reason    = candidate.get("finishReason", "UNKNOWN")
        print(f"  Finish reason: {reason}")

        if "content" not in candidate:
            block = data.get("promptFeedback", {}).get("blockReason", "unknown")
            print(f"  No content. Block reason: {block}. Full: {json.dumps(data)[:300]}")
            time.sleep(3)
            continue

        parts = candidate["content"].get("parts", [])
        text  = "".join(p.get("text", "") for p in parts if "text" in p).strip()
        print(f"  Response length: {len(text)}")

        if text:
            return text, reason

        time.sleep(3)

    raise ValueError(f"Gemini failed after trying all {len(GEMINI_API_KEYS)} API key(s). All quota exceeded or errored.")


# ── Step 1: Search prompt (plain text output, small) ─────────────────────────

SEARCH_PROMPT = f"""
Today is {datetime.now().strftime('%B %d, %Y')}.

Search the web for remote web developer jobs using these searches:
1. remote React developer job weworkremotely.com
2. remote frontend developer job wellfound.com
3. remote full stack JavaScript developer job

For each job found write:
- Company name
- Job title
- Salary (or "Not Listed")
- Required skills
- Job URL (full link if available, otherwise the site homepage)
- Date posted (best estimate if exact date not shown)

Find 3 jobs. Plain text only. Do your best — include whatever details you can find.
"""

# ── Step 2: JSON conversion prompt (no search, controlled size) ───────────────

def make_json_prompt(job_text):
    return f"""Convert these job listings to JSON. Evaluate each against my profile.

MY PROFILE: {MY_PROFILE}

JOB LISTINGS:
{job_text[:1500]}

CRITICAL RULES:
- job_url: copy the FULL URL exactly as found (must start with https://). Write "Not Found" if missing
- date_posted: copy the EXACT date (e.g. "March 10, 2026"). Write "Not Found" if missing
- missing_skills: only skills from required_skills that I lack per my profile
- match_score: integer 0-100
- Max 3 responsibilities, 5 required_skills, 3 nice_to_have, 3 missing_skills
- All strings under 100 chars

Output ONLY raw JSON, nothing else, starting with {{ ending with }}:
{{
  "jobs": [
    {{
      "company_name": "...",
      "job_title": "...",
      "salary_range": "...",
      "responsibilities": ["...", "..."],
      "required_skills": ["...", "..."],
      "nice_to_have_skills": ["...", "..."],
      "missing_skills": ["..."],
      "match_score": 70,
      "job_url": "https://...",
      "date_posted": "Month DD, YYYY"
    }}
  ],
  "top_missing_skills": ["...", "...", "...", "...", "..."]
}}"""


# ── Parse JSON (with truncation recovery) ────────────────────────────────────

def parse_json(text):
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*",     "", text)
    text = text.strip()

    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object in response:\n{text[:600]}")

    end = text.rfind("}") + 1

    # If truncated (no closing brace), try to fix by closing open brackets
    if end <= 1:
        print("  Response truncated — attempting to close open JSON...")
        partial = text[start:]
        open_braces  = partial.count("{") - partial.count("}")
        open_brackets = partial.count("[") - partial.count("]")
        partial += "]" * max(open_brackets, 0)
        partial += "}" * max(open_braces, 0)
        text = partial
        end = len(text)

    json_str = text[start:end]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"  JSON decode error: {e} — attempting recovery...")

        # Try extracting individual complete job objects
        matches = re.findall(
            r'\{[^{}]*"company_name"[^{}]*"match_score"\s*:\s*\d+[^{}]*\}',
            json_str, re.DOTALL
        )
        jobs = []
        for m in matches:
            try:
                jobs.append(json.loads(m))
            except Exception:
                pass

        if not jobs:
            raise ValueError(f"Could not recover jobs from:\n{json_str[:600]}")

        all_missing = []
        for job in jobs:
            all_missing.extend(job.get("missing_skills", []))
        top = [s for s, _ in Counter(all_missing).most_common(5)]
        print(f"  Recovered {len(jobs)} jobs.")
        return {"jobs": jobs, "top_missing_skills": top}


# ── Fetch jobs ────────────────────────────────────────────────────────────────

def fetch_jobs():
    print("Step 1: Searching for jobs...")
    job_text, _ = call_gemini(SEARCH_PROMPT, use_search=True)
    print(f"  Preview: {job_text[:200]}\n")

    print("Step 2: Converting to JSON...")
    json_text, reason = call_gemini(make_json_prompt(job_text), use_search=False)
    print(f"  Preview: {json_text[:200]}\n")

    if reason == "MAX_TOKENS":
        print("  Warning: response was truncated, attempting recovery...")

    result = parse_json(json_text)
    print(f"  Parsed {len(result.get('jobs', []))} jobs.")
    return result


# ── Google Sheets auth ────────────────────────────────────────────────────────

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
    sheets_req("PUT", f"/values/{tab}!A1?valueInputOption=RAW",
               token, json={"values": rows})
    print(f"Written {len(jobs)} jobs to '{tab}'")

    print(f"Done! {len(jobs)} jobs saved. Top skills to learn: {', '.join(top_missing)}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = fetch_jobs()
    write_to_sheets(result)