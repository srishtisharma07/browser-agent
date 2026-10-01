# AI Browser Agent

**SIH Problem Statement: SIH260171 — AI-Powered Browser Assistant / Agent**

---

## Project Vision

AI Browser Agent is an intelligent, autonomous browser assistant built for Smart India Hackathon 2024.
The system will leverage a large language model (Google Gemini) orchestrated by LangGraph to interpret
natural-language instructions and autonomously control a Chromium browser via Playwright — enabling
end-to-end web tasks such as job searching, form filling, and multi-step research workflows with
minimal human intervention.

> **Phase 1 status:** Repository initialised. Browser automation and the AI agent are **not yet implemented.**

---

## Technology Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18 · Vite · Tailwind CSS |
| **Backend** | Python 3.11+ · FastAPI · Uvicorn |
| **Agent Orchestration** | LangGraph *(planned – Phase 2)* |
| **LLM** | Google Gemini API *(planned – Phase 2)* |
| **Browser Automation** | Playwright + Chromium *(planned – Phase 2)* |

---

## Current Implementation Status

### ✅ Phase 1 — Initialisation (current)
- Monorepo scaffold: `frontend/`, `backend/`, `docs/`
- React + Vite frontend with placeholder UI
- FastAPI backend with `GET /api/health` endpoint
- CORS configured for local development
- `.gitignore`, `.env.example`, and README in place

### 🔲 Phase 2 — Agent Core *(not started)*
- LangGraph agent graph
- Gemini LLM integration
- Playwright browser automation

### 🔲 Phase 3 — Features *(not started)*
- Job search workflows
- Form filling
- Multi-step task execution
- Real-time agent status streaming

---

## Getting Started

### Prerequisites

- Node.js ≥ 18
- Python ≥ 3.11
- npm ≥ 9

---

### 1. Clone and set up environment

```bash
git clone <repo-url>
cd ai-browser-agent
cp .env.example .env   # fill in values as needed
```

---

### 2. Start the backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the development server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check: <http://localhost:8000/api/health>  
Interactive docs: <http://localhost:8000/docs>

---

### 3. Start the frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the Vite dev server
npm run dev
```

App: <http://localhost:5173>

---

## Project Structure

```text
ai-browser-agent/
├── frontend/          # React + Vite + Tailwind CSS
│   ├── src/
│   │   ├── App.jsx    # Root component
│   │   └── main.jsx   # Entry point
│   └── ...
├── backend/           # Python + FastAPI
│   ├── app/
│   │   ├── __init__.py
│   │   └── main.py    # FastAPI application
│   └── requirements.txt
├── docs/              # Project documentation
├── .env.example       # Environment variable template
├── .gitignore
└── README.md
```

---

## Disclaimer

Browser automation (**Playwright**) and the AI agent (**LangGraph + Gemini**) are **not implemented yet**.
This repository represents the clean Phase 1 foundation that subsequent phases will build upon.
