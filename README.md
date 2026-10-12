# Opportunity Radar AI

Opportunity Radar AI is a student research assistant for discovering hackathons, internships, scholarships, early-career jobs, and broader opportunities. It searches Google results through SerpApi, ranks individual opportunities separately from directories and secondary leads, checks source-page accessibility, and can request a narrative research brief from Groq.

Search results and AI summaries are leads—not proof of eligibility, authenticity, application availability, or deadlines. Always inspect the original source before acting.

## Features

- Category-, topic-, location-, and study-level-aware search queries with a small bounded number of follow-up searches.
- Primary results separated from directories, adjacent matches, and third-party leads.
- Deduplication and conservative status/deadline extraction from explicitly worded source-page evidence.
- Source-check states distinguish readable pages from unreachable and unchecked sources; readability does not verify identity.
- Deterministic report rows and evidence cards built from the structured backend results.
- Privacy-conscious server diagnostics and safe DOM rendering of narrative and source links.
- Search results remain available when Groq is not configured or cannot generate a summary.

## Architecture

- **Backend:** Python, FastAPI, Uvicorn, HTTPX, and `python-dotenv`.
- **Search:** SerpApi Google Search API.
- **Narrative:** Groq Chat Completions API.
- **Frontend:** Existing HTML, CSS, and vanilla JavaScript in `static/`.
- **Tests:** Pytest with mocked external services; tests do not spend SerpApi or Groq credits.

## Prerequisites

- Windows PowerShell and Python 3.11 or newer.
- A SerpApi key for live searches.
- A Groq key is optional; without it, search results still display and the AI brief is unavailable.
- Node.js is optional and is only needed for the JavaScript syntax check.

## Install and run on Windows

Run these commands from the project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

In `.env`, replace the placeholder values locally. Do not paste real credentials into the README, source files, screenshots, or public issue reports:

```dotenv
SERPAPI_KEY=your_serpapi_key
GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.3-70b-versatile
```

`GROQ_API_KEY` is optional if only live search is required. `GROQ_MODEL` uses the configured model or the backend default if omitted.

Start the application:

```powershell
python -m uvicorn app:app --reload
```

Open <http://127.0.0.1:8000>. `GET /api/health` reports whether each service is configured without returning API key values.

## Run tests and checks

From the project folder with the virtual environment active:

```powershell
python -m py_compile app.py test_app.py
python -m pytest -q
node --check static\app.js
```

The Node.js check is optional if Node.js is not installed. The test suite mocks external API and source-page calls; running it does not perform live searches.

## API

- `GET /` serves the web interface.
- `GET /api/health` returns service-configuration flags and the configured Groq model name.
- `POST /api/search` accepts `topic`, `opportunity_type`, `location`, and `student_level`, and returns structured primary results, report rows, optional secondary results, and narrative fields.

Example request:

```json
{
  "topic": "AI agents and cybersecurity",
  "opportunity_type": "Hackathons",
  "location": "India",
  "student_level": "Undergraduate"
}
```

## Security and limitations

- API keys are loaded from environment variables; `.env` is ignored by Git. `.env.example` contains placeholders only.
- Do not publish real credentials. If a key is exposed, revoke and replace it.
- Source checks use timeouts, reject non-public host resolutions, and validate each redirect target. DNS is not pinned to the validated address for the HTTP connection, so this is not a complete DNS-rebinding defense. The source-text parsing cap is applied after HTTPX receives the response body, not as a strict network-download limit. Source accessibility is not source or organizer verification.
- Search results can be stale, incomplete, misclassified, or unavailable. Third-party results are not treated as official solely because a page is readable.
- Application status remains Unknown and deadlines remain Unverified unless explicit page evidence supports a different value. Past deadlines are labeled potentially expired.
- AI output is narrative only and may still make mistakes. Structured report data comes from backend result objects; verify claims against original pages.
- Results depend on SerpApi coverage, ranking, network availability, and provider quotas. No search is guaranteed to find actionable opportunities.
- The application does not submit applications or make eligibility decisions.

## Demonstration and submission checklist

1. Add API keys to the local `.env` file and start the app.
2. Confirm the homepage loads at <http://127.0.0.1:8000> and check `/api/health`.
3. Run one focused search and one different category or topic; note that these use live SerpApi credits.
4. Compare the primary results, secondary leads, report rows, and evidence cards. Open original sources and review source-check, status, and deadline notes.
5. Run the mocked test suite and syntax checks above.
6. Before publishing, confirm `.env` is not included, inspect the final repository contents, and include the source-verification limitations in the demo.
7. Follow the submission organizer's requirements for repository visibility, demo links, and AI-use disclosure.

## Optional Render deployment

The included `render.yaml` defines the existing Render web service. Configure `SERPAPI_KEY`, and optionally `GROQ_API_KEY`, as Render environment variables. Never add credentials to `render.yaml` or commit `.env`.
