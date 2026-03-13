# 🚀 Remote Web Dev Job Tracker

> Automatically finds remote web developer jobs every day, analyzes your skill gaps, and saves everything to your Google Sheet — completely free.

![GitHub Actions](https://img.shields.io/badge/Automated-GitHub_Actions-2088FF?style=flat-square&logo=github-actions&logoColor=white)
![Gemini AI](https://img.shields.io/badge/Powered_by-Gemini_AI-4285F4?style=flat-square&logo=google&logoColor=white)
![Google Sheets](https://img.shields.io/badge/Saves_to-Google_Sheets-34A853?style=flat-square&logo=google-sheets&logoColor=white)
![Free](https://img.shields.io/badge/Cost-100%25_Free-brightgreen?style=flat-square)

---

## ✨ What It Does

Every day at **8 PM** the script automatically:

1. 🔍 Searches the web for fresh remote web dev job postings
2. 🤖 Analyzes each job against your skill profile
3. 📊 Calculates your match percentage and identifies skill gaps
4. 📝 Appends results to your Google Sheet (never overwrites old data)

---

## 📋 Prerequisites

Before you start, make sure you have:

- A **GitHub** account → [github.com](https://github.com)
- A **Google** account (for Sheets)
- A **Gemini API** key (free) → [aistudio.google.com](https://aistudio.google.com)

---

## 🛠️ Setup Guide

### Step 1 — Get Your Gemini API Key

1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Sign in with your Google account
3. Click **"Get API Key"** → **"Create API key"**
4. Copy the key — it looks like `AIzaSy...`

> 💡 The free tier gives you 250+ requests/day — more than enough for one daily run.

---

### Step 2 — Set Up Google Sheets API

#### 2a. Create a Google Cloud Project
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click the project dropdown at the top → **"New Project"**
3. Name it `job-tracker` → click **Create**

#### 2b. Enable Required APIs
1. In the left menu → **"APIs & Services"** → **"Enable APIs and Services"**
2. Search **"Google Sheets API"** → click **Enable**
3. Go back → search **"Google Drive API"** → click **Enable**

#### 2c. Create a Service Account
1. Left menu → **"APIs & Services"** → **"Credentials"**
2. Click **"+ Create Credentials"** → **"Service Account"**
3. Name it `job-tracker-bot` → click **Done**

#### 2d. Download the JSON Key
1. Click on your new service account → go to **"Keys"** tab
2. Click **"Add Key"** → **"Create new key"** → select **JSON**
3. A `.json` file downloads automatically — **keep this safe!**

#### 2e. Create Your Google Sheet
1. Go to [sheets.google.com](https://sheets.google.com) → create a new sheet
2. Name it **"Web Dev Jobs"**
3. Copy the **Spreadsheet ID** from the URL:
   ```
   https://docs.google.com/spreadsheets/d/YOUR_ID_IS_HERE/edit
   ```
4. Open the downloaded JSON file → find the `client_email` field:
   ```
   job-tracker-bot@job-tracker-xxxxx.iam.gserviceaccount.com
   ```
5. In your Google Sheet → click **Share** → paste that email → set to **Editor** → click **Send**

---

### Step 3 — Set Up the GitHub Repository

#### 3a. Create a Private Repo
1. Go to [github.com](https://github.com) → click **"New"**
2. Name it `job-tracker` → set to **Private** → click **Create repository**

#### 3b. Set Up the File Structure
Create this exact structure on your computer:

```
job-tracker/
├── job_tracker.py
└── .github/
    └── workflows/
        └── daily.yml
```

Download both files from this repo and place them accordingly.

#### 3c. Push to GitHub
Open terminal in your `job-tracker` folder:

```bash
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/job-tracker.git
git push -u origin main
```

---

### Step 4 — Add GitHub Secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these 3 secrets:

| Secret Name | Value |
|---|---|
| `GEMINI_API_KEY` | Your Gemini API key (`AIzaSy...`) |
| `SPREADSHEET_ID` | Your Google Sheet ID |
| `GOOGLE_CREDENTIALS` | Contents of your JSON file (see below) |

#### How to encode your Google credentials

**Windows (PowerShell):**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\path\to\your-credentials.json")) | clip
```

**Mac/Linux:**
```bash
base64 -i your-credentials.json | tr -d '\n' | pbcopy
```

This copies the encoded value to your clipboard. Paste it as the `GOOGLE_CREDENTIALS` secret.

> ⚠️ Never commit your credentials JSON file to GitHub. Add it to `.gitignore`.

---

### Step 5 — Customize Your Profile

Open `job_tracker.py` and edit the `MY_PROFILE` section to match your actual skills:

```python
MY_PROFILE = """
Skills: HTML, CSS, JavaScript, React, basic Node.js, Git, REST APIs, Tailwind CSS
Experience: Self-taught, no industry/professional experience yet
Also know: TypeScript (basic), basic SQL
Missing: Docker, AWS, GraphQL, Next.js (intermediate+), CI/CD, Redis, Jest/Vitest
Target: Remote entry-level or junior frontend/full-stack roles, $40k+ salary
"""
```

Be honest about your skills — the more accurate this is, the better your match scores will be.

---

### Step 6 — Test It

Before waiting for 8 PM, trigger a manual run:

1. Go to your repo → **Actions** tab
2. Click **"Daily Job Tracker"** in the left sidebar
3. Click **"Run workflow"** → **"Run workflow"** (green button)
4. Wait ~30 seconds
5. Check your Google Sheet — a new **"All Jobs"** tab should appear with results!

---

## 📊 Understanding Your Google Sheet

The **"All Jobs"** sheet grows every day with new rows:

| Column | Description |
|---|---|
| **Date Added** | When the job was found |
| **Company** | Company name |
| **Role** | Job title |
| **Salary** | Salary range if listed |
| **Match %** | How well you match the role |
| **Responsibilities** | Key job duties |
| **Required Skills** | Skills the job needs |
| **Nice to Have** | Bonus skills |
| **Skills I'm Missing** | Gaps based on your profile |
| **Date Posted** | When the job was posted |
| **Job URL** | Direct link to apply |

---

## ⏰ Schedule

The script runs automatically every day at **8 PM Bangladesh Time (UTC+6)**.

To change the time, edit `.github/workflows/daily.yml`:

```yaml
- cron: '0 14 * * *'  # 14:00 UTC = 8 PM Bangladesh (UTC+6)
```

Use [crontab.guru](https://crontab.guru) to calculate your timezone.

---

## 🔑 Optional: Add a Backup Gemini API Key

If your primary key hits the daily rate limit, the script automatically falls back to a second key.

1. Get a second Gemini API key from [aistudio.google.com](https://aistudio.google.com)
2. Add it as a secret named `GEMINI_API_KEY_2`

---

## 🐛 Troubleshooting

| Error | Fix |
|---|---|
| `KeyError: 'GOOGLE_CREDENTIALS'` | Secret name doesn't match — check spelling in GitHub Secrets |
| `429 rate limit` | Gemini daily quota exceeded — add a second API key or wait until tomorrow |
| `0 jobs found` | Gemini couldn't find jobs — will retry tomorrow automatically |
| `JSONDecodeError` | Gemini response was cut off — already handled by retry logic |
| Sheet not updating | Check service account has **Editor** access to your Google Sheet |

---

## 💡 Pro Tips

- **Combine with job alerts** — set up free email alerts on [LinkedIn](https://linkedin.com/jobs), [Indeed](https://indeed.com), [Wellfound](https://wellfound.com), and [Himalayas](https://himalayas.app) for maximum coverage
- **Update your profile regularly** — as you learn new skills, update `MY_PROFILE` in the script so your match scores stay accurate
- **Check GitHub Actions logs** — if something goes wrong, go to Actions tab → click the failed run → expand "Run job tracker" to see detailed logs

---

## 📁 Project Structure

```
job-tracker/
├── job_tracker.py          # Main script
├── .github/
│   └── workflows/
│       └── daily.yml       # GitHub Actions scheduler
├── .gitignore              # Make sure credentials are ignored
└── README.md               # This file
```

**.gitignore** should contain:
```
*.json
.env
```

---

## 🆓 Cost Breakdown

| Service | Free Tier | Usage |
|---|---|---|
| GitHub Actions | 2,000 min/month | ~15 min/month ✅ |
| Gemini API | 250 req/day | 2 req/day ✅ |
| Google Sheets API | Unlimited | ~5 req/day ✅ |
| Google Cloud | Free | Service account only ✅ |

**Total cost: $0/month** 🎉

---

## 🤝 Contributing

Found a bug or want to improve the script? Feel free to open an issue or submit a pull request.
