# 🚀 Opportunity Radar AI

**Discover opportunities. Research smarter. Make informed decisions.**

Opportunity Radar AI is an AI-powered research assistant that helps students discover hackathons, internships, scholarships, early-career jobs, and other opportunities through live web search.

Instead of manually searching multiple websites, users can enter their interests, select an opportunity category, specify their location and study level, and receive relevant search results with source links and an optional AI-generated research brief.

🔗 **Live Demo:** https://opportunity-radar-ai-xi.vercel.app/  
💻 **GitHub Repository:** https://github.com/jeevanabhi-r/Opportunity-Radar-AI

---

## 📌 Table of Contents

- [Problem Statement](#-problem-statement)
- [Our Solution](#-our-solution)
- [Key Features](#-key-features)
- [How It Works](#-how-it-works)
- [Technology Stack](#-technology-stack)
- [Project Structure](#-project-structure)
- [Getting Started](#-getting-started)
- [Environment Variables](#-environment-variables)
- [Running the Application](#-running-the-application)
- [API Endpoints](#-api-endpoints)
- [Testing](#-testing)
- [Deployment](#-deployment)
- [Security and Privacy](#-security-and-privacy)
- [Limitations](#-limitations)
- [Future Improvements](#-future-improvements)
- [Contributing](#-contributing)
- [License](#-license)

## 🎯 Problem Statement

Students often struggle to find relevant opportunities because information is scattered across websites, deadlines may be unclear, and some search results are outdated or unrelated to their interests.

Manually verifying every result takes time and makes it difficult to identify promising opportunities.

## 💡 Our Solution

Opportunity Radar AI combines live web search, relevance-focused result organization, source checks, and AI-generated summaries to make opportunity research easier.

Users can search based on:

- **Interest or topic:** For example, AI agents, cybersecurity, web development, or machine learning.
- **Opportunity type:** Hackathons, internships, scholarships, jobs, and other supported categories.
- **Location:** Such as India or a specific region.
- **Study level:** Such as undergraduate or another supported level.

The application organizes results into primary opportunities and secondary leads so users can investigate the most relevant sources first.

## ✨ Key Features

### 🔍 1. Topic-Based Opportunity Discovery
Search for opportunities using a topic, category, location, and study level.

### 🌐 2. Live Web Search
Uses the SerpApi Google Search API to discover relevant web pages. Results depend on search coverage, ranking, network availability, and API limits.

### 🎯 3. Relevance-Based Organization
Separates primary opportunities from directories, adjacent matches, and secondary leads to help users prioritize their research.

### 🧠 4. AI-Generated Research Briefs
Uses the Groq API to generate a narrative brief when the AI service is configured and available. Search results can still be displayed without the AI brief.

### 🔗 5. Source Links
Provides links to original web pages so users can investigate the details themselves.

### 🛡️ 6. Source Accessibility Checks
Distinguishes readable sources from unreachable or unchecked sources. A readable page does not automatically mean that an organizer or opportunity is authentic.

### 📅 7. Conservative Status and Deadline Reporting
Uses available page evidence to extract status and deadline information. Unknown status and unverified deadlines are retained when sufficient evidence is unavailable.

### 🧪 8. Automated Tests
Includes tests that mock external services, allowing core application behavior to be tested without spending live API credits.

---

## ⚙️ How It Works

1. **Enter your interests:** Describe the type of opportunity you want to find.
2. **Choose your filters:** Select the opportunity type, location, and study level.
3. **Discover opportunities:** The backend builds relevant search queries and retrieves web results through SerpApi.
4. **Organize the results:** The application processes, deduplicates, and classifies the results.
5. **Check available evidence:** Source accessibility and explicitly supported status or deadline details are assessed.
6. **Generate an AI brief:** Groq can provide a narrative summary when configured and available.
7. **Verify before applying:** Open the original source to confirm eligibility, authenticity, application availability, and deadlines.

---

## 🧰 Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend application logic |
| FastAPI | Web framework and API endpoints |
| Uvicorn | Runs the Python application server |
| SerpApi | Google Search results |
| Groq API | AI-generated research briefs |
| HTML | Frontend structure |
| CSS | Styling and responsive interface |
| JavaScript | Frontend interactions and API requests |
| HTTPX | HTTP requests and source accessibility checks |
| python-dotenv | Loads environment variables locally |
| Pytest | Automated testing |

---

## 📁 Project Structure

```text
Opportunity-Radar-AI/
│
├── app.py                 # FastAPI backend
├── requirements.txt       # Python dependencies
├── test_app.py            # Automated tests
├── render.yaml            # Render deployment configuration
├── .env.example           # Example environment variables
├── .gitignore             # Files excluded from Git
├── README.md              # Project documentation
│
└── static/
    ├── index.html         # Main webpage
    ├── styles.css         # Frontend styling
    └── app.js             # Frontend JavaScript
```

**Note:** `.env` contains your local API credentials and should not be committed to GitHub.

---

## 🚀 Getting Started

Follow these instructions to run the application on your computer.

### Prerequisites

Install the following:

- Python 3.11 or newer
- Git (optional, for cloning the repository)
- A SerpApi API key for live search
- A Groq API key for AI-generated briefs (optional)

### Step 1: Clone the Repository

Open a terminal and run:

```bash
git clone https://github.com/jeevanabhi-r/Opportunity-Radar-AI.git
cd Opportunity-Radar-AI
```

Alternatively, download the repository as a ZIP file from GitHub and extract it.

### Step 2: Create a Virtual Environment

**Windows PowerShell:**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, you can use the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**macOS or Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Dependencies

With the virtual environment activated, run:

```bash
python -m pip install -r requirements.txt
```

### Step 4: Configure Environment Variables

Create a local `.env` file from the example:

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

Open `.env` in your code editor and replace the placeholder values with your own API credentials.

### Step 5: Start the Application

```bash
python -m uvicorn app:app --reload
```

When the server starts successfully, open:

**Application:** http://127.0.0.1:8000

**Health check:** http://127.0.0.1:8000/api/health

The health endpoint reports service configuration without returning the actual API key values.

---

## 🔐 Environment Variables

The application uses environment variables to configure external services.

Create a `.env` file in the project root:

```env
SERPAPI_KEY=your_serpapi_key
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
```

Replace the example values with your actual credentials.

| Variable | Required? | Purpose |
|---|---|---|
| `SERPAPI_KEY` | Yes for live search | Authenticates SerpApi requests |
| `GROQ_API_KEY` | Optional | Enables AI-generated briefs |
| `GROQ_MODEL` | Optional | Selects the Groq model; the backend may use a default if omitted |

Use the model supported by your Groq account and configured for your application.

**Important security rules:**

- Never commit `.env` to GitHub.
- Never put API keys in frontend JavaScript or HTML.
- Never publish API keys in screenshots, documentation, or videos.
- If a key is exposed publicly, revoke it and generate a replacement.
- For hosted deployments, configure secrets in the hosting provider's environment-variable settings.

---

## 🔌 API Endpoints

### 1. Health Check

**Endpoint:** `GET /api/health`

Checks the application's service configuration.

Example:

```bash
curl http://127.0.0.1:8000/api/health
```

### 2. Search Opportunities

**Endpoint:** `POST /api/search`

Accepts search criteria and returns structured opportunity results, report information, secondary leads, and optional narrative fields.

Example request:

```json
{
  "topic": "AI agents and cybersecurity",
  "opportunity_type": "Hackathons",
  "location": "India",
  "student_level": "Undergraduate"
}
```

Example using Python:

```python
import requests

url = "http://127.0.0.1:8000/api/search"

payload = {
    "topic": "AI agents and cybersecurity",
    "opportunity_type": "Hackathons",
    "location": "India",
    "student_level": "Undergraduate"
}

response = requests.post(url, json=payload, timeout=120)

print(response.status_code)
print(response.json())
```

Run this example while the application is running locally. Actual response fields and results depend on the backend implementation and available search data.

---

## 🧪 Testing

Run the following commands from the project root.

### Check Python Syntax

```bash
python -m py_compile app.py test_app.py
```

### Run Automated Tests

```bash
python -m pytest -q
```

### Check JavaScript Syntax

If Node.js is installed:

```bash
node --check static/app.js
```

The automated tests use mocked external services, so they can test application behavior without making live SerpApi or Groq requests.

Passing automated tests does not guarantee that external APIs, deployment settings, or live search results will always work.

---

## ☁️ Deployment

The repository includes a `render.yaml` file for a Render deployment configuration. The frontend and Python backend must both be served correctly by whichever hosting provider you use.

### Option A: Deploy with Render

1. Push your code to GitHub.
2. Open [Render](https://render.com/).
3. Create a new Web Service and connect your repository.
4. Check the service settings and the included `render.yaml`.
5. Configure `SERPAPI_KEY` in the Render environment variables.
6. Add `GROQ_API_KEY` if you want AI-generated briefs.
7. Deploy and check the service logs.
8. Open the deployed homepage and `/api/health`.

For a manual FastAPI configuration, the typical commands are:

**Build command**

```bash
pip install -r requirements.txt
```

**Start command**

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

Use the actual service settings and deployment configuration required by your host.

### Option B: Deploy with Vercel

Live demo: https://opportunity-radar-ai-xi.vercel.app/

For Vercel deployments:

1. Connect the GitHub repository to your Vercel project.
2. Configure the environment variables required by the backend in Vercel project settings.
3. Ensure the Python FastAPI backend is configured to run correctly on Vercel.
4. Redeploy after changing environment variables.
5. Test both the homepage and `/api/health`.
6. Run a search to verify that the backend can reach SerpApi.

**Troubleshooting:** If the application displays `SERPAPI_KEY is missing`, verify that the variable exists in the correct Vercel environment, such as Production, and redeploy. If `/api/health` returns a 404 or a server error, check the backend deployment configuration and logs.

A frontend loading successfully does not necessarily mean that the backend is working.

---

## 🔒 Security and Privacy

Opportunity Radar AI follows several important precautions:

- API credentials are intended to remain on the server.
- `.env` is excluded from version control.
- `.env.example` provides placeholders instead of real secrets.
- Health diagnostics do not expose API key values.
- Source checks include timeouts and checks intended to prevent requests to non-public hosts.
- Frontend rendering uses safer handling for generated narrative text and source links.

Source accessibility checks are not a complete security guarantee. Always keep dependencies updated and review security changes before deploying.

---

## ⚠️ Limitations

- Search results may be incomplete, outdated, irrelevant, or unavailable.
- Not every opportunity will be discovered.
- A readable webpage does not prove that an opportunity is legitimate.
- Deadlines and application status may remain unverified if clear evidence is unavailable.
- AI-generated summaries can contain mistakes and must be checked against original sources.
- Live search depends on SerpApi availability and quotas.
- AI summaries depend on Groq availability, configuration, and quotas.
- The application helps users research opportunities; it does not apply on their behalf or guarantee eligibility.

**Always verify important information on the official opportunity website before applying.**

---

## 🛣️ Future Improvements

Potential future enhancements include:

- User accounts and saved opportunities.
- Deadline reminders and notifications.
- Filters for remote, online, and in-person opportunities.
- Improved official-source verification.
- More detailed eligibility matching.
- Exporting search reports.
- Better search history and personalized recommendations.

These are planned improvements and are not necessarily available in the current version.

---

## 🤝 Contributing

Contributions and suggestions are welcome.

1. Fork this repository.
2. Create a branch for your changes.
3. Implement and test your changes.
4. Submit a pull request with a clear explanation.

Please do not include API keys, passwords, or other sensitive information in commits or issue reports.

---

## 📄 License

No license is specified here. Before reusing, modifying, or redistributing this project, check whether a license has been added to the repository. You can add an appropriate open-source license if you intend to permit public reuse.

---

## 👨‍💻 Project

**Opportunity Radar AI**

Built to help students discover and research opportunities more efficiently through live search and AI-assisted summaries.

- **Live Demo:** https://opportunity-radar-ai-xi.vercel.app/
- **Source Code:** https://github.com/jeevanabhi-r/Opportunity-Radar-AI

*Discover opportunities. Verify the evidence. Take the next step.*
